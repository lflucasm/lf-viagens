import { createAdminClient } from "@/lib/supabase/admin";
import { cifrar, criptoConfigurada } from "@/lib/cripto";
import type { Programa } from "@/lib/cedentes";

type ClienteAdmin = ReturnType<typeof createAdminClient>;

export type DadosConta = { login: string; senha: string; observacao: string | null };

/**
 * Grava o andamento de uma conta do cedente — login, senha e observação de
 * um programa. Usado tanto pelo próprio titular no cadastro guiado
 * (/cedente/[token]) quanto pelo painel, quando um colaborador corrige uma
 * credencial por fora. Mesma regra dos dois lados: senha em branco não apaga
 * o que já estava salvo, e o status sai sozinho de ter (ou já ter tido)
 * login e senha guardados — não é escolhido por quem preenche.
 *
 * A senha nunca chega no banco em claro: cifra antes de gravar, numa tabela
 * que só service_role lê (ver a migration 20260819200000). Se a chave não
 * estiver configurada, recusa a senha em vez de gravar em claro — falhar
 * alto é melhor do que guardar credencial exposta sem ninguém notar.
 */
export async function salvarContaCedente(
  admin: ClienteAdmin,
  cedenteId: string,
  programa: Programa,
  { login, senha, observacao }: DadosConta,
): Promise<{ erro: string | null; status?: string }> {
  if (senha && !criptoConfigurada()) {
    return { erro: "O cofre de credenciais não está configurado. Avise a equipe da LF Viagens." };
  }

  const [{ data: contaAtual }, { data: senhaExistente }] = await Promise.all([
    admin
      .from("cedente_contas")
      .select("login, status")
      .eq("cedente_id", cedenteId)
      .eq("programa", programa)
      .maybeSingle(),
    admin
      .from("cedente_credenciais")
      .select("id")
      .eq("cedente_id", cedenteId)
      .eq("programa", programa)
      .eq("campo", "senha")
      .maybeSingle(),
  ]);

  const loginEfetivo = login || contaAtual?.login || "";
  const temSenha = Boolean(senha) || Boolean(senhaExistente);
  // Editar só a observação de uma conta que o cedente declarou "não criada"
  // não pode desfazer isso.
  const status =
    loginEfetivo && temSenha
      ? "concluida"
      : contaAtual?.status === "nao_criada"
        ? "nao_criada"
        : "pendente";

  const { error } = await admin
    .from("cedente_contas")
    .update({
      status,
      login: login || contaAtual?.login || null,
      observacao,
      concluida_em: status === "concluida" ? new Date().toISOString() : null,
      atualizado_em: new Date().toISOString(),
    })
    .eq("cedente_id", cedenteId)
    .eq("programa", programa);

  if (error) return { erro: "Não deu para salvar. Tente de novo." };

  // Credencial em branco não apaga o que já estava lá: quem edita só pra
  // mudar outra coisa não deveria perder a senha que já tinha registrado.
  const credenciais: Array<{ campo: string; valor: string }> = [];
  if (login) credenciais.push({ campo: "login", valor: login });
  if (senha) credenciais.push({ campo: "senha", valor: senha });

  for (const credencial of credenciais) {
    await admin.from("cedente_credenciais").upsert(
      {
        cedente_id: cedenteId,
        programa,
        campo: credencial.campo,
        valor_cifrado: cifrar(credencial.valor),
        atualizado_em: new Date().toISOString(),
      },
      { onConflict: "cedente_id,programa,campo" },
    );
  }

  // O e-mail criado no primeiro passo é o contato do cedente daqui pra
  // frente — sobe pro cadastro pra aparecer no painel e ir junto pro CRM.
  if (programa === "email" && login) {
    await admin.from("cedentes").update({ email_criado: login }).eq("id", cedenteId);
  }

  return { erro: null, status };
}
