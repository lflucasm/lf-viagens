import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { exigirColaboradorPorToken } from "../_auth";

/**
 * POST /api/extensao/chat-token
 * body: { access_token?: string, refresh_token: string, expira_em?: number }
 *
 * Recebe o token de sessão do VollyChat (backend Supabase SEPARADO da Volly,
 * projeto SEU_PROJETO_CHAT - ver src/volly_chat.py) que o content
 * script `content-chat-token.js` capta do localStorage sempre que a aba do
 * navegador renova sozinha. Grava em chat_auth_state pra src/relatorio_gestao.py
 * (rodando local ou no GitHub Actions) ler dali, em vez de ter dois lados
 * girando o mesmo refresh_token sem se falar e um invalidando o outro.
 *
 * `chat_auth_state` nao tem policy de RLS pra `authenticated` de proposito
 * (e um token de sessao, nao dado de agencia) - por isso usa o client
 * service_role aqui dentro, depois de confirmar que quem chamou e
 * colaborador ativo (exigirColaboradorPorToken, mesma auth do resto de
 * /api/extensao/*).
 *
 * `chat_auth_state` ainda nao esta no database.types.ts gerado (tabela nova,
 * tabelas geradas nao foram atualizadas) - por isso o client aqui e sem o
 * generic <Database>, so pra essa tabela.
 */
export async function POST(req: Request) {
  const { erro } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const body = (await req.json().catch(() => null)) as {
    access_token?: string;
    refresh_token?: string;
    expira_em?: number;
  } | null;

  if (!body || typeof body.refresh_token !== "string" || !body.refresh_token) {
    return Response.json({ error: "refresh_token obrigatório" }, { status: 400 });
  }

  const admin = createSupabaseClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );

  const { error } = await admin.from("chat_auth_state").upsert(
    {
      id: "lfviagens",
      access_token: body.access_token ?? null,
      refresh_token: body.refresh_token,
      expira_em: typeof body.expira_em === "number" ? body.expira_em : null,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "id" },
  );

  if (error) return Response.json({ error: error.message }, { status: 400 });
  return Response.json({ ok: true });
}
