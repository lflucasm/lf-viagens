import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/database.types";

/**
 * Camada de preço da extensão (ver docs/superpowers/specs/
 * 2026-08-30-extensao-preco-milhas-fase1-design.md).
 *
 * O R$/milheiro de cada programa vem da média por faixa do felip-ai
 * (GET /market/internal/price-bands, protegido por X-Internal-Secret). Por cima
 * disso o colaborador pode fixar um override manual e um markup — guardados no
 * Supabase (config_precos_extensao / config_markup_extensao).
 *
 * Estas funções são puras (exceto `buscarFaixas`, que faz o fetch + cache) pra
 * poderem ser testadas isoladas.
 */

type Sb = SupabaseClient<Database>;

// ── Janela de tempo ────────────────────────────────────────────────────────
export type Janela = "24h" | "7d" | "30d";

/**
 * Default `24h` — mesma janela que a tabela de preços do felip-ai ("nosso
 * bot") mostra, pra bater com o que o colaborador já confere lá.
 */
export function parseJanela(raw: string | null | undefined): Janela {
  return raw === "7d" || raw === "30d" ? raw : "24h";
}

/**
 * Ordem de cascata: programas de mercado mais fino (ex.: Azul/TudoAzul) podem
 * não ter nenhuma oferta publicada nas últimas 24h mesmo tendo bastante
 * liquidez na semana — em vez de o voo sair sem preço, alarga a janela.
 */
export const CASCATA_JANELAS: readonly Janela[] = ["24h", "7d", "30d"];

// ── Mapa site da cia → nome do programa no felip-ai ─────────────────────────
export type Cia = "latam" | "azul" | "smiles" | "azpm" | "tap" | "iberia" | "aa" | "copa";

export const MAPA_CIA_PROGRAMA: Record<Cia, string> = {
  latam: "LATAM",
  azul: "AZUL/TUDO AZUL",
  smiles: "SMILES",
  azpm: "AZUL INTERLINE/AZUL PELO MUNDO",
  tap: "TAP",
  iberia: "IBERIA",
  aa: "AA",
  copa: "COPA",
};

export function ehCia(v: unknown): v is Cia {
  return typeof v === "string" && Object.prototype.hasOwnProperty.call(MAPA_CIA_PROGRAMA, v);
}

/**
 * Normaliza nome de programa pra casar. Vários `programName` do felip-ai vêm
 * com um WORD JOINER (U+2060) ou outro zero-width no começo (ex.:
 * <U+2060>"AZUL/TUDO AZUL"), o que quebra a comparação `===` crua.
 */
const ZERO_WIDTH = /[\u200B-\u200D\u2060\uFEFF]/g;

/** Nome do programa sem zero-width nem espa\u00E7o nas pontas (pra exibir). */
export function limparPrograma(s: string): string {
  return s.replace(ZERO_WIDTH, "").trim();
}

/** Nome do programa normalizado pra casar (`===`). */
export function normPrograma(s: string): string {
  return limparPrograma(s).toUpperCase();
}

/**
 * Programas internacionais: a grafia no felip-ai não foi confirmada, então
 * casam por apelido. O felip-ai junta apelidos com "/" ("AZUL/TUDO AZUL"),
 * basta um dos pedaços bater. "AVIOS" fica de fora de propósito: é a moeda de
 * vários programas (British, Qatar), casaria com o programa errado.
 */
const APELIDOS: Record<string, string[]> = {
  TAP: ["TAP", "MILES&GO", "TAP MILES&GO"],
  IBERIA: ["IBERIA", "IBERIA PLUS"],
  AA: ["AA", "AADVANTAGE", "AMERICAN", "AMERICAN AIRLINES"],
  COPA: ["COPA", "COPA AIRLINES", "CONNECTMILES"],
};

/** `nome` (felip-ai ou override salvo) é o programa `programa` do mapa? */
export function mesmoPrograma(nome: string, programa: string): boolean {
  const n = normPrograma(nome);
  const alvo = normPrograma(programa);
  if (n === alvo) return true;
  const apelidos = APELIDOS[alvo];
  return !!apelidos && n.split("/").some((p) => apelidos.includes(p.trim()));
}

// ── Câmbio da taxa de embarque ────────────────────────────────────────────
// As cias internacionais cobram a taxa em USD/EUR. Cache em memória, mesmo
// TTL das faixas; se a cotação falhar, fica a última que veio.
// shortcut: câmbio comercial (venda), sem IOF nem spread do cartão; trocar
// por um fator configurável se a diferença pesar na cotação.
// Estimativa fixa (16/11/2026) usada quando a cotação ao vivo não responde:
// melhor um R$ aproximado do que o voo sem chip. shortcut: números parados no
// tempo, revisar de vez em quando ou trocar por fator configurável.
const CAMBIO_ESTIMADO: Record<string, number> = { USD: 5.8, EUR: 6.4, GBP: 7.6 };
const cambio: { at: number; taxas: Record<string, number> } = { at: 0, taxas: { ...CAMBIO_ESTIMADO } };

type Cotacoes = Record<string, number>;

/** Fonte principal: AwesomeAPI (câmbio comercial, venda). */
async function cotarAwesome(): Promise<Cotacoes> {
  const res = await fetch("https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL,GBP-BRL", {
    signal: AbortSignal.timeout(5_000),
  });
  if (!res.ok) throw new Error(`awesomeapi HTTP ${res.status}`);
  const json = (await res.json()) as Record<string, { code?: string; ask?: string }>;
  const out: Cotacoes = {};
  for (const par of Object.values(json)) {
    const v = Number(par.ask);
    if (par.code && v > 0) out[par.code] = v;
  }
  return out;
}

/** Fontes de reserva: uma chamada em base USD → R$ por USD, EUR e GBP. */
function deBaseUsd(rates: Record<string, number> | undefined): Cotacoes {
  const brl = Number(rates?.BRL);
  if (!(brl > 0)) return {};
  const out: Cotacoes = { USD: brl };
  for (const m of ["EUR", "GBP"]) if (Number(rates?.[m]) > 0) out[m] = brl / Number(rates![m]);
  return out;
}

async function cotarErApi(): Promise<Cotacoes> {
  const res = await fetch("https://open.er-api.com/v6/latest/USD", { signal: AbortSignal.timeout(5_000) });
  if (!res.ok) throw new Error(`er-api HTTP ${res.status}`);
  return deBaseUsd(((await res.json()) as { rates?: Record<string, number> }).rates);
}

async function cotarFrankfurter(): Promise<Cotacoes> {
  const res = await fetch("https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL,EUR,GBP", {
    signal: AbortSignal.timeout(5_000),
  });
  if (!res.ok) throw new Error(`frankfurter HTTP ${res.status}`);
  return deBaseUsd(((await res.json()) as { rates?: Record<string, number> }).rates);
}

/**
 * R$ por unidade de cada moeda estrangeira (`{ USD: 5.4, EUR: 6.1, GBP: 7 }`),
 * sempre com a cotação do dia: tenta AwesomeAPI, depois er-api e frankfurter.
 * Só cai na estimativa fixa se nenhuma responder e nunca houve cotação.
 */
export async function cambioBRL(agora: number = Date.now()): Promise<Record<string, number>> {
  if (agora - cambio.at < TTL_MS) return cambio.taxas;
  for (const fonte of [cotarAwesome, cotarErApi, cotarFrankfurter]) {
    try {
      const taxas = await fonte();
      if (taxas.USD > 0) {
        cambio.at = agora;
        cambio.taxas = { ...CAMBIO_ESTIMADO, ...taxas };
        return cambio.taxas;
      }
    } catch (e) {
      console.warn("[câmbio]", fonte.name, e instanceof Error ? e.message : e);
    }
  }
  return cambio.taxas; // última cotação (ou a estimativa, se nunca houve uma)
}

/** Taxa em BRL, ou `null` quando a moeda não tem cotação (voo sai sem preço). */
export function taxaEmBRL(taxa: number, moeda: string | undefined, taxas: Record<string, number>): number | null {
  if (!moeda || moeda === "BRL") return taxa;
  const c = taxas[moeda];
  return c > 0 ? round2(taxa * c) : null;
}

// ── Shape da resposta do felip-ai ──────────────────────────────────────────
export interface FaixaCelula {
  quantityFloor: number;
  avgPrice: number;
  offerCount: number;
}

export interface FaixaPrograma {
  programId: number;
  programName: string;
  cells: FaixaCelula[];
  overallAvgPrice: number | null;
  totalOfferCount: number;
}

export interface Faixas {
  window: Janela;
  quantityFloors: number[];
  bandStep: number;
  rows: FaixaPrograma[];
}

// ── Cache em memória do processo ───────────────────────────────────────────
// Vive só enquanto a instância serverless está quente; some no cold start. É de
// propósito: 15 min de cache quente cobre a rajada de buscas de uma cotação, e
// o cold start pega dado fresco.
const TTL_MS = 15 * 60_000;
const cache = new Map<Janela, { at: number; data: Faixas }>();

// `Date.now()` fora de teste; injetável só pra teste não depender de relógio.
export async function buscarFaixas(
  janela: Janela,
  agora: number = Date.now(),
): Promise<{ faixas: Faixas | null; stale: boolean }> {
  const quente = cache.get(janela);
  if (quente && agora - quente.at < TTL_MS) return { faixas: quente.data, stale: false };

  const base = process.env.FELIP_AI_URL;
  const secret = process.env.LF_EXT_PRICE_SECRET;
  if (!base || !secret) {
    return quente ? { faixas: quente.data, stale: true } : { faixas: null, stale: true };
  }

  try {
    const res = await fetch(`${base}/market/internal/price-bands?window=${janela}`, {
      headers: { "X-Internal-Secret": secret },
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) throw new Error(`felip-ai HTTP ${res.status}`);
    const json = (await res.json()) as { data?: Faixas };
    if (!json.data?.rows) throw new Error("payload sem rows");
    cache.set(janela, { at: agora, data: json.data });
    return { faixas: json.data, stale: false };
  } catch {
    return quente ? { faixas: quente.data, stale: true } : { faixas: null, stale: true };
  }
}

// só pra teste
export function _limparCacheFaixas(): void {
  cache.clear();
}

// ── Config do Supabase ────────────────────────────────────────────────────
export interface Markup {
  tipo: "pct" | "abs";
  valor: number;
  escopo: "venda" | "pessoa";
}

export const MARKUP_ZERO: Markup = { tipo: "pct", valor: 0, escopo: "venda" };

export interface ConfigPrecos {
  /** programa (nome felip-ai) → R$/milheiro fixado à mão. */
  overrides: Map<string, number>;
  markup: Markup;
}

export async function lerConfig(supabase: Sb): Promise<ConfigPrecos> {
  const [ov, mk] = await Promise.all([
    supabase.from("config_precos_extensao").select("programa, milheiro_manual"),
    supabase.from("config_markup_extensao").select("tipo, valor, escopo").eq("id", true).maybeSingle(),
  ]);

  const overrides = new Map<string, number>();
  for (const row of ov.data ?? []) {
    const v = row.milheiro_manual;
    if (v != null && Number(v) > 0) overrides.set(normPrograma(row.programa), Number(v));
  }

  const markup: Markup = mk.data
    ? {
        tipo: mk.data.tipo === "abs" ? "abs" : "pct",
        valor: Math.max(0, Number(mk.data.valor) || 0),
        escopo: mk.data.escopo === "pessoa" ? "pessoa" : "venda",
      }
    : MARKUP_ZERO;

  return { overrides, markup };
}

// ── Resolução do R$/milheiro ──────────────────────────────────────────────
export type FonteMilheiro = "override" | "faixa" | "geral" | null;

/**
 * Arredonda pro múltiplo de 0,25 mais próximo — o mercado de milhas cota
 * sempre em passos de R$0,25 (é como a tabela do felip-ai mostra), a média
 * bruta de várias ofertas não cai exatamente nesse grid.
 */
function arredondarMilheiro(valor: number): number {
  return Math.round(Math.round(valor / 0.25) * 0.25 * 100) / 100;
}

/**
 * Ordem: override manual (vence tudo) → faixa de 10k que contém `milhas` (se
 * teve oferta) → média geral do programa → nada (voo sai sem preço).
 */
export function resolverMilheiro(
  programa: string,
  milhas: number,
  faixas: Faixas | null,
  config: ConfigPrecos,
): { valor: number | null; fonte: FonteMilheiro } {
  const override = Array.from(config.overrides).find(([nome]) => mesmoPrograma(nome, programa))?.[1];
  if (override != null && override > 0) return { valor: arredondarMilheiro(override), fonte: "override" };

  const row = faixas?.rows.find((r) => mesmoPrograma(r.programName, programa));
  if (row) {
    const step = faixas?.bandStep && faixas.bandStep > 0 ? faixas.bandStep : 10000;
    const piso = Math.floor(milhas / step) * step;
    const cell = row.cells.find((c) => c.quantityFloor === piso && c.offerCount >= 1);
    if (cell && cell.avgPrice > 0) return { valor: arredondarMilheiro(cell.avgPrice), fonte: "faixa" };
    if (row.overallAvgPrice != null && row.overallAvgPrice > 0) {
      return { valor: arredondarMilheiro(row.overallAvgPrice), fonte: "geral" };
    }
  }
  return { valor: null, fonte: null };
}

/** Faixas (+ se vieram de cache velho) de cada janela já buscada. */
export type FaixasPorJanela = Partial<Record<Janela, { faixas: Faixas | null; stale: boolean }>>;

/**
 * Tenta `resolverMilheiro` na janela pedida; se o programa não tiver nenhuma
 * oferta ali (mercado fino — ex.: Azul/TudoAzul sem giro nas últimas 24h),
 * alarga sucessivamente pra 7d e depois 30d antes de desistir.
 */
export function resolverMilheiroCascata(
  programa: string,
  milhas: number,
  faixasPorJanela: FaixasPorJanela,
  janelaInicial: Janela,
  config: ConfigPrecos,
): { valor: number | null; fonte: FonteMilheiro; janelaUsada: Janela | null; stale: boolean } {
  const inicio = CASCATA_JANELAS.indexOf(janelaInicial);
  for (const janela of CASCATA_JANELAS.slice(inicio < 0 ? 0 : inicio)) {
    const entrada = faixasPorJanela[janela];
    const r = resolverMilheiro(programa, milhas, entrada?.faixas ?? null, config);
    if (r.valor != null) return { ...r, janelaUsada: r.fonte === "override" ? null : janela, stale: entrada?.stale ?? false };
  }
  return { valor: null, fonte: null, janelaUsada: null, stale: false };
}

// ── Markup ────────────────────────────────────────────────────────────────
/**
 * Fase 1: escopo sempre "venda" (uma chave = um voo). `pessoa` fica pra quando
 * o carrinho agrupar mais de um pax por chave.
 */
export function aplicarMarkup(custo: number, markup: Markup): number {
  if (markup.valor <= 0) return round2(custo);
  if (markup.tipo === "pct") return round2(custo * (1 + markup.valor / 100));
  return round2(custo + markup.valor);
}

export function custoVoo(milhas: number, milheiro: number, taxa: number): number {
  return round2((milhas / 1000) * milheiro + taxa);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
