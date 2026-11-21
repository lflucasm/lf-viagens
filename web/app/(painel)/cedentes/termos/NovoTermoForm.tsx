"use client";

import { useActionState } from "react";
import { publicarTermo, type EstadoTermo } from "./actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

const estadoInicial: EstadoTermo = { erro: null, sucesso: null };

export function NovoTermoForm() {
  const [estado, acao] = useActionState(publicarTermo, estadoInicial);

  return (
    <form action={acao} className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
      <h2 className="text-sm font-semibold">Publicar versão nova</h2>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="block text-xs font-medium text-gray-600">Título</span>
          <input
            name="titulo"
            required
            placeholder="Termo de ciência e autorização"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="block space-y-1">
          <span className="block text-xs font-medium text-gray-600">Versão</span>
          <input
            name="versao"
            required
            placeholder="v1-2026-08"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      <label className="block space-y-1">
        <span className="block text-xs font-medium text-gray-600">Texto do termo</span>
        <textarea
          name="corpo"
          required
          rows={10}
          className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs"
        />
      </label>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}
      {estado.sucesso && <p className="text-sm text-green-700">{estado.sucesso}</p>}

      <BotaoEnviar variante="principal" pendente="Publicando…">
        Publicar
      </BotaoEnviar>
    </form>
  );
}
