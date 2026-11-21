"use client";

import { useState } from "react";
import { classesBotao } from "@/components/botao";

/** Copia `texto` pra área de transferência e mostra "Copiada" por 2 s. */
export function BotaoCopiar({ texto, rotulo = "Copiar mensagem" }: { texto: string; rotulo?: string }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // sem permissão de clipboard: mostra o texto pra copiar na mão
      window.prompt("Copie a mensagem:", texto);
    }
  }

  return (
    <button type="button" onClick={copiar} className={classesBotao("contorno", "sm")} title={texto}>
      {copiado ? "Copiada ✓" : rotulo}
    </button>
  );
}
