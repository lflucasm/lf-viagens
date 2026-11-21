import { carregarLinhasVoos } from "@/lib/painel";
import { ORDEM_PRIORIDADE } from "@/lib/prioridade";
import { createClient } from "@/lib/supabase/server";
import { descreverAlerta, ROTULO_TIPO } from "@/lib/tipos";
import { CardAlerta } from "@/components/CardAlerta";
import { BotaoEnviar } from "@/components/BotaoEnviar";
import { PropostaVolly } from "@/components/PropostaVolly";
import { liberarAlertasSegurados } from "./actions";

function horaBrasilia(iso: string | null): string {
  if (!iso) return "?";
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Linha `telegram_segurado` (gravada por src/nuvem_comum.enviar_alertas
 * quando uma rodada passa do teto) e a última liberação pedida no site.
 * O botão só aparece com o segurado aberto.
 */
async function carregarSegurado() {
  const supabase = await createClient();
  const { data } = await supabase
    .from("supervisor_estado")
    .select("chave, aberto_em, avisado_em, detalhe")
    .in("chave", ["telegram_segurado", "telegram_liberado"]);
  const segurado = data?.find((l) => l.chave === "telegram_segurado") ?? null;
  const liberado = data?.find((l) => l.chave === "telegram_liberado") ?? null;
  if (!segurado) return null;

  const detalhe = (segurado.detalhe ?? {}) as { quantidades?: Record<string, number> };
  const quantidade = Object.values(detalhe.quantidades ?? {}).reduce((a, b) => a + b, 0);
  const referencia = segurado.avisado_em ?? segurado.aberto_em;
  const liberacaoPedida =
    !!liberado?.aberto_em && !!referencia && liberado.aberto_em > referencia;
  return { desde: segurado.aberto_em, quantidade, liberacaoPedida };
}

/**
 * Propostas de atualização da Volly esperando alguém clicar "Aplicar na
 * Volly" (27/09/2026). Sem isto o botão só existia dentro da página da
 * reserva — e a reserva sai desta aba assim que alguém clica "Verificado",
 * justo o momento em que a proposta chega.
 */
async function carregarPropostasPendentes() {
  const supabase = await createClient();
  const { data } = await supabase
    .from("propostas_volly")
    .select("id, voo_id, status, mensagem, criado_em, pedido_em, resultado, voos(localizador, embarque, passageiros)")
    .eq("status", "proposta")
    .order("criado_em", { ascending: false });
  return (data ?? []).map((p) => {
    const resultado = (p.resultado ?? {}) as { em?: string; simulado?: boolean; erro?: string };
    const aplicando = !!p.pedido_em && (!resultado.em || p.pedido_em > resultado.em);
    return { ...p, resultado, aplicando };
  });
}

export default async function PaginaUrgente() {
  const [{ linhas }, segurado, propostas] = await Promise.all([
    carregarLinhasVoos(),
    carregarSegurado(),
    carregarPropostasPendentes(),
  ]);

  const comAlerta = linhas
    .filter((l) => l.pendente && l.prioridade !== "passado")
    .sort(
      (a, b) =>
        ORDEM_PRIORIDADE[a.prioridade] - ORDEM_PRIORIDADE[b.prioridade] ||
        (a.voo.embarque ?? "").localeCompare(b.voo.embarque ?? ""),
    );
  // "Adiar 24h" no card tira da lista sem resolver; volta sozinho
  const urgentes = comAlerta.filter((l) => !l.adiadoAte);
  const adiados = comAlerta.filter((l) => l.adiadoAte);

  // quantos de cada tipo, com o rótulo legível ("Horário da venda não bate
  // com a companhia · 16") em vez do código gravado no histórico
  const porTipo = new Map<string, number>();
  for (const l of urgentes) {
    if (!l.pendente) continue;
    // pelo tipo, não pelo título: "Horário mudou: 07:10 → 08:40" muda a
    // cada alerta e quebraria a contagem
    const titulo =
      (l.pendente.campo && ROTULO_TIPO[l.pendente.campo]) || descreverAlerta(l.pendente).titulo;
    porTipo.set(titulo, (porTipo.get(titulo) ?? 0) + 1);
  }
  const resumo = [...porTipo.entries()].sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Urgente</h1>
        <p className="text-sm text-gray-500">
          {urgentes.length} reserva(s) com alteração detectada e ainda não resolvida.
        </p>
      </div>

      {segurado && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-atencao/30 bg-atencao/10 px-4 py-3 text-sm text-gray-800">
          <p>
            <strong className="font-semibold text-atencao">Telegram segurado</strong> desde{" "}
            {horaBrasilia(segurado.desde)}
            {segurado.quantidade > 0 && <> ({segurado.quantidade} alertas de uma vez)</>}. Os
            alertas estão aqui na lista e saem sozinhos em 24h.
            {segurado.liberacaoPedida && (
              <> Liberação pedida: sai na próxima rodada dos checadores.</>
            )}
          </p>
          {!segurado.liberacaoPedida && (
            <form action={liberarAlertasSegurados}>
              <BotaoEnviar variante="principal" tamanho="sm" pendente="Liberando…">
                Liberar alertas segurados
              </BotaoEnviar>
            </form>
          )}
        </div>
      )}

      {propostas.length > 0 && (
        <section className="space-y-2">
          <h2 className="flex items-baseline gap-2 text-base font-semibold">
            Propostas para aplicar na Volly
            <span className="rounded-full bg-gold-500/15 px-2 py-0.5 font-sans text-xs font-semibold text-gold-600">
              {propostas.length}
            </span>
          </h2>
          <ul className="grid gap-2 lg:grid-cols-2">
            {propostas.map((p) => (
              <li key={p.id}>
                <PropostaVolly
                  proposta={p}
                  passageiros={p.voos?.passageiros}
                  aplicando={p.aplicando}
                  linkReserva
                  detalhe={<>Proposta de {horaBrasilia(p.criado_em)}</>}
                  aviso={
                    p.resultado.erro
                      ? `Última tentativa não aplicou: ${p.resultado.erro}`
                      : p.resultado.simulado && p.resultado.em
                        ? `Simulada em ${horaBrasilia(p.resultado.em)} (gravação real desligada)`
                        : null
                  }
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {resumo.length > 0 && (
        <ul className="flex flex-wrap gap-2 text-xs">
          {resumo.map(([titulo, qtd]) => (
            <li key={titulo} className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white/90 py-1 pl-3 pr-1 text-gray-700">
              {titulo}
              <span className="rounded-full bg-gray-100 px-1.5 font-semibold tabular-nums text-gray-900">{qtd}</span>
            </li>
          ))}
        </ul>
      )}

      {urgentes.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white/90 p-6 text-center text-sm text-gray-500">
          Nenhum alerta pendente.
        </div>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {urgentes.map((l) => (
            <li key={l.voo.id}>
              <CardAlerta linha={l} />
            </li>
          ))}
        </ul>
      )}

      {adiados.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-gray-600">
            Adiados ({adiados.length}) · voltam sozinhos para a lista
          </summary>
          <ul className="mt-3 grid gap-3 lg:grid-cols-2">
            {adiados.map((l) => (
              <li key={l.voo.id}>
                <CardAlerta linha={l} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
