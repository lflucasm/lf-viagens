/**
 * Regras da página Saúde — versão enxuta de src/supervisor.py (o supervisor
 * de verdade roda no fim de cada ciclo no Actions e avisa no Telegram; aqui é só
 * o retrato na hora em que alguém abre a página). Mesmas janelas por etapa e
 * mesma regra de cobertura; se mudar lá, mudar aqui.
 */
import type { Database, Json } from "@/lib/database.types";

export type Batimento = Database["public"]["Tables"]["batimentos"]["Row"];
export type Cor = "verde" | "amarelo" | "vermelho" | "cinza";

export type Etapa = {
  etapa: string;
  nome: string;
  cadencia: string;
  /** horas em que precisa ter rodado; null = sob demanda (sem janela) */
  janelaH: number | null;
  /** a janela vale pra última rodada OK (não basta ter rodado) */
  exigeOk: boolean;
};

// Crons conferidos em 26/09/2026 (ver JANELA_ETAPA_H em supervisor.py); desde
// 15/10/2026 ingestao, monitor, filas e malha rodam no ciclo.yml; desde 23/10/2026
// a cada 2h das 07h as 23h e nada de madrugada (disparado pelo vigia do Supabase),
// com o supervisor como ultima etapa. Janelas de 11h cobrem a noite parada
// (ultima rodada ~21h, primeira ~07h) sem ficar vermelho toda manha; o
// supervisor.py fica com 8h/6h porque so roda logo depois de um ciclo.
export const ETAPAS: Etapa[] = [
  { etapa: "ingestao", nome: "Ingestão (Volly → painel)", cadencia: "a cada 2h, 07h–23h (ciclo)", janelaH: 11, exigeOk: true },
  { etapa: "monitor-volly", nome: "Monitor Volly", cadencia: "a cada 2h, 07h–23h (ciclo), todos os vencidos", janelaH: 11, exigeOk: true },
  { etapa: "malha", nome: "Malha (reserva)", cadencia: "2x por dia", janelaH: 20, exigeOk: false },
  { etapa: "portal-latam", nome: "Portal LATAM", cadencia: "07h30 todas, 18h só ≤7 dias", janelaH: 20, exigeOk: false },
  { etapa: "portal-gol", nome: "Portal GOL", cadencia: "07h30 todas, 18h só ≤7 dias", janelaH: 20, exigeOk: false },
  { etapa: "portal-azul", nome: "Portal Azul", cadencia: "1x por dia (07h30)", janelaH: 30, exigeOk: false },
  { etapa: "reconferencia", nome: "Reconferência", cadencia: "sob demanda + fila a cada 2h", janelaH: null, exigeOk: false },
  { etapa: "aplicar-volly", nome: "Aplicar na Volly", cadencia: "sob demanda + fila a cada 2h", janelaH: null, exigeOk: false },
  { etapa: "supervisor", nome: "Supervisor", cadencia: "no fim de cada ciclo", janelaH: 11, exigeOk: true },
];

const TAXA_FALHA_MAX = 0.3;
// Prazo de cobertura = validade da leitura no ritmo de pessoa do monitor
// Volly (4h/10h/16h/30h conforme o embarque, src/ritmo_humano.py, 28/09/2026)
// + folga. Mesma regra de supervisor.prazo_cobertura_h.
const VALIDADE_POR_FAIXA: [number | null, number][] = [
  [24, 4],
  [7 * 24, 10],
  [30 * 24, 16],
  [null, 30],
];
export function prazoCoberturaH(horasAteEmbarque: number): number {
  let validade = 30;
  for (const [limite, horas] of VALIDADE_POR_FAIXA) {
    if (limite === null || horasAteEmbarque <= limite) {
      validade = horas;
      break;
    }
  }
  return validade + Math.max(4, validade * 0.5);
}
// visto_em gravado antes de 26/09/2026 com "-03:00" no runner UTC ficou 3h
// no futuro — mesma tolerância do supervisor.py
const FOLGA_FUTURO_MS = 5 * 60 * 1000;
const DESVIO_BUG_FUSO_MS = 3 * 36e5;

export function objeto(valor: Json | undefined): Record<string, unknown> {
  return valor && typeof valor === "object" && !Array.isArray(valor)
    ? (valor as Record<string, unknown>)
    : {};
}

function ms(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : t;
}

function tolerante(iso: string | null | undefined, agora: number): number | null {
  const t = ms(iso);
  if (t === null) return null;
  return t > agora + FOLGA_FUTURO_MS ? t - DESVIO_BUG_FUSO_MS : t;
}

export type StatusEtapa = {
  etapa: Etapa;
  cor: Cor;
  motivo: string;
  ultima: Batimento | null;
};

/** Rodadas concluídas (ok gravado), da mais nova pra mais velha. */
function concluidas(batimentos: Batimento[], etapa: string): Batimento[] {
  return batimentos
    .filter((b) => b.etapa === etapa && b.ok !== null)
    .sort((a, b) => (ms(b.inicio) ?? 0) - (ms(a.inicio) ?? 0));
}

export function statusEtapa(etapa: Etapa, batimentos: Batimento[], agora: number): StatusEtapa {
  const rodadas = concluidas(batimentos, etapa.etapa);
  const ultima = rodadas[0] ?? null;
  const detalhe = objeto(ultima?.detalhe);

  if (detalhe.erro_login) {
    return { etapa, cor: "vermelho", motivo: "login na Volly falhou", ultima };
  }
  if (etapa.janelaH !== null) {
    const referencia = etapa.exigeOk ? rodadas.find((b) => b.ok) : ultima;
    const quando = ms(referencia?.inicio);
    if (quando === null || agora - quando >= etapa.janelaH * 36e5) {
      return {
        etapa,
        cor: "vermelho",
        motivo: `sem rodada${etapa.exigeOk ? " ok" : ""} nas últimas ${etapa.janelaH}h`,
        ultima,
      };
    }
  } else if (!ultima) {
    return { etapa, cor: "cinza", motivo: "ainda não rodou", ultima };
  }
  if (ultima && ultima.ok === false) {
    return { etapa, cor: "amarelo", motivo: "última rodada quebrou", ultima };
  }
  const falhas = ultima?.falhas ?? 0;
  const total = (ultima?.lidos ?? 0) + falhas;
  if (total > 0 && falhas / total > TAXA_FALHA_MAX) {
    return {
      etapa,
      cor: "amarelo",
      motivo: `${falhas} de ${total} consultas falharam`,
      ultima,
    };
  }
  return { etapa, cor: "verde", motivo: "em dia", ultima };
}

export type VooSaude = Pick<
  Database["public"]["Tables"]["voos"]["Row"],
  "id" | "localizador" | "numero_voo" | "origem" | "destino" | "embarque" | "incompleto" | "passageiros"
>;
export type ObservacaoSaude = { voo_id: string; origem: string; visto_em: string };

export type SemCobertura = {
  voo: VooSaude;
  ultimaLeitura: number | null;
  motivo: string | null;
};

/** Motivo de "sem leitura" da última rodada concluída do monitor Volly. */
function motivosSemLeitura(batimentos: Batimento[]): Map<string, string> {
  const motivos = new Map<string, string>();
  const ultima = concluidas(batimentos, "monitor-volly")[0];
  const lista = objeto(ultima?.detalhe).sem_leitura_lista;
  if (!Array.isArray(lista)) return motivos;
  for (const item of lista as { voo_ids?: string[]; motivo?: string }[]) {
    for (const id of item.voo_ids ?? []) {
      if (item.motivo) motivos.set(id, item.motivo);
    }
  }
  return motivos;
}

/**
 * Voo elegível (ativo, embarque futuro, sem `incompleto`) sem leitura de
 * nenhuma fonte nas últimas 24h — ou 4h se embarca em menos de 24h. Origem
 * `*-plano` (simulação) não conta como leitura.
 */
export function semCobertura(
  voos: VooSaude[],
  observacoes: ObservacaoSaude[],
  batimentos: Batimento[],
  agora: number,
): { elegiveis: number; faltando: SemCobertura[] } {
  const ultima = new Map<string, number>();
  for (const o of observacoes) {
    if (o.origem.endsWith("-plano")) continue;
    const visto = tolerante(o.visto_em, agora);
    if (visto === null) continue;
    if ((ultima.get(o.voo_id) ?? -Infinity) < visto) ultima.set(o.voo_id, visto);
  }
  const motivos = motivosSemLeitura(batimentos);
  let elegiveis = 0;
  const faltando: SemCobertura[] = [];
  for (const voo of voos) {
    const embarque = ms(voo.embarque);
    if (voo.incompleto || embarque === null || embarque <= agora) continue;
    elegiveis++;
    const prazoH = prazoCoberturaH((embarque - agora) / 36e5);
    const visto = ultima.get(voo.id) ?? null;
    if (visto === null || agora - visto >= prazoH * 36e5) {
      faltando.push({ voo, ultimaLeitura: visto, motivo: motivos.get(voo.id) ?? null });
    }
  }
  faltando.sort((a, b) => (a.voo.embarque ?? "").localeCompare(b.voo.embarque ?? ""));
  return { elegiveis, faltando };
}

const FORMATO_BRT = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function horaBrasilia(momento: string | number | null | undefined): string {
  if (momento === null || momento === undefined) return "—";
  const data = new Date(momento);
  return Number.isNaN(data.getTime()) ? "—" : FORMATO_BRT.format(data);
}

export function ha(momento: string | number | null | undefined, agora: number): string {
  const t = typeof momento === "number" ? momento : ms(momento);
  if (t === null) return "nunca";
  const minutos = Math.max(0, Math.floor((agora - t) / 60000));
  if (minutos < 90) return `há ${minutos} min`;
  if (minutos < 48 * 60) return `há ${Math.floor(minutos / 60)}h`;
  return `há ${Math.floor(minutos / (24 * 60))} dias`;
}
