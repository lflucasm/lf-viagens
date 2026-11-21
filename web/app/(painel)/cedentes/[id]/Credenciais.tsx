"use client";

import { useActionState } from "react";
import { ROTULO_PROGRAMA, type Programa } from "@/lib/cedentes";
import { revelarCredenciais, type EstadoCredenciais } from "../actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

const estadoInicial: EstadoCredenciais = { erro: null, valores: null };

/**
 * As senhas só aparecem depois de um clique — a ficha do cedente é aberta o
 * tempo todo pra conferir dado bobo, e não faz sentido a senha estar no HTML
 * em toda visita.
 */
export function Credenciais({ cedenteId }: { cedenteId: string }) {
  const [estado, acao] = useActionState(revelarCredenciais, estadoInicial);

  const porPrograma = new Map<string, { login?: string; senha?: string }>();
  for (const v of estado.valores ?? []) {
    const atual = porPrograma.get(v.programa) ?? {};
    porPrograma.set(v.programa, { ...atual, [v.campo]: v.valor });
  }

  return (
    <section className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
      <h2 className="text-sm font-semibold">Credenciais das contas</h2>

      {estado.valores ? (
        <table className="w-full text-sm">
          <tbody>
            {[...porPrograma.entries()].map(([programa, dados]) => (
              <tr key={programa} className="border-b border-gray-100 last:border-0">
                <td className="py-2 pr-3 font-medium">
                  {ROTULO_PROGRAMA[programa as Programa] ?? programa}
                </td>
                <td className="py-2 pr-3 font-mono text-xs">{dados.login ?? "—"}</td>
                <td className="py-2 font-mono text-xs">{dados.senha ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <form action={acao}>
          <input type="hidden" name="cedente_id" value={cedenteId} />
          <BotaoEnviar pendente="Abrindo…">Mostrar credenciais</BotaoEnviar>
        </form>
      )}

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}
    </section>
  );
}
