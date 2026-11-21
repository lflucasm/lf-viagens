"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createAdminClient } from "@/lib/supabase/admin";
import { exigirAdmin, exigirColaborador } from "@/lib/auth";
import {
  PIX_TIPOS,
  PROGRAMAS,
  cpfValido,
  dataBrParaIso,
  gerarCodigoConvite,
  normalizarCpf,
  normalizarTelefone,
  type PixTipo,
  type Programa,
} from "@/lib/cedentes";
import { enviarConta } from "@/lib/milhasflow";
import { decifrar } from "@/lib/cripto";
import { salvarContaCedente } from "@/lib/contasCedente";

/**
 * Cria o código de convite do colaborador que está logado, se ele ainda não
 * tem. Vai por service_role porque convites não tem policy de insert pra
 * authenticated — a autorização é o exigirColaborador() aqui, e o código
 * sempre sai amarrado ao próprio auth.uid(), nunca ao id que vier do form.
 */
export async function gerarMeuConvite() {
  const { perfil } = await exigirColaborador();
  const admin = createAdminClient();

  const { data: existente } = await admin
    .from("convites")
    .select("id")
    .eq("colaborador_id", perfil.id)
    .maybeSingle();

  if (!existente) {
    // Colisão de nome entre colaboradores é improvável, mas o unique é quem
    // decide: tenta sufixos numéricos antes de desistir, em vez de estourar
    // na cara do usuário.
    for (let tentativa = 0; tentativa < 5; tentativa += 1) {
      const { error } = await admin
        .from("convites")
        .insert({ colaborador_id: perfil.id, codigo: gerarCodigoConvite(perfil.nome, tentativa) });
      if (!error) break;
      if (tentativa === 4) throw new Error(error.message);
    }
  }

  revalidatePath("/cedentes");
}

export async function alternarConvite(formData: FormData) {
  await exigirAdmin();

  const conviteId = String(formData.get("convite_id"));
  const ativo = formData.get("ativo") === "true";

  const admin = createAdminClient();
  const { error } = await admin.from("convites").update({ ativo }).eq("id", conviteId);
  if (error) throw new Error(error.message);

  revalidatePath("/cedentes");
}

type ClienteAdmin = ReturnType<typeof createAdminClient>;

const PONTOS_POR_PROGRAMA: Partial<Record<Programa, "pontos_latam" | "pontos_smiles" | "pontos_livelo" | "pontos_esfera">> = {
  latam: "pontos_latam",
  smiles: "pontos_smiles",
  livelo: "pontos_livelo",
  esfera: "pontos_esfera",
};

/**
 * Manda pro MilhasFlow cada conta do cedente que já foi criada (status
 * "concluida", com login e senha) e ainda não subiu. O MilhasFlow guarda uma
 * linha por conta de programa — ver lib/milhasflow.ts — então o envio e o
 * rastro de "já subiu" são por conta (cedente_contas), não por cedente.
 *
 * Nunca estoura: aprovação e envio são coisas separadas, e uma falha no CRM
 * de terceiros não pode desfazer a aprovação que o admin acabou de dar. Uma
 * conta que falha não impede as outras de subir — cada erro fica gravado na
 * própria linha, pra aparecer no painel e poder ser reenviada sozinha.
 */
async function enviarParaCrm(admin: ClienteAdmin, cedenteId: string) {
  const { data: cedente } = await admin
    .from("cedentes")
    .select("*")
    .eq("id", cedenteId)
    .maybeSingle();

  if (!cedente) return;

  const [{ data: contas }, { data: credenciais }] = await Promise.all([
    admin
      .from("cedente_contas")
      .select("*")
      .eq("cedente_id", cedenteId)
      .eq("status", "concluida")
      .is("milhasflow_enviado_em", null)
      .in("programa", PROGRAMAS.filter((p) => p.chave !== "email").map((p) => p.chave)),
    admin.from("cedente_credenciais").select("programa, campo, valor_cifrado").eq("cedente_id", cedenteId),
  ]);

  for (const conta of contas ?? []) {
    const senhaCifrada =
      credenciais?.find((c) => c.programa === conta.programa && c.campo === "senha")?.valor_cifrado ??
      null;

    if (!senhaCifrada) {
      await admin
        .from("cedente_contas")
        .update({ milhasflow_erro: "Sem senha guardada para esta conta." })
        .eq("id", conta.id);
      continue;
    }

    let resultado;
    try {
      const campoPontos = PONTOS_POR_PROGRAMA[conta.programa as Programa];
      resultado = await enviarConta({
        nomeCompleto: cedente.nome_completo,
        cpf: cedente.cpf,
        dataNascimentoIso: cedente.data_nascimento ?? "",
        emailCriado: cedente.email_criado,
        telefone: cedente.telefone,
        programa: conta.programa as Programa,
        senha: decifrar(senhaCifrada),
        pontosIniciais: campoPontos ? (cedente[campoPontos] ?? 0) : 0,
      });
    } catch (e) {
      resultado = {
        ok: false as const,
        motivo: "falha" as const,
        detalhe: e instanceof Error ? e.message : String(e),
      };
    }

    await admin
      .from("cedente_contas")
      .update(
        resultado.ok
          ? {
              milhasflow_id: resultado.id,
              milhasflow_enviado_em: new Date().toISOString(),
              milhasflow_erro: null,
            }
          : { milhasflow_erro: resultado.detalhe },
      )
      .eq("id", conta.id);
  }
}

export async function aprovarCedente(formData: FormData) {
  const { perfil } = await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { error } = await admin
    .from("cedentes")
    .update({
      status: "aprovado",
      revisado_por: perfil.id,
      revisado_em: new Date().toISOString(),
      atualizado_em: new Date().toISOString(),
    })
    .eq("id", cedenteId);

  if (error) throw new Error(error.message);

  await enviarParaCrm(admin, cedenteId);

  revalidatePath("/cedentes");
  revalidatePath(`/cedentes/${cedenteId}`);
}

export async function rejeitarCedente(formData: FormData) {
  const { perfil } = await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { error } = await admin
    .from("cedentes")
    .update({
      status: "rejeitado",
      revisado_por: perfil.id,
      revisado_em: new Date().toISOString(),
      atualizado_em: new Date().toISOString(),
    })
    .eq("id", cedenteId);

  if (error) throw new Error(error.message);

  revalidatePath("/cedentes");
  revalidatePath(`/cedentes/${cedenteId}`);
}

/**
 * Reabre um cedente rejeitado para análise, voltando o status pra "pendente"
 * — sem isso a rejeição era definitiva, mas às vezes o titular corrige o que
 * faltava e precisa ser reavaliado. Os dados da revisão anterior são
 * limpos: a tela de "pendente" some com o rótulo de quem revisou, e o
 * aprovar/rejeitar seguinte grava um novo revisado_por/revisado_em.
 */
export async function reabrirAnaliseCedente(formData: FormData) {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { error } = await admin
    .from("cedentes")
    .update({
      status: "pendente",
      revisado_por: null,
      revisado_em: null,
      atualizado_em: new Date().toISOString(),
    })
    .eq("id", cedenteId);

  if (error) throw new Error(error.message);

  revalidatePath("/cedentes");
  revalidatePath(`/cedentes/${cedenteId}`);
}

/** Reenvia um cedente já aprovado que não subiu na primeira tentativa. */
export async function reenviarParaCrm(formData: FormData) {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { data: cedente } = await admin
    .from("cedentes")
    .select("status")
    .eq("id", cedenteId)
    .maybeSingle();

  if (cedente?.status !== "aprovado") return;

  await enviarParaCrm(admin, cedenteId);

  revalidatePath(`/cedentes/${cedenteId}`);
}

export type EstadoCredenciais = {
  erro: string | null;
  valores: Array<{ programa: string; campo: string; valor: string }> | null;
};

/**
 * Decifra e devolve as credenciais de um cedente. Só admin, e por action —
 * nunca renderizada junto da página: quem abre a ficha de um cedente não
 * deveria ter as senhas dele no HTML sem ter pedido.
 */
export async function revelarCredenciais(
  _estado: EstadoCredenciais,
  formData: FormData,
): Promise<EstadoCredenciais> {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { data: linhas } = await admin
    .from("cedente_credenciais")
    .select("programa, campo, valor_cifrado")
    .eq("cedente_id", cedenteId)
    .order("programa");

  if (!linhas || linhas.length === 0) {
    return { erro: "Nenhuma credencial guardada ainda.", valores: null };
  }

  try {
    return {
      erro: null,
      valores: linhas.map((l) => ({
        programa: l.programa,
        campo: l.campo,
        valor: decifrar(l.valor_cifrado),
      })),
    };
  } catch (e) {
    return {
      erro: e instanceof Error ? e.message : "Não foi possível decifrar as credenciais.",
      valores: null,
    };
  }
}

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

export type EstadoEdicaoCedente = { erro: string | null };

/**
 * Edição completa do cadastro pelo painel — só admin, por lidar com CPF,
 * PIX e pontos. Mesma validação da Fase 1 pública (lib/cedentes.ts), porque
 * é o mesmo dado, só que agora corrigido por quem trabalha na agência em
 * vez de digitado pelo próprio titular.
 */
export async function atualizarCedente(
  _estado: EstadoEdicaoCedente,
  formData: FormData,
): Promise<EstadoEdicaoCedente> {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id") ?? "");
  const admin = createAdminClient();

  const nome = texto(formData, "nome_completo");
  const cpf = normalizarCpf(String(formData.get("cpf") ?? ""));
  const nascimento = dataBrParaIso(String(formData.get("data_nascimento") ?? ""));
  const telefone = normalizarTelefone(String(formData.get("telefone") ?? ""));
  const pixTipo = String(formData.get("pix_tipo") ?? "") as PixTipo;
  const chavePix = texto(formData, "chave_pix");
  const banco = texto(formData, "banco", 120);

  if (!nome || nome.split(/\s+/).length < 2) {
    return { erro: "Escreva o nome completo do titular." };
  }
  if (!cpfValido(cpf)) {
    return { erro: "CPF inválido — confira os números." };
  }
  if (!nascimento) {
    return { erro: "Data de nascimento inválida. Use o formato DD/MM/AAAA." };
  }
  if (telefone.length < 10) {
    return { erro: "Telefone incompleto — inclua o DDD." };
  }
  if (chavePix && !PIX_TIPOS.includes(pixTipo)) {
    return { erro: "Tipo de chave PIX inválido." };
  }

  const { data: duplicado } = await admin
    .from("cedentes")
    .select("id")
    .eq("cpf", cpf)
    .neq("id", cedenteId)
    .maybeSingle();

  if (duplicado) {
    return { erro: "Já existe outro cedente com este CPF." };
  }

  const { error } = await admin
    .from("cedentes")
    .update({
      nome_completo: nome,
      cpf,
      data_nascimento: nascimento,
      telefone,
      banco,
      pix_tipo: chavePix ? pixTipo : null,
      chave_pix: chavePix,
      pontos_latam: inteiro(formData, "pontos_latam"),
      pontos_smiles: inteiro(formData, "pontos_smiles"),
      pontos_livelo: inteiro(formData, "pontos_livelo"),
      pontos_esfera: inteiro(formData, "pontos_esfera"),
      atualizado_em: new Date().toISOString(),
    })
    .eq("id", cedenteId);

  if (error) return { erro: "Não foi possível salvar. Tente de novo." };

  revalidatePath("/cedentes");
  revalidatePath(`/cedentes/${cedenteId}`);
  redirect(`/cedentes/${cedenteId}`);
}

/**
 * "Excluir" um cadastro é inativar, não apagar — mesmo padrão de
 * perfis.ativo/convites.ativo. Mantém o histórico (aceites, contas já
 * criadas) em vez de perder tudo, e dá pra reverter com reativarCedente.
 */
export async function inativarCedente(formData: FormData) {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { error } = await admin
    .from("cedentes")
    .update({ ativo: false, atualizado_em: new Date().toISOString() })
    .eq("id", cedenteId);

  if (error) throw new Error(error.message);

  revalidatePath("/cedentes");
  revalidatePath(`/cedentes/${cedenteId}`);
}

export async function reativarCedente(formData: FormData) {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id"));
  const admin = createAdminClient();

  const { error } = await admin
    .from("cedentes")
    .update({ ativo: true, atualizado_em: new Date().toISOString() })
    .eq("id", cedenteId);

  if (error) throw new Error(error.message);

  revalidatePath("/cedentes");
  revalidatePath(`/cedentes/${cedenteId}`);
}

export type EstadoContaAdmin = { erro: string | null; sucesso: string | null };

/**
 * Edita login/senha/observação de uma conta de programa pelo painel — pra
 * quando o titular passa a senha errada, troca a senha por fora, ou algo
 * precisa ser corrigido sem depender dele abrir o link de novo. Mesma regra
 * do cadastro guiado (lib/contasCedente.ts): senha em branco mantém a que
 * já tava salva.
 */
export async function atualizarContaCedente(
  _estado: EstadoContaAdmin,
  formData: FormData,
): Promise<EstadoContaAdmin> {
  await exigirAdmin();

  const cedenteId = String(formData.get("cedente_id") ?? "");
  const programa = String(formData.get("programa") ?? "") as Programa;

  if (!cedenteId || !PROGRAMAS.some((p) => p.chave === programa)) {
    return { erro: "Conta inválida.", sucesso: null };
  }

  const admin = createAdminClient();
  const login = String(formData.get("login") ?? "").trim();
  const senha = String(formData.get("senha") ?? "");
  const observacao = String(formData.get("observacao") ?? "").trim() || null;

  const { erro } = await salvarContaCedente(admin, cedenteId, programa, {
    login,
    senha,
    observacao,
  });
  if (erro) return { erro, sucesso: null };

  revalidatePath(`/cedentes/${cedenteId}`);
  revalidatePath(`/cedentes/${cedenteId}/editar`);
  return { erro: null, sucesso: "Salvo." };
}
