"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { confirmarCartilha, type EstadoCartilha } from "./actions";

const estadoInicial: EstadoCartilha = { erro: null };

/**
 * Confirmação de que o cedente leu a cartilha. Vem logo depois dela: o
 * checkbox só libera quando o fim da cartilha (o marcador abaixo) já passou
 * pela tela, pra "li tudo" ser mais que um clique. A trava é só de tela — o
 * servidor grava a ciência (data, IP e navegador) em confirmarCartilha.
 */
export function ConfirmarCartilha({ token }: { token: string }) {
  const [estado, acao, pendente] = useActionState(confirmarCartilha, estadoInicial);
  const fim = useRef<HTMLDivElement>(null);
  const [chegouAoFim, setChegouAoFim] = useState(false);
  const [ciente, setCiente] = useState(false);

  useEffect(() => {
    const el = fim.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        setChegouAoFim(true);
        obs.disconnect();
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <form action={acao} className="mt-10 space-y-4">
      <div ref={fim} />
      <input type="hidden" name="token" value={token} />

      <label
        className={`flex items-start gap-3 rounded-xl border-2 p-4 text-sm leading-relaxed ${chegouAoFim ? "border-red-300 bg-red-50 text-red-900" : "border-gray-200 bg-gray-50 text-gray-500"}`}
      >
        <input
          type="checkbox"
          name="ciente"
          checked={ciente}
          disabled={!chegouAoFim}
          onChange={(e) => setCiente(e.target.checked)}
          className="mt-1 h-5 w-5 shrink-0 accent-red-600"
        />
        <span>
          <strong>Li a cartilha inteira e estou ciente</strong> de que é estritamente proibido
          resgatar, pagar, converter ou transferir pontos das contas — inclusive pelo PagStix,
          pelo CPF no caixa ou pelo app de qualquer parceiro —, de que isso causa prejuízo
          financeiro à LF Viagens e de que quem fizer resgate está sujeito ao{" "}
          <strong>encerramento definitivo da parceria</strong>.
          {!chegouAoFim && (
            <em className="mt-1 block text-xs">Role a cartilha até aqui para liberar a confirmação.</em>
          )}
        </span>
      </label>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}

      <button
        type="submit"
        disabled={!ciente || pendente}
        className="w-full rounded-md bg-gold-500 px-5 py-3.5 text-lg font-bold text-navy-950 transition-colors hover:bg-gold-600 disabled:opacity-50 sm:w-auto"
      >
        {pendente ? "Um instante…" : "Confirmar leitura da cartilha"}
      </button>
    </form>
  );
}
