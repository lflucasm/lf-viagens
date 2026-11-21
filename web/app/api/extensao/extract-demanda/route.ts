import { exigirColaboradorPorToken } from "../_auth";
import { acertarPassageiros, camposQueFaltam, datasDeNascimento, DEMANDA_JSON_SCHEMA, normalizarDemanda, PROMPT_EXTRACAO_DEMANDA } from "../_demanda";
import { getOpenAI, lerDocumentosDasFotos, modeloDaRota, pareceDocumento } from "../_openai";

// Leitura de print por visão é lenta — o padrão de 10s do Vercel derruba a
// função antes de o modelo responder.
export const maxDuration = 60;

export async function POST(req: Request) {
  const { erro } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const { images, texts } = await req.json().catch(() => ({ images: null, texts: null }));
  const imagens: string[] = Array.isArray(images) ? images.filter((i) => typeof i === "string" && i) : [];
  const textos: string[] = Array.isArray(texts) ? texts.filter((t) => typeof t === "string" && t.trim()) : [];
  if (!imagens.length && !textos.length) {
    return Response.json({ error: "Mande ao menos 1 imagem ('images') ou texto ('texts') da demanda" }, { status: 400 });
  }

  // Sem data de nascimento no texto, os passageiros só vêm nos documentos das
  // fotos: lê junto com o print (em paralelo) pra contar adultos/crianças/bebês
  // antes da busca. A extensão guarda e reaproveita no preenchimento.
  const datasDoTexto = datasDeNascimento(textos);
  const lerFotos = !datasDoTexto.length && imagens.length > 0;

  const openai = getOpenAI();
  const [completion, dasFotos] = await Promise.all([openai.chat.completions.create({
    model: modeloDaRota("extract-demanda"),
    temperature: 0,
    messages: [
      { role: "system", content: `${PROMPT_EXTRACAO_DEMANDA}\n\nData de hoje: ${new Date().toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" })}` },
      {
        role: "user",
        content: [
          { type: "text", text: textos.length ? `Mensagens da agência:\n\n${textos.join("\n\n")}` : "A agência mandou só o(s) print(s) a seguir." },
          ...imagens.map((b64) => ({
            type: "image_url" as const,
            image_url: { url: b64.startsWith("data:") ? b64 : `data:image/jpeg;base64,${b64}` },
          })),
        ],
      },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "demanda_emissao", schema: DEMANDA_JSON_SCHEMA, strict: true },
    },
  }), lerFotos ? lerDocumentosDasFotos(imagens).catch(() => null) : null]);

  const raw = completion.choices[0]?.message?.content;
  if (!raw) return Response.json({ error: "IA não retornou resultado" }, { status: 502 });

  const passageirosDasFotos = dasFotos ? dasFotos.filter(pareceDocumento) : null;
  const datas = datasDoTexto.length ? datasDoTexto : (passageirosDasFotos ?? []).map((p) => String(p.data_nascimento));
  const demanda = acertarPassageiros(normalizarDemanda(JSON.parse(raw)), datas);
  return Response.json({ demanda, faltam: camposQueFaltam(demanda), passageirosDasFotos });
}
