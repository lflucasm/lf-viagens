import { exigirColaboradorPorToken } from "../_auth";
import {
  buscarFaixas,
  lerConfig,
  limparPrograma,
  MAPA_CIA_PROGRAMA,
  mesmoPrograma,
  normPrograma,
  parseJanela,
} from "../_precos";

/**
 * GET /api/extensao/precos?window=24h|7d|30d
 *
 * Tabela de preço por programa que a aba "Preços" do popup mostra: R$/milheiro
 * médio por faixa (do felip-ai, cache 15 min) + o override manual e o markup
 * salvos no Supabase. `stale: true` = o felip-ai não respondeu e isto é o
 * último cache (ou vazio).
 */
export async function GET(req: Request) {
  const { erro, supabase } = await exigirColaboradorPorToken(req);
  if (erro) return erro;

  const janela = parseJanela(new URL(req.url).searchParams.get("window"));
  const [{ faixas, stale }, config] = await Promise.all([buscarFaixas(janela), lerConfig(supabase)]);

  // Nome canônico (limpo) por programa das cias suportadas.
  const nomesPrograma = Object.values(MAPA_CIA_PROGRAMA);

  const programs = (faixas?.rows ?? [])
    .filter((r) => nomesPrograma.some((n) => mesmoPrograma(r.programName, n)))
    .map((r) => {
      const chave = normPrograma(r.programName);
      return {
        programName: limparPrograma(r.programName),
        overallAvgPrice: r.overallAvgPrice,
        overrideMilheiro: config.overrides.get(chave) ?? null,
        bands: r.cells,
      };
    });

  // Programa sem faixa nenhuma na janela também aparece: é por aqui que o
  // colaborador fixa o milheiro de um programa que o felip-ai não cota.
  for (const nome of nomesPrograma) {
    const chave = normPrograma(nome);
    if (!programs.some((p) => mesmoPrograma(p.programName, nome))) {
      programs.push({
        programName: nome,
        overallAvgPrice: null,
        overrideMilheiro: config.overrides.get(chave) ?? null,
        bands: [],
      });
    }
  }

  return Response.json({
    window: janela,
    bandStep: faixas?.bandStep ?? 10000,
    stale,
    markup: config.markup,
    programs,
  });
}
