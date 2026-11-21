/**
 * Versão simplificada de src/qualidade.py:prioridade — mesmos limiares
 * (48h/7d/30d), mas sem a conversão de fuso por aeroporto de src/fusos.py.
 * Serve só pra ordenar/colorir o painel; a decisão de alerta em si continua
 * sendo do motor Python, que trata fuso com precisão.
 */

export type Prioridade = "critica" | "alta" | "media" | "baixa" | "indefinida" | "passado";

export function prioridade(embarqueLocal: string | null, agora: Date = new Date()): Prioridade {
  if (!embarqueLocal) return "indefinida";

  const embarque = new Date(embarqueLocal.replace(" ", "T"));
  if (Number.isNaN(embarque.getTime())) return "indefinida";

  const horas = (embarque.getTime() - agora.getTime()) / 36e5;
  if (horas < 0) return "passado";
  if (horas <= 48) return "critica";
  if (horas <= 24 * 7) return "alta";
  if (horas <= 24 * 30) return "media";
  return "baixa";
}

export const CORES_PRIORIDADE: Record<Prioridade, string> = {
  critica: "#dc2626",
  alta: "#ea580c",
  media: "#ca8a04",
  baixa: "#65a30d",
  indefinida: "#6b7280",
  passado: "#9ca3af",
};

export const ORDEM_PRIORIDADE: Record<Prioridade, number> = {
  critica: 0,
  alta: 1,
  media: 2,
  baixa: 3,
  indefinida: 4,
  passado: 5,
};

export const ROTULO_PRIORIDADE: Record<Prioridade, string> = {
  critica: "Crítica",
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
  indefinida: "Indefinida",
  passado: "Já embarcou",
};
