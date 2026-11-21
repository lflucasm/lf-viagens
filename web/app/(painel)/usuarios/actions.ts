"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { exigirAdmin } from "@/lib/auth";

export type EstadoUsuarios = { erro: string | null; sucesso: string | null };

/**
 * Cria conta no Supabase Auth (precisa de service_role) + linha em perfis.
 * exigirAdmin() aqui não é decoração: uma Server Action é uma rota
 * chamável por qualquer requisição autenticada, não só pelo botão que a
 * dispara — a checagem de papel tem que estar na própria função.
 */
export async function criarColaborador(
  _estado: EstadoUsuarios,
  formData: FormData,
): Promise<EstadoUsuarios> {
  await exigirAdmin();

  const nome = String(formData.get("nome") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const senha = String(formData.get("senha") ?? "");
  const papel = String(formData.get("papel") ?? "atendente");

  if (!nome || !email || senha.length < 6) {
    return {
      erro: "Preencha nome, e-mail e uma senha de pelo menos 6 caracteres.",
      sucesso: null,
    };
  }
  if (papel !== "admin" && papel !== "atendente") {
    return { erro: "Papel inválido.", sucesso: null };
  }

  const admin = createAdminClient();
  const { data, error } = await admin.auth.admin.createUser({
    email,
    password: senha,
    email_confirm: true,
  });

  if (error || !data.user) {
    return { erro: error?.message ?? "Não foi possível criar o usuário.", sucesso: null };
  }

  const { error: erroPerfil } = await admin.from("perfis").insert({
    id: data.user.id,
    nome,
    papel,
    ativo: true,
  });

  if (erroPerfil) {
    // sem isso o usuario fica orfao no Auth: exigirColaborador nunca acha
    // perfil pra ele, e o e-mail fica "em uso" pro admin tentar de novo
    await admin.auth.admin.deleteUser(data.user.id);
    return { erro: erroPerfil.message, sucesso: null };
  }

  revalidatePath("/usuarios");
  return { erro: null, sucesso: `Colaborador ${nome} criado.` };
}

/**
 * Só troca perfis.ativo — passa pelo client de sessão normal (não
 * service_role): a policy "admin atualiza perfis" já garante no banco que
 * só admin consegue, então a proteção não depende só desta função.
 */
export async function alternarAtivo(formData: FormData) {
  await exigirAdmin();

  const perfilId = String(formData.get("perfil_id"));
  const ativo = formData.get("ativo") === "true";

  const supabase = await createClient();
  const { error } = await supabase.from("perfis").update({ ativo }).eq("id", perfilId);
  if (error) throw new Error(error.message);

  revalidatePath("/usuarios");
}
