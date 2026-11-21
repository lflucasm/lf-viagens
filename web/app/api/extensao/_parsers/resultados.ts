/**
 * Parsers da resposta de busca (award) de cada cia → lista normalizada de voos.
 *
 * Escritos contra fixtures reais em `__fixtures__/<cia>-resultados.json`
 * (capturadas pela extensão na sessão logada do proprietário, 2026-08-30).
 *
 * Cada cia manda um payload enorme e a maior parte é ruído — os acessos vão
 * todos por `rec()`/`arr()` pra ler só o que interessa sem `any`.
 */
import type { Cia } from "../_precos";

export interface VooExtraido {
  /** `ORIG-DEST-DEPHHMM-CHEGHHMM` — o content script casa por isto. */
  chave: string;
  origem: string;
  destino: string;
  dataIda: string; // YYYY-MM-DD
  horaPartida: string; // HH:MM
  horaChegada: string; // HH:MM
  milhas: number;
  /**
   * Azul: pontos com o desconto de titular ("DiscountForContactPax", 10%),
   * que só vale se o titular da conta estiver na reserva. Ausente = sem
   * desconto nessa tarifa (ou cia que não tem isso).
   */
  milhasTitular?: number;
  taxa: number; // BRL
  /** Só no modo carrinho: moeda em que a cia mostra a taxa (ausente = BRL). */
  moeda?: string;
  escalas: number;
}

// ── acessores tolerantes a payload desconhecido ───────────────────────────
type Rec = Record<string, unknown>;
const rec = (v: unknown): Rec => (v && typeof v === "object" ? (v as Rec) : {});
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

function num(v: unknown): number {
  const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}
function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

function soHora(v: unknown): string {
  const m = str(v).match(/(\d{1,2}):(\d{2})/);
  return m ? `${m[1].padStart(2, "0")}:${m[2]}` : "";
}
function soData(v: unknown): string {
  const s = str(v);
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/); // ISO
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/); // dd/mm/yyyy
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return "";
}
/**
 * `ORIG-DEST-DEPHHMM-CHEGHHMM`. A hora de chegada entra pra desempatar voos
 * que partem no mesmo horário mas com conexões diferentes (a Latam lista
 * vários assim). Se a chegada não vier no payload, o sufixo fica vazio — o
 * content script monta a chave do mesmo jeito, então continua casando.
 */
function chaveVoo(origem: string, destino: string, horaPartida: string, horaChegada: string): string {
  const hhmm = (h: string) => h.replace(/\D/g, "");
  return `${origem}-${destino}-${hhmm(horaPartida)}-${hhmm(horaChegada)}`;
}
function voo(p: Omit<VooExtraido, "chave">): VooExtraido | null {
  if (!p.origem || !p.destino || !p.horaPartida || !(p.milhas > 0)) return null;
  return { ...p, chave: chaveVoo(p.origem, p.destino, p.horaPartida, p.horaChegada) };
}

// ── Latam: /bff/air-offers/v2/offers/search ───────────────────────────────
function parseLatam(payload: unknown): VooExtraido[] {
  const out: VooExtraido[] = [];
  for (const item of arr(rec(payload).content)) {
    const s = rec(rec(item).summary);
    const origin = rec(s.origin);
    const destination = rec(s.destination);
    if (!origin.iataCode || !destination.iataCode) continue;

    const brandsPts = arr(s.brands)
      .map((b) => rec(b))
      .filter((b) => rec(b.price).currency === "LOYALTY_POINTS" && rec(b.cabin).id === "Y")
      .map((b) => ({ milhas: num(rec(b.price).amount), taxa: num(rec(b.taxes).amount) }))
      .filter((b) => b.milhas > 0)
      .sort((a, b) => a.milhas - b.milhas);

    const escolhido = brandsPts[0];
    const milhas = escolhido ? escolhido.milhas : num(rec(s.lowestPrice).amount);
    const taxa = escolhido ? escolhido.taxa : num(rec(rec(arr(s.brands)[0]).taxes).amount);

    const v = voo({
      origem: str(origin.iataCode),
      destino: str(destination.iataCode),
      dataIda: soData(origin.departure),
      horaPartida: soHora(origin.departureTime || origin.departure),
      horaChegada: soHora(destination.arrivalTime || destination.arrival),
      milhas,
      taxa,
      escalas: num(s.stopOvers),
    });
    if (v) out.push(v);
  }
  return out;
}

// ── Azul Pelo Mundo: api/v1/availability ──────────────────────────────────
function parseAzpm(payload: unknown): VooExtraido[] {
  const data = rec(rec(payload).data);
  const out: VooExtraido[] = [];
  for (const item of arr(rec(data.departureFlights).flights)) {
    const f = rec(item);
    const v = voo({
      origem: str(f.originAirport || data.origin),
      destino: str(f.finalDestination || data.finalDestination),
      dataIda: soData(f.departureDate),
      horaPartida: soHora(f.departureTime),
      horaChegada: soHora(f.finalArrivalTime),
      milhas: num(rec(f.points).value),
      taxa: num(rec(rec(rec(arr(f.recommendations)[0]).fee).total).value),
      escalas: num(f.connection),
    });
    if (v) out.push(v);
  }
  return out;
}

// ── Smiles: mfe emissão de passagem ───────────────────────────────────────
function parseSmiles(payload: unknown): VooExtraido[] {
  const out: VooExtraido[] = [];
  for (const seg of arr(rec(payload).requestedFlightSegmentList)) {
    for (const item of arr(rec(seg).flightList)) {
      const f = rec(item);
      const fares = arr(f.fareList).map((x) => rec(x));
      // Preço sempre em cima da tarifa Clube Smiles (decisão do proprietário,
      // 2026-10-14); sem clube, a SMILES normal. SMILES_MONEY/MONEY misturam
      // dinheiro e nunca servem de base.
      const doTipo = (t: string) => fares.find((x) => x.type === t && num(x.miles) > 0);
      const barato = fares
        .filter((x) => num(x.miles) > 0 && x.type !== "SMILES_MONEY" && x.type !== "MONEY")
        .sort((a, b) => num(a.miles) - num(b.miles))[0];
      const fare = doTipo("SMILES_CLUB") || doTipo("SMILES") || barato || {};
      const v = voo({
        origem: str(rec(rec(f.departure).airport).code),
        destino: str(rec(rec(f.arrival).airport).code),
        dataIda: soData(rec(f.departure).date),
        horaPartida: soHora(rec(f.departure).date),
        horaChegada: soHora(rec(f.arrival).date),
        milhas: num(fare.miles),
        taxa: num(rec(fare.g3).costTax),
        escalas: num(f.stops),
      });
      if (v) out.push(v);
    }
  }
  return out;
}

// ── Azul doméstico: reservationavailability/api/reservation/availability ───
function parseAzul(payload: unknown): VooExtraido[] {
  const out: VooExtraido[] = [];
  for (const t of arr(rec(rec(payload).data).trips)) {
    const trip = rec(t);
    for (const j of arr(trip.journeys)) {
      const journey = rec(j);
      const id = rec(journey.identifier);
      // amountLevel 1 = tarifa 100% pontos (o "teto"); níveis > 1 são pontos + dinheiro.
      let milhas = 0;
      let milhasTitular = 0;
      let taxa = 0;
      for (const fare of arr(journey.fares)) {
        for (const pp of arr(rec(fare).paxPoints)) {
          if (rec(pp).amountLevel !== 1) continue;
          const lvl = rec(arr(rec(pp).levels)[0]);
          const points = rec(lvl.points);
          const pts = num(points.amount);
          if (pts > 0 && (milhas === 0 || pts < milhas)) {
            milhas = pts;
            // `amount` é o cheio (titular fora); `discountedAmount` só vale
            // com o titular voando — só quando o desconto foi aplicado.
            const desconto = rec(points.discount);
            const comDesconto = num(points.discountedAmount);
            milhasTitular = desconto.applied === true && comDesconto > 0 && comDesconto < pts ? comDesconto : 0;
            taxa = Math.round((num(lvl.taxesAndFees) + num(lvl.convenienceFee)) * 100) / 100;
          }
        }
      }
      const segs = arr(journey.segments);
      const v = voo({
        origem: str(id.departureStation || trip.departureStation),
        destino: str(id.arrivalStation || trip.arrivalStation),
        dataIda: soData(id.std),
        horaPartida: soHora(id.std),
        horaChegada: soHora(id.sta),
        milhas,
        taxa,
        escalas: Math.max(0, segs.length - 1),
      });
      if (v && milhasTitular) v.milhasTitular = milhasTitular;
      if (v) out.push(v);
    }
  }
  return out;
}

// tap/iberia/aa/copa não têm parser: a extensão lê milhas + taxa da tela e
// manda no modo carrinho.
const semParser = (): VooExtraido[] => [];

export const PARSERS_RESULTADOS: Record<Cia, (payload: unknown) => VooExtraido[]> = {
  latam: parseLatam,
  azpm: parseAzpm,
  smiles: parseSmiles,
  azul: parseAzul,
  tap: semParser,
  iberia: semParser,
  aa: semParser,
  copa: semParser,
};
