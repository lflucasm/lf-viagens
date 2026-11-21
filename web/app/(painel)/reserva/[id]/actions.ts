"use server";

import { revalidatePath } from "next/cache";
import { after } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { exigirColaborador } from "@/lib/auth";
import { enviarAvisoCliente } from "@/lib/milhasflow";
import { mensagemPassageiro } from "@/lib/tipos";
import {
  dispararChecagemCia,
  dispararChecagemMalha,
  dispararAplicacaoVolly,
  dispararChecagemVolly,
  dispararReconferencia,
  temPortal,
} from "@/lib/github";

export async function marcarResolvido(formData: FormData) {
  await exigirColaborador();

  const historicoId = Number(formData.get("historico_id"));
  const vooId = String(formData.get("voo_id"));
  const resolvido = formData.get("resolvido") === "true";

  const supabase = await createClient();
  const { error } = await supabase.rpc("marcar_historico_resolvido", {
    p_historico_id: historicoId,
    p_resolvido: resolvido,
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/");
  revalidatePath("/urgente");
}

/**
 * "Verificado — passageiro avisado" (substitui o "Marcar resolvido" desde
 * 26/09/2026): grava resolvido + quem/quando verificou (RPC
 * marcar_historico_verificado, verificado_por = auth.uid()) e dispara a
 * reconferência (reconferir.yml), que relê a companhia e grava em
 * propostas_volly o que mudaria no cadastro da Volly — sem escrever nela.
 * O disparo fica num try: GitHub fora do ar não pode desfazer nem travar o
 * "verificado", que é o que a equipe precisa registrar (o supervisor cobra
 * verificado sem proposta em 10 min).
 */
export async function marcarVerificado(formData: FormData) {
  await exigirColaborador();

  const historicoId = Number(formData.get("historico_id"));
  const vooId = String(formData.get("voo_id"));

  const supabase = await createClient();
  const { error } = await supabase.rpc("marcar_historico_verificado", {
    p_historico_id: historicoId,
  });
  if (error) throw new Error(error.message);

  // after(): o botão responde assim que o "verificado" está gravado; a
  // chamada ao GitHub (até alguns segundos) roda depois da resposta.
  after(async () => {
    try {
      const r = await dispararReconferencia(vooId, historicoId);
      if (!r.ok) console.error("Falha ao disparar reconferência:", r.erro);
    } catch (erro) {
      console.error("Falha ao disparar reconferência:", erro);
    }
  });

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/");
  revalidatePath("/urgente");
}

/**
 * "Aplicar na Volly" numa proposta (27/09/2026): registra quem pediu (RPC
 * pedir_aplicacao_volly) e dispara aplicar-volly.yml, que confere de novo e
 * grava no trecho da Volly — ou só simula, enquanto a chave APLICAR_VOLLY do
 * GitHub não estiver "real". Falha do GitHub não desfaz o pedido; o bloco da
 * proposta fica "Aplicando…" e o supervisor cobra.
 */
export async function aplicarNaVolly(formData: FormData) {
  await exigirColaborador();

  const propostaId = Number(formData.get("proposta_id"));
  const vooId = String(formData.get("voo_id"));

  const supabase = await createClient();
  const { error } = await supabase.rpc("pedir_aplicacao_volly", {
    p_proposta_id: propostaId,
  });
  if (error) throw new Error(error.message);

  after(async () => {
    try {
      const r = await dispararAplicacaoVolly(propostaId);
      if (!r.ok) console.error("Falha ao disparar aplicação na Volly:", r.erro);
    } catch (erro) {
      console.error("Falha ao disparar aplicação na Volly:", erro);
    }
  });

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/urgente");
}

/**
 * "Ignorar" um alerta (28/09/2026 — a verificação é opcional): tira o alerta
 * da aba Urgente registrando quem ignorou e quando, SEM reconferir e sem
 * proposta pra Volly (RPC ignorar_historico).
 */
export async function ignorarAlerta(formData: FormData) {
  await exigirColaborador();

  const historicoId = Number(formData.get("historico_id"));
  const vooId = String(formData.get("voo_id"));

  const supabase = await createClient();
  const { error } = await supabase.rpc("ignorar_historico", { p_historico_id: historicoId });
  if (error) throw new Error(error.message);

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/");
  revalidatePath("/urgente");
}

/**
 * "Enviar aviso ao cliente" (20/11/2026): manda a mensagem pronta do alerta
 * pro WhatsApp do cliente da venda, via fila da Volly
 * (lib/milhasflow.enviarAvisoCliente), e marca o alerta como verificado.
 * O texto é montado de novo aqui, nunca o que veio do navegador. Devolve
 * erro em vez de lançar, pro card mostrar o motivo (ex.: sem telefone).
 */
export async function enviarAvisoAoCliente(
  _anterior: { erro?: string } | null,
  formData: FormData,
): Promise<{ erro?: string } | null> {
  await exigirColaborador();
  const historicoId = Number(formData.get("historico_id"));
  const vooId = String(formData.get("voo_id"));

  const supabase = await createClient();
  const [{ data: h }, { data: voo }] = await Promise.all([
    supabase.from("historico").select("campo, valor_novo, resolvido, aviso_enviado_em").eq("id", historicoId).maybeSingle(),
    supabase.from("voos").select("*").eq("id", vooId).maybeSingle(),
  ]);
  if (!h || !voo) return { erro: "Alerta ou voo não encontrado." };
  if (h.resolvido || h.aviso_enviado_em) return { erro: "Esse alerta já foi resolvido." };
  if (!voo.emissao_id) return { erro: "Voo sem emissão na Volly." };
  const mensagem = mensagemPassageiro(h.campo, (h.valor_novo ?? "").trim(), voo);
  if (!mensagem) return { erro: "Esse tipo de alerta não tem aviso pronto." };

  const envio = await enviarAvisoCliente(voo.emissao_id, mensagem);
  if (!envio.ok) return { erro: envio.detalhe };

  const { error } = await supabase.rpc("registrar_aviso_cliente", {
    p_historico_id: historicoId,
    p_volly_id: envio.id,
  });
  // a mensagem já saiu: falha aqui só perde o rastro, não pode virar reenvio
  if (error) console.error("Aviso enviado mas não registrado:", historicoId, error.message);

  after(async () => {
    try {
      const r = await dispararReconferencia(vooId, historicoId);
      if (!r.ok) console.error("Falha ao disparar reconferência:", r.erro);
    } catch (erro) {
      console.error("Falha ao disparar reconferência:", erro);
    }
  });

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/");
  revalidatePath("/urgente");
  return null;
}

/**
 * "Adiar" um alerta (19/11/2026, ideia da Traveos): some da aba Urgente por
 * `horas` e volta sozinho, sem resolver (RPC adiar_historico grava
 * adiado_ate/adiado_por). Telegram e supervisor não mudam.
 */
export async function adiarAlerta(formData: FormData) {
  await exigirColaborador();

  const historicoId = Number(formData.get("historico_id"));
  const vooId = String(formData.get("voo_id"));
  const horas = Number(formData.get("horas") ?? 24);

  const supabase = await createClient();
  const { error } = await supabase.rpc("adiar_historico", {
    p_historico_id: historicoId,
    p_horas: horas,
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/urgente");
}

/**
 * "Ignorar proposta" (28/09/2026 — aplicar na Volly é opcional): a proposta
 * vira `descartada` com quem/quando e sai da fila; nada é gravado na Volly.
 */
export async function ignorarProposta(formData: FormData) {
  await exigirColaborador();

  const propostaId = Number(formData.get("proposta_id"));
  const vooId = String(formData.get("voo_id"));

  const supabase = await createClient();
  const { error } = await supabase.rpc("descartar_proposta_volly", { p_proposta_id: propostaId });
  if (error) throw new Error(error.message);

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/urgente");
}

export async function atribuir(formData: FormData) {
  await exigirColaborador();

  const historicoId = Number(formData.get("historico_id"));
  const vooId = String(formData.get("voo_id"));
  const atendenteIdBruto = String(formData.get("atendente_id") ?? "");
  const atendenteId = atendenteIdBruto === "" ? null : atendenteIdBruto;

  const supabase = await createClient();
  const { error } = await supabase.rpc("atribuir_historico", {
    p_historico_id: historicoId,
    // o parâmetro aceita NULL no Postgres (desatribuir); o gerador de tipos
    // do Supabase não expressa isso e tipa como string não-nula
    p_atendente_id: atendenteId as string,
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/reserva/${vooId}`);
  revalidatePath("/");
}

export async function adicionarNota(formData: FormData) {
  const { perfil } = await exigirColaborador();

  const vooId = String(formData.get("voo_id"));
  const texto = String(formData.get("texto") ?? "").trim();
  if (!texto) return;

  const supabase = await createClient();
  const { error } = await supabase.from("notas").insert({
    voo_id: vooId,
    autor_id: perfil.id,
    texto,
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/reserva/${vooId}`);
}

/**
 * "Checar agora": pede uma checagem individual pra essa reserva, 100% na
 * nuvem (GitHub Actions, workflow_dispatch com o localizador): monitor
 * Volly sempre, mais o portal da companhia (LATAM/GOL/Azul) ou, pra
 * companhia sem portal na nuvem, a malha. Não usa mais a fila do Mac
 * (solicitacoes_checagem) - desde 26/09/2026 nada depende do Mac ligado.
 * Não afirma qual trecho vai mudar - só pede pra conferir de novo, igual o
 * resto do sistema.
 */
export async function checarAgora(formData: FormData) {
  await exigirColaborador();

  const localizador = String(formData.get("localizador") ?? "").trim();
  const cia = String(formData.get("cia") ?? "");
  if (!localizador) return;

  // paralelo: os disparos são chamadas HTTP independentes, sem ordem entre
  // si. allSettled, não all: dispararWorkflow não trata erro de rede do
  // fetch, e uma fonte que falha de disparar não pode impedir as outras.
  // Roda depois da resposta (after): o resultado só vai pro log, então o
  // botão não precisa esperar o GitHub.
  after(async () => {
    const disparos: [string, Promise<{ ok: boolean; erro?: string }>][] = [
      ["monitor Volly", dispararChecagemVolly(localizador)],
      temPortal(cia)
        ? [`portal ${cia}`, dispararChecagemCia(cia, localizador)]
        : ["malha", dispararChecagemMalha(localizador)],
    ];
    const resultados = await Promise.allSettled(disparos.map(([, p]) => p));
    resultados.forEach((r, i) => {
      if (r.status === "rejected") {
        console.error(`Falha ao disparar checagem (${disparos[i][0]}):`, r.reason);
      } else if (!r.value.ok) {
        console.error(`Falha ao disparar checagem (${disparos[i][0]}):`, r.value.erro);
      }
    });
  });
}
