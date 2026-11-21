import { exigirColaboradorPorToken } from "../_auth";
import {
  conferirComTexto,
  getOpenAI,
  modeloDaRota,
  normalizarPassageiros,
  PASSAGEIRO_JSON_SCHEMA,
  PROMPT_EXTRACAO_PASSAGEIRO,
} from "../_openai";

export async function POST(req: Request) {
  const { erro } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const { text } = await req.json().catch(() => ({ text: null }));
  if (!text || typeof text !== "string" || !text.trim()) {
    return Response.json({ error: "Campo 'text' é obrigatório" }, { status: 400 });
  }

  const openai = getOpenAI();
  const completion = await openai.chat.completions.create({
    model: modeloDaRota("extract-text"),
    temperature: 0,
    messages: [
      { role: "system", content: PROMPT_EXTRACAO_PASSAGEIRO },
      { role: "user", content: text },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "passageiros", schema: PASSAGEIRO_JSON_SCHEMA, strict: true },
    },
  });

  const raw = completion.choices[0]?.message?.content;
  if (!raw) return Response.json({ error: "IA não retornou resultado" }, { status: 502 });

  const parsed = JSON.parse(raw);
  const passageiros = normalizarPassageiros(parsed.passageiros ?? [], text);
  return Response.json({ passageiros, avisos: conferirComTexto(passageiros, text) });
}
