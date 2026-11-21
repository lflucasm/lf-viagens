import { createClient as createSupabaseClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/database.types";

type Perfil = Database["public"]["Tables"]["perfis"]["Row"];

type ResultadoAuth =
  | { erro: Response; perfil?: undefined; supabase?: undefined }
  | { erro?: undefined; perfil: Perfil; supabase: SupabaseClient<Database> };

/**
 * A extensão Chrome não compartilha cookie com o domínio do Vercel — o
 * login acontece direto contra o Supabase (signInWithPassword) e o JWT
 * resultante viaja como Bearer token em cada chamada às rotas /api/extensao/*.
 * Esta função é o equivalente de exigirColaborador() (web/lib/auth.ts) para
 * esse caso: valida o JWT e confirma que o colaborador está ativo.
 *
 * No sucesso devolve também o `supabase` já com o JWT no header — as rotas que
 * mexem em tabela (config de preço) usam esse mesmo client pra escrita/leitura
 * passar pela RLS de colaborador.
 */
export async function exigirColaboradorPorToken(req: Request): Promise<ResultadoAuth> {
  const authHeader = req.headers.get("authorization") ?? "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;

  if (!token) {
    return { erro: Response.json({ error: "Token ausente" }, { status: 401 }) };
  }

  // O token vai no header global, não só no getUser(): a policy
  // "colaborador le perfis" usa eh_colaborador_ativo(), que depende de
  // auth.uid(). Sem o JWT na requisição ao PostgREST, auth.uid() é nulo e
  // a leitura de perfis volta vazia mesmo pra colaborador ativo.
  const supabase = createSupabaseClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      auth: { autoRefreshToken: false, persistSession: false },
      global: { headers: { Authorization: `Bearer ${token}` } },
    },
  );

  const {
    data: { user },
    error: erroUsuario,
  } = await supabase.auth.getUser(token);

  if (erroUsuario || !user) {
    return { erro: Response.json({ error: "Token inválido" }, { status: 401 }) };
  }

  const { data: perfil } = await supabase
    .from("perfis")
    .select("*")
    .eq("id", user.id)
    .maybeSingle();

  if (!perfil || !perfil.ativo) {
    return { erro: Response.json({ error: "Colaborador inativo ou não encontrado" }, { status: 401 }) };
  }

  return { perfil, supabase };
}
