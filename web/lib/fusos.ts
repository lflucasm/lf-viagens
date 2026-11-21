/**
 * Porta de src/fusos.py — o banco grava UTC, cada aeroporto mostra a hora
 * local. Sem isso, todo horário de embarque/chegada aparece com o fuso
 * errado (o Brasil fica 3h atrás de UTC).
 */

// Mesmo mapa fixo de src/fusos.py:FUSOS — manter os dois iguais. Sincronizado
// em 27/09/2026: faltavam os aeroportos acrescentados no Python em 26-27/09,
// e o site mostrava o horário desses voos em UTC.
export const FUSOS: Record<string, string> = {
  // Brasil
  BSB: "America/Sao_Paulo",
  CGH: "America/Sao_Paulo",
  CNF: "America/Sao_Paulo",
  CWB: "America/Sao_Paulo",
  GIG: "America/Sao_Paulo",
  GRU: "America/Sao_Paulo",
  MGF: "America/Sao_Paulo",
  POA: "America/Sao_Paulo",
  RAO: "America/Sao_Paulo",
  SDU: "America/Sao_Paulo",
  VCP: "America/Sao_Paulo",
  BHZ: "America/Sao_Paulo",
  FLN: "America/Sao_Paulo",
  IGU: "America/Sao_Paulo",
  IZA: "America/Sao_Paulo",
  SJP: "America/Sao_Paulo",
  UDI: "America/Sao_Paulo",
  DOU: "America/Campo_Grande",
  AJU: "America/Maceio",
  VDC: "America/Bahia",
  FOR: "America/Fortaleza",
  JPA: "America/Fortaleza",
  NAT: "America/Fortaleza",
  THE: "America/Fortaleza",
  MCZ: "America/Maceio",
  REC: "America/Recife",
  SSA: "America/Bahia",
  // Exterior
  ATL: "America/New_York",
  PTY: "America/Panama",
  BLL: "Europe/Copenhagen",
  CDG: "Europe/Paris",
  FCO: "Europe/Rome",
  FLR: "Europe/Rome",
  LHR: "Europe/London",
  LIS: "Europe/Lisbon",
  XPG: "Europe/Paris", // Gare du Nord (trecho de trem)
  QQS: "Europe/London", // St Pancras (trecho de trem)
  BKK: "Asia/Bangkok",
  DOH: "Asia/Qatar",
  AEP: "America/Argentina/Buenos_Aires",
  BLQ: "Europe/Rome",
  BOS: "America/New_York",
  JFK: "America/New_York",
  MAD: "Europe/Madrid",
  DUS: "Europe/Berlin",
  ROS: "America/Argentina/Cordoba",
};

/**
 * Fuso do aeroporto: mapa fixo primeiro, depois o `extra` (ex.: fusos
 * aprendidos da tabela fusos_aeroporto, mesma ordem de src/fusos.py:fuso_de).
 * Hoje o site só usa o fixo: fusos_aeroporto não tem policy de leitura.
 */
function fusoDe(codigoAeroporto: string | null, extra?: Record<string, string>): string | undefined {
  if (!codigoAeroporto) return undefined;
  const codigo = codigoAeroporto.trim().toUpperCase();
  return FUSOS[codigo] ?? extra?.[codigo];
}

export function temFuso(codigoAeroporto: string | null, extra?: Record<string, string>): boolean {
  return fusoDe(codigoAeroporto, extra) !== undefined;
}

function formatarEmFuso(data: Date, fuso: string): string {
  const partes = new Intl.DateTimeFormat("pt-BR", {
    timeZone: fuso,
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(data);
  const obter = (tipo: string) => partes.find((p) => p.type === tipo)?.value ?? "";
  // "qui 20/11/2026 04:10": dia da semana ajuda a conferir com o passageiro.
  return `${obter("weekday").replace(".", "")} ${obter("day")}/${obter("month")}/${obter("year")} ${obter("hour")}:${obter("minute")}`;
}

/**
 * Converte um horário UTC (ISO, como o MilhasFlow grava) pra hora local do
 * aeroporto. Sem fuso mapeado pro código, devolve o texto original — melhor
 * entregar o dado cru do que um horário errado (mesma regra do fusos.py).
 */
export function textoLocal(
  iso: string | null,
  codigoAeroporto: string | null,
  extra?: Record<string, string>,
): string {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;

  const fuso = fusoDe(codigoAeroporto, extra);
  if (!fuso) return iso;

  return formatarEmFuso(data, fuso);
}
