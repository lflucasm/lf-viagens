import { exigirColaboradorPorToken } from "../_auth";
import {
  aplicarMarkup,
  buscarFaixas,
  cambioBRL,
  CASCATA_JANELAS,
  custoVoo,
  ehCia,
  lerConfig,
  MAPA_CIA_PROGRAMA,
  parseJanela,
  resolverMilheiroCascata,
  taxaEmBRL,
  type FaixasPorJanela,
  type Janela,
  type Faixas,
} from "../_precos";
import { PARSERS_RESULTADOS, type VooExtraido } from "../_parsers/resultados";

/**
 * POST /api/extensao/precificar
 * body: { cia: 'latam'|'azul'|'smiles'|'azpm'|'tap'|'iberia'|'aa'|'copa', modo?: 'resultados'|'carrinho',
 *         payload: <json cru da cia>, window?: '24h'|'7d'|'30d' }
 *
 * Parseia o payload da cia, resolve o R$/milheiro (override → faixa → média
 * geral) e devolve o custo e o preço com markup de cada voo. `stale: true` = a
 * média de mercado veio de cache velho (felip-ai não respondeu).
 */
export async function POST(req: Request) {
  const { erro, supabase } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const body = (await req.json().catch(() => null)) as {
    cia?: string;
    modo?: string;
    payload?: unknown;
    window?: string;
  } | null;

  if (!body || !ehCia(body.cia)) {
    return Response.json({ error: "cia inválida" }, { status: 400 });
  }

  const cia = body.cia;
  const programa = MAPA_CIA_PROGRAMA[cia];
  const modo = body.modo === "carrinho" ? "carrinho" : "resultados";

  let voos: VooExtraido[];
  if (modo === "carrinho") {
    // No carrinho o content script já leu milhas + taxa do DOM e manda a lista
    // pronta — aqui só resolvemos o R$. `payload` = { voos: [...] }.
    // A taxa pode vir em USD/EUR (cias internacionais): vira BRL aqui; sem
    // cotação ao vivo, `cambioBRL` cai numa estimativa fixa (voo sem chip é pior).
    const lidos = normalizarCarrinho(body.payload);
    const taxas = lidos.some((v) => v.moeda && v.moeda !== "BRL") ? await cambioBRL() : {};
    voos = [];
    for (const v of lidos) {
      const taxa = taxaEmBRL(v.taxa, v.moeda, taxas);
      if (taxa != null) voos.push({ ...v, taxa });
    }
  } else {
    try {
      voos = PARSERS_RESULTADOS[cia](body.payload);
    } catch {
      voos = [];
    }
  }

  const janela = parseJanela(body.window);
  // Alarga a janela em cascata (24h → 7d → 30d) por voo: um programa de
  // mercado fino (ex.: Azul/TudoAzul) pode não ter oferta nenhuma nas últimas
  // 24h e ainda assim ter preço confiável na semana.
  const janelasNecessarias = CASCATA_JANELAS.slice(Math.max(0, CASCATA_JANELAS.indexOf(janela)));
  const [entradas, config] = await Promise.all([
    Promise.all(
      janelasNecessarias.map(
        async (j): Promise<[Janela, { faixas: Faixas | null; stale: boolean }]> => [j, await buscarFaixas(j)],
      ),
    ),
    lerConfig(supabase),
  ]);
  const faixasPorJanela: FaixasPorJanela = Object.fromEntries(entradas);
  const stale = entradas[0]?.[1].stale ?? true;

  const resultado = voos.map((v) => {
    const { valor: milheiro, fonte, janelaUsada } = resolverMilheiroCascata(
      programa,
      v.milhas,
      faixasPorJanela,
      janela,
      config,
    );
    const custoRS = milheiro != null ? custoVoo(v.milhas, milheiro, v.taxa) : null;
    const precoComMarkup = custoRS != null ? aplicarMarkup(custoRS, config.markup) : null;
    // Azul com titular na reserva: os pontos caem (desconto do titular) e
    // podem cair noutra faixa de milheiro — resolve de novo pra essa milhagem.
    const titular = v.milhasTitular
      ? resolverMilheiroCascata(programa, v.milhasTitular, faixasPorJanela, janela, config).valor
      : null;
    const custoTitular = titular != null && v.milhasTitular ? custoVoo(v.milhasTitular, titular, v.taxa) : null;
    return {
      chave: v.chave,
      origem: v.origem,
      destino: v.destino,
      dataIda: v.dataIda,
      horaPartida: v.horaPartida,
      horaChegada: v.horaChegada,
      milhas: v.milhas,
      taxa: v.taxa,
      escalas: v.escalas,
      milheiroUsado: milheiro,
      fonteMilheiro: fonte,
      // janela de onde saiu o milheiro usado — só difere de `janela` quando a
      // cascata precisou alargar (ex.: pediu 24h, achou só em 7d).
      janelaMilheiro: janelaUsada,
      custoRS,
      precoComMarkup,
      milhasTitular: v.milhasTitular ?? null,
      milheiroTitular: titular,
      custoTitular,
      precoComMarkupTitular: custoTitular != null ? aplicarMarkup(custoTitular, config.markup) : null,
    };
  });

  return Response.json({ cia, programa, janela, modo, stale, markup: config.markup, voos: resultado });
}

/** Lista de voos que o content script do carrinho já extraiu do DOM. */
function normalizarCarrinho(payload: unknown): VooExtraido[] {
  const p = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  const lista = Array.isArray(p.voos) ? p.voos : [];
  const out: VooExtraido[] = [];
  for (const item of lista) {
    const v = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
    const origem = String(v.origem ?? "");
    const destino = String(v.destino ?? "");
    const horaPartida = String(v.horaPartida ?? "");
    const milhas = Number(v.milhas) || 0;
    if (!origem || !destino || !(milhas > 0)) continue;
    out.push({
      chave: String(v.chave ?? `${origem}-${destino}-${horaPartida.replace(/\D/g, "")}`),
      origem,
      destino,
      dataIda: String(v.dataIda ?? ""),
      horaPartida,
      horaChegada: String(v.horaChegada ?? ""),
      milhas,
      taxa: Number(v.taxa) || 0,
      moeda: typeof v.moeda === "string" ? v.moeda.toUpperCase() : undefined,
      escalas: Number(v.escalas) || 0,
    });
  }
  return out;
}
