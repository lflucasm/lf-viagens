"use server";

import { createAdminClient } from "@/lib/supabase/admin";
import {
  PROGRAMAS,
  cpfValido,
  dataBrParaIso,
  gerarIdentificador,
  gerarTokenAcesso,
  normalizarCpf,
  normalizarTelefone,
} from "@/lib/cedentes";

export type EstadoConvite = {
  erro: string | null;
  /** token do cadastro guiado, quando deu certo */
  token: string | null;
};

function texto(formData: FormData, campo: string, max = 255) {
  const v = String(formData.get(campo) ?? "").trim();
  if (!v) return null;
  return v.length > max ? v.slice(0, max) : v;
}

/**
 * Primeira etapa do cadastro: só o que identifica o titular. A partir daqui
 * o cedente já existe no banco (status "rascunho") e ganha o token_acesso —
 * é o que permite fechar a aba e voltar depois pelo mesmo link de
 * /cedente/[token], em vez de perder tudo se não terminar de uma vez.
 *
 * Roda com service_role porque quem preenche não tem sessão — a autorização
 * é o código, revalidado aqui e não só na página (Server Action é uma rota
 * chamável por qualquer requisição, não só pelo botão que a dispara).
 */
export async function iniciarCadastro(
  _estado: EstadoConvite,
  formData: FormData,
): Promise<EstadoConvite> {
  const codigo = String(formData.get("codigo") ?? "").trim();
  const admin = createAdminClient();

  const { data: convite } = await admin
    .from("convites")
    .select("id, ativo, usos, colaborador_id")
    .ilike("codigo", codigo)
    .maybeSingle();

  if (!convite || !convite.ativo) {
    return { erro: "Este convite não está mais ativo.", token: null };
  }

  const { data: colaborador } = await admin
    .from("perfis")
    .select("ativo")
    .eq("id", convite.colaborador_id)
    .maybeSingle();

  if (!colaborador?.ativo) {
    return { erro: "Este convite não está mais ativo.", token: null };
  }

  const nome = texto(formData, "nome_completo");
  const cpf = normalizarCpf(String(formData.get("cpf") ?? ""));
  const nascimento = dataBrParaIso(String(formData.get("data_nascimento") ?? ""));
  const telefone = normalizarTelefone(String(formData.get("telefone") ?? ""));

  if (!nome || nome.split(/\s+/).length < 2) {
    return { erro: "Escreva seu nome completo, como está no documento.", token: null };
  }
  if (!cpfValido(cpf)) {
    return { erro: "CPF inválido — confira os números.", token: null };
  }
  if (!nascimento) {
    return { erro: "Data de nascimento inválida. Use o formato DD/MM/AAAA.", token: null };
  }
  if (telefone.length < 10) {
    return { erro: "Telefone incompleto — inclua o DDD.", token: null };
  }

  const { data: existente } = await admin
    .from("cedentes")
    .select("id")
    .eq("cpf", cpf)
    .maybeSingle();

  if (existente) {
    return {
      erro:
        "Este CPF já está cadastrado. Se você começou o cadastro e perdeu o link, fale com quem te indicou para reenviar.",
      token: null,
    };
  }

  const token = gerarTokenAcesso();

  const { data: cedente, error } = await admin
    .from("cedentes")
    .insert({
      identificador: gerarIdentificador(nome),
      nome_completo: nome,
      data_nascimento: nascimento,
      cpf,
      telefone,
      status: "rascunho",
      colaborador_id: convite.colaborador_id,
      convite_id: convite.id,
      token_acesso: token,
    })
    .select("id")
    .single();

  if (error || !cedente) {
    return { erro: "Não foi possível concluir o cadastro. Tente de novo.", token: null };
  }

  // As etapas já nascem criadas: é o que a linha do tempo do cadastro
  // guiado desenha, mesmo antes de o titular abrir a primeira aba.
  await admin.from("cedente_contas").insert(
    PROGRAMAS.map((p, i) => ({ cedente_id: cedente.id, programa: p.chave, ordem: i })),
  );

  await admin
    .from("convites")
    .update({ usos: convite.usos + 1, ultimo_uso_em: new Date().toISOString() })
    .eq("id", convite.id);

  return { erro: null, token };
}
