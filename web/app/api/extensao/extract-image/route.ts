import { exigirColaboradorPorToken } from "../_auth";
import { lerDocumentosDasFotos } from "../_openai";

// Leitura de documento por foto é a chamada mais lenta das três — o padrão
// de 10s do Vercel derruba a função antes do GPT-4o responder.
export const maxDuration = 60;

export async function POST(req: Request) {
  const { erro } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const { images } = await req.json().catch(() => ({ images: null }));
  if (!Array.isArray(images) || images.length === 0) {
    return Response.json({ error: "Campo 'images' precisa de ao menos 1 imagem em base64" }, { status: 400 });
  }

  const passageiros = await lerDocumentosDasFotos(images);
  if (!passageiros) return Response.json({ error: "IA não retornou resultado" }, { status: 502 });
  return Response.json({ passageiros });
}
