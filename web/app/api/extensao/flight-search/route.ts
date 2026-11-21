import { exigirColaboradorPorToken } from "../_auth";
import { getOpenAI, modeloDaRota, parametrosDeDecisao } from "../_openai";

const BUSCA_JSON_SCHEMA = {
  type: "object" as const,
  properties: {
    origin: { type: "string", description: "código IATA de 3 letras da origem — de cidade quando o texto cita a cidade" },
    destination: { type: "string", description: "código IATA de 3 letras do destino — de cidade quando o texto cita a cidade" },
    departureDate: { type: "string", description: "data de ida, formato dd/mm/aaaa" },
    returnDate: { type: "string", description: "data de volta, formato dd/mm/aaaa, ou vazio se só ida" },
    adults: { type: "number" },
    children: { type: "number" },
    babies: { type: "number" },
  },
  required: ["origin", "destination", "departureDate", "returnDate", "adults", "children", "babies"],
  additionalProperties: false,
};

const PROMPT_BUSCA = `Interprete a busca de voo em texto livre e devolva os dados estruturados.

Regras:
- origin/destination: código IATA de 3 letras.
  Cidade com mais de um aeroporto tem código próprio de cidade, que busca
  todos eles de uma vez — use SEMPRE esse código quando o texto citar a
  cidade, nunca um aeroporto específico:
    São Paulo = SAO (não GRU)      Rio de Janeiro = RIO (não GIG)
    Belo Horizonte = BHZ           Buenos Aires = BUE
    Nova York = NYC                Londres = LON
    Paris = PAR                    Milão = MIL
    Roma = ROM                     Tóquio = TYO
    Chicago = CHI                  Washington = WAS
    Toronto = YTO                  Montreal = YMQ
  Só use código de aeroporto quando o texto nomear o aeroporto: "Guarulhos"
  = GRU, "Congonhas" = CGH, "Galeão" = GIG, "Santos Dumont" = SDU,
  "Viracopos" = VCP, "Confins" = CNF.
  Cidade com um aeroporto só usa o código dele: Natal = NAT, Recife = REC,
  Fortaleza = FOR, Salvador = SSA, Brasília = BSB, Curitiba = CWB.
- Datas sempre dd/mm/aaaa. Se o ano não for dito, assuma o próximo ano em que a data ainda não passou a partir de hoje.
- Se não houver menção de volta, returnDate = "".
- adults/children/babies: se não for dito, adults = 1, children = 0, babies = 0.`;

export async function POST(req: Request) {
  const { erro } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const { query } = await req.json().catch(() => ({ query: null }));
  if (!query || typeof query !== "string" || !query.trim()) {
    return Response.json({ error: "Campo 'query' é obrigatório" }, { status: 400 });
  }

  const openai = getOpenAI();
  const modelo = modeloDaRota("flight-search");
  const completion = await openai.chat.completions.create({
    model: modelo,
    ...parametrosDeDecisao(modelo),
    messages: [
      { role: "system", content: `${PROMPT_BUSCA}\n\nData de hoje: ${new Date().toLocaleDateString("pt-BR")}` },
      { role: "user", content: query },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "busca_voo", schema: BUSCA_JSON_SCHEMA, strict: true },
    },
  });

  const raw = completion.choices[0]?.message?.content;
  if (!raw) return Response.json({ error: "IA não retornou resultado" }, { status: 502 });

  return Response.json(JSON.parse(raw));
}
