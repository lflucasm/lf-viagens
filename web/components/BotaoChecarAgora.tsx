"use client";

import { useState } from "react";
import { BotaoEnviar } from "@/components/BotaoEnviar";

type Props = {
  action: (formData: FormData) => Promise<void>;
  vooId: string;
  localizador: string;
  cia: string;
  /**
   * Pedido antigo ainda aberto na fila `solicitacoes_checagem` (era atendida
   * pelo Mac). Desde 26/09/2026 a fila não é mais alimentada — o botão
   * dispara direto na nuvem — então isso só aparece para pedido antigo.
   */
  pendente: boolean;
};

/**
 * Pede uma checagem individual pra esse voo, 100% na nuvem (GitHub Actions:
 * monitor Volly + portal da cia ou malha — ver checarAgora em
 * reserva/[id]/actions.ts). O resultado não volta na hora: aparece no
 * histórico/aba Urgente quando os workflows terminam. Sem localizador não
 * tem o que checar.
 */
export function BotaoChecarAgora({ action, vooId, localizador, cia, pendente }: Props) {
  const [disparado, setDisparado] = useState(false);

  if (!localizador) return null;

  if (pendente) {
    return (
      <span className="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs text-gray-500">
        <span className="h-1.5 w-1.5 rounded-full bg-gold-500" aria-hidden="true" />
        Checagem solicitada
      </span>
    );
  }

  if (disparado) {
    return (
      <span
        className="inline-flex h-7 items-center gap-1.5 rounded-md bg-ok/10 px-2.5 text-xs font-medium text-ok"
        title="Volly + portal da companhia. O resultado aparece no histórico em alguns minutos."
        role="status"
      >
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" aria-hidden="true">
          <path d="M3.5 8.5l3 3 6-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Checagem pedida
      </span>
    );
  }

  return (
    <form
      action={async (formData) => {
        await action(formData);
        setDisparado(true);
      }}
    >
      <input type="hidden" name="voo_id" value={vooId} />
      <input type="hidden" name="localizador" value={localizador} />
      <input type="hidden" name="cia" value={cia} />
      <BotaoEnviar
        tamanho="sm"
        pendente="Pedindo…"
        title="Confere de novo na nuvem: monitor Volly + portal da companhia (ou a malha, para companhia sem portal)"
      >
        Checar agora
      </BotaoEnviar>
    </form>
  );
}
