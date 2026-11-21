import { CORES_PRIORIDADE, ROTULO_PRIORIDADE, type Prioridade } from "@/lib/prioridade";

export function BadgePrioridade({ prioridade }: { prioridade: Prioridade }) {
  return (
    <span
      className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white"
      style={{ backgroundColor: CORES_PRIORIDADE[prioridade] }}
    >
      {ROTULO_PRIORIDADE[prioridade]}
    </span>
  );
}
