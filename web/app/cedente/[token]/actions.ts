"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { createAdminClient } from "@/lib/supabase/admin";
import { salvarContaCedente } from "@/lib/contasCedente";
import { CARTILHA_VERSAO, PIX_TIPOS, PROGRAMAS, type Programa, type PixTipo } from "@/lib/cedentes";

export type EstadoConta = { erro: string | null; sucesso: string | null };

export type EstadoRascunho = { erro: string | null };

export type EstadoAviso = { erro: string | null };

export type EstadoCartilha = { erro: string | null };

function texto(formData: FormData, campo: string, max = 255) {
  const v = String(formData.get(campo) ?? "").trim();
  if (!v) return null;
  return v.length > max ? v.slice(0, max) : v;
}

function inteiro(formData: FormData, campo: string) {
  const n = Number(String(formData.get(campo) ?? "").replace(/\D+/g, ""));
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.trunc(n);
}

/**
 * Fecha a Fase 1 do cadastro (rascunho -> pendente): onde receber o
 * pagamento, os pontos que já existem, e o aceite do termo. Continua sem
 * sessão — o token da URL é quem autoriza, igual salvarConta().
 */
export async function concluirCadastro(
  _estado: EstadoRascunho,
  formData: FormData,
): Promise<EstadoRascunho> {
  const token = String(formData.get("token") ?? "").trim();
  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("id, status, ativo")
    .eq("token_acesso", token)
    .maybeSingle();

  if (!cedente || !cedente.ativo) return { erro: "Link não encontrado." };
  if (cedente.status !== "rascunho") return { erro: null };

  const pixTipo = String(formData.get("pix_tipo") ?? "") as PixTipo;
  const chavePix = texto(formData, "chave_pix");
  const banco = texto(formData, "banco", 120);
  const aceitou = formData.get("aceite") === "on";
  const termoVersao = String(formData.get("termo_versao") ?? "").trim();

  if (!PIX_TIPOS.includes(pixTipo)) {
    return { erro: "Escolha o tipo da sua chave PIX." };
  }
  if (!chavePix || !banco) {
    return { erro: "Preencha o banco e a chave PIX." };
  }
  if (!aceitou || !termoVersao) {
    return { erro: "É preciso ler e aceitar o termo para continuar." };
  }

  // O termo que veio do formulário tem que ser um que está no ar agora —
  // senão um POST montado à mão registra aceite de uma versão desativada.
  const { data: termo } = await admin
    .from("termos_indicacao")
    .select("versao")
    .eq("versao", termoVersao)
    .eq("ativo", true)
    .maybeSingle();

  if (!termo) {
    return { erro: "O termo mudou enquanto você preenchia. Recarregue a página." };
  }

  const { error } = await admin
    .from("cedentes")
    .update({
      banco,
      pix_tipo: pixTipo,
      chave_pix: chavePix,
      pontos_latam: inteiro(formData, "pontos_latam"),
      pontos_smiles: inteiro(formData, "pontos_smiles"),
      pontos_livelo: inteiro(formData, "pontos_livelo"),
      pontos_esfera: inteiro(formData, "pontos_esfera"),
      status: "pendente",
      atualizado_em: new Date().toISOString(),
    })
    .eq("id", cedente.id);

  if (error) return { erro: "Não foi possível concluir o cadastro. Tente de novo." };

  const cabecalhos = await headers();
  const ip =
    cabecalhos.get("x-forwarded-for")?.split(",")[0].trim() ??
    cabecalhos.get("x-real-ip")?.trim() ??
    null;

  await admin.from("aceites_termo").insert({
    cedente_id: cedente.id,
    termo_versao: termoVersao,
    ip,
    user_agent: cabecalhos.get("user-agent"),
  });

  revalidatePath(`/cedente/${token}`);
  return { erro: null };
}

/**
 * Fecha a etapa de aviso (entre o PIX/termo e o passo a passo das contas):
 * só registra que o cedente confirmou que leu — sem isso, page.tsx mostra
 * o aviso de novo. Idempotente de propósito: reenviar o form não deve
 * sobrescrever o horário do primeiro aceite.
 */
export async function confirmarAvisoContas(
  _estado: EstadoAviso,
  formData: FormData,
): Promise<EstadoAviso> {
  const token = String(formData.get("token") ?? "").trim();
  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("id, status, ativo, aviso_contas_confirmado_em")
    .eq("token_acesso", token)
    .maybeSingle();

  if (!cedente || !cedente.ativo) return { erro: "Link não encontrado." };
  if (cedente.status === "rascunho") return { erro: null };

  if (!cedente.aviso_contas_confirmado_em) {
    const { error } = await admin
      .from("cedentes")
      .update({ aviso_contas_confirmado_em: new Date().toISOString() })
      .eq("id", cedente.id);

    if (error) return { erro: "Não foi possível continuar. Tente de novo." };
  }

  revalidatePath(`/cedente/${token}`);
  return { erro: null };
}

/**
 * Salva o andamento de uma conta do cadastro guiado, com o login e a senha
 * que o titular acabou de criar.
 *
 * Igual à action do convite: sem sessão, o que autoriza é o token da URL — e
 * ele é conferido aqui dentro, não só na página que desenhou o formulário.
 *
 * A senha nunca chega no banco em claro: cifra antes de gravar, numa tabela
 * que só service_role lê (ver a migration 20260819200000). Se a chave não
 * estiver configurada, o passo recusa a senha em vez de gravar em claro —
 * falhar alto é melhor do que guardar credencial exposta sem ninguém notar.
 */
export async function salvarConta(
  _estado: EstadoConta,
  formData: FormData,
): Promise<EstadoConta> {
  const token = String(formData.get("token") ?? "").trim();
  const programa = String(formData.get("programa") ?? "") as Programa;

  if (!token || !PROGRAMAS.some((p) => p.chave === programa)) {
    return { erro: "Passo inválido.", sucesso: null };
  }

  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("id")
    .eq("token_acesso", token)
    .maybeSingle();

  if (!cedente) return { erro: "Link não encontrado.", sucesso: null };

  const login = String(formData.get("login") ?? "").trim();
  const senha = String(formData.get("senha") ?? "");
  const observacao = String(formData.get("observacao") ?? "").trim() || null;

  const { erro, status } = await salvarContaCedente(admin, cedente.id, programa, {
    login,
    senha,
    observacao,
  });
  if (erro) return { erro, sucesso: null };

  // Antes isto dizia "Salvo." mesmo com login/senha em branco, e o cedente
  // achava que a conta estava feita. Só vale com os dois preenchidos.
  if (status !== "concluida") {
    return {
      erro: "Preencha o login e a senha da conta que você criou — ela só conta como criada com os dois.",
      sucesso: null,
    };
  }

  revalidatePath(`/cedente/${token}`);
  return { erro: null, sucesso: "Salvo." };
}

/**
 * O cedente declara que não conseguiu criar a conta da Esfera (o cadastro
 * dela costuma barrar). Só a Esfera pode ficar de fora — as outras são
 * obrigatórias —, então o programa é fixo aqui em vez de vir do formulário.
 * Conta que já está "concluida" não volta atrás.
 */
export async function marcarContaNaoCriada(
  _estado: EstadoAviso,
  formData: FormData,
): Promise<EstadoAviso> {
  const token = String(formData.get("token") ?? "").trim();
  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("id, status, ativo")
    .eq("token_acesso", token)
    .maybeSingle();

  if (!cedente || !cedente.ativo) return { erro: "Link não encontrado." };
  if (cedente.status === "rascunho") return { erro: null };

  const { error } = await admin
    .from("cedente_contas")
    .update({ status: "nao_criada", concluida_em: null, atualizado_em: new Date().toISOString() })
    .eq("cedente_id", cedente.id)
    .eq("programa", "esfera")
    .neq("status", "concluida");
  if (error) return { erro: "Não foi possível registrar. Tente de novo." };

  revalidatePath(`/cedente/${token}`);
  return { erro: null };
}

/**
 * Registra a ciência da cartilha do cedente (prova: versão, data, IP e
 * navegador em aceites_termo, igual ao aceite do termo). Idempotente: se já
 * existe aceite dessa versão, não grava outro. Sem sessão — o token da URL
 * autoriza, como no resto do cadastro.
 */
export async function confirmarCartilha(
  _estado: EstadoCartilha,
  formData: FormData,
): Promise<EstadoCartilha> {
  const token = String(formData.get("token") ?? "").trim();
  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("id, status, ativo")
    .eq("token_acesso", token)
    .maybeSingle();

  if (!cedente || !cedente.ativo) return { erro: "Link não encontrado." };
  if (cedente.status === "rascunho") return { erro: null };
  if (formData.get("ciente") !== "on") {
    return { erro: "Marque que leu a cartilha para confirmar." };
  }

  const { data: jaTem } = await admin
    .from("aceites_termo")
    .select("id")
    .eq("cedente_id", cedente.id)
    .eq("termo_versao", CARTILHA_VERSAO)
    .limit(1)
    .maybeSingle();

  if (!jaTem) {
    const cabecalhos = await headers();
    const ip =
      cabecalhos.get("x-forwarded-for")?.split(",")[0].trim() ??
      cabecalhos.get("x-real-ip")?.trim() ??
      null;

    const { error } = await admin.from("aceites_termo").insert({
      cedente_id: cedente.id,
      termo_versao: CARTILHA_VERSAO,
      ip,
      user_agent: cabecalhos.get("user-agent"),
    });
    if (error) return { erro: "Não foi possível confirmar. Tente de novo." };
  }

  revalidatePath(`/cedente/${token}`);
  return { erro: null };
}
