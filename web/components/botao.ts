/**
 * Sistema único de botões do painel. Cada variante tem um papel, não uma cor
 * solta por página:
 *
 * - `marca`: a decisão que grava algo fora do site (Aplicar na Volly,
 *   Verificado). Dourado da logo, no máximo um por bloco.
 * - `principal`: a ação normal de um formulário (Filtrar, Adicionar).
 * - `contorno`: ação secundária ao lado de uma principal (Abrir, Checar agora).
 * - `discreto`: sair de um fluxo sem gravar nada (Ignorar, Cancelar).
 *
 * Altura fixa por tamanho pra botões lado a lado alinharem em qualquer linha
 * de tabela, e `active:` dá retorno no clique antes de a ação responder.
 * Fica fora do arquivo "use client" pra servir também em <a> e <Link> de
 * Server Component.
 */
export type Variante = "marca" | "principal" | "contorno" | "discreto";
export type Tamanho = "sm" | "md";

const BASE =
  "inline-flex shrink-0 select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium " +
  "transition-[background-color,border-color,color,transform] duration-150 active:translate-y-px " +
  "disabled:pointer-events-none disabled:opacity-60 aria-disabled:pointer-events-none aria-disabled:opacity-60";

const VARIANTES: Record<Variante, string> = {
  marca: "bg-gold-500 text-navy-950 shadow-sm shadow-gold-600/20 hover:bg-gold-400 active:bg-gold-600",
  principal: "bg-gray-900 text-white hover:bg-gray-700 active:bg-gray-800",
  contorno: "border border-gray-300 bg-white text-gray-800 hover:border-gray-400 hover:bg-gray-50 active:bg-gray-100",
  discreto: "text-gray-500 hover:bg-gray-100 hover:text-gray-900 active:bg-gray-200",
};

const TAMANHOS: Record<Tamanho, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
};

export function classesBotao(variante: Variante = "contorno", tamanho: Tamanho = "md", extra = "") {
  return `${BASE} ${VARIANTES[variante]} ${TAMANHOS[tamanho]} ${extra}`.trim();
}
