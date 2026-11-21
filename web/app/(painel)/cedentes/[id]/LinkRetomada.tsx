"use client";

import { useState } from "react";
import { classesBotao } from "@/components/botao";

/** Mesmo padrão de copiar-e-colar do link de convite, mas pro link individual
 * do cedente — o token que permite a ele retomar o cadastro de onde parou. */
export function LinkRetomada({ url }: { url: string }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    await navigator.clipboard.writeText(url);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        readOnly
        value={url}
        onFocus={(e) => e.currentTarget.select()}
        className="min-w-0 flex-1 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-xs"
      />
      <button
        type="button"
        onClick={copiar}
        className={classesBotao("principal", "md", "min-w-[5.5rem]")}
      >
        {copiado ? "Copiado!" : "Copiar"}
      </button>
    </div>
  );
}
