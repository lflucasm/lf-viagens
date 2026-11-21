import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Database } from "@/lib/database.types";

export type Perfil = Database["public"]["Tables"]["perfis"]["Row"];

/**
 * Exige colaborador autenticado e ativo. proxy.ts já bloqueia a rota antes
 * de chegar aqui, mas a checagem se repete — um matcher mal ajustado não
 * pode virar acesso sem dono (ver aviso na doc do proxy.js do Next 16).
 */
export async function exigirColaborador(): Promise<{ perfil: Perfil }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: perfil } = await supabase
    .from("perfis")
    .select("*")
    .eq("id", user.id)
    .maybeSingle();

  if (!perfil || !perfil.ativo) redirect("/login");

  return { perfil };
}

export async function exigirAdmin(): Promise<{ perfil: Perfil }> {
  const { perfil } = await exigirColaborador();
  if (perfil.papel !== "admin") redirect("/");
  return { perfil };
}
