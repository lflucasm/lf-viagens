"use client";

import { useActionState } from "react";
import { confirmarAvisoContas, type EstadoAviso } from "./actions";

const estadoInicial: EstadoAviso = { erro: null };

const PASSOS = [
  "Abra o site do programa pelo link que a gente vai te mostrar.",
  "Crie a conta de verdade nesse site (ou entre na que você já tem) — preenchendo os dados que o próprio site pedir.",
  "Confirme que você conseguiu entrar — chegou na área logada da conta, dentro do site do programa.",
];

export function AvisoContas({ token }: { token: string }) {
  const [estado, acao, pendente] = useActionState(confirmarAvisoContas, estadoInicial);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border-2 border-red-300 bg-red-50 p-6 text-center shadow-sm">
        <p className="text-3xl font-extrabold leading-tight text-red-700 sm:text-4xl">
          Você precisa criar as contas de verdade
        </p>
        <p className="mt-3 text-xl font-bold text-red-600 sm:text-2xl">
          Não adianta digitar aqui um login e senha que não existem.
        </p>
      </div>

      <div className="space-y-5 rounded-xl border border-gray-100 bg-white/90 p-5 shadow-sm sm:p-6">
        <p className="text-base leading-relaxed text-gray-700">
          Na próxima tela você vai ver o passo a passo de 5 contas (e-mail, LATAM, Smiles,
          Livelo e Esfera). Para <strong>cada uma</strong> delas, o caminho é sempre o mesmo:
        </p>

        <ol className="space-y-4">
          {PASSOS.map((passo, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-900 text-sm font-bold text-cream-50">
                {i + 1}
              </span>
              <span className="pt-0.5 text-base leading-relaxed text-gray-800">{passo}</span>
            </li>
          ))}
          <li className="flex items-start gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gold-500 text-sm font-bold text-navy-950">
              4
            </span>
            <span className="pt-0.5 text-base leading-relaxed text-gray-800">
              <strong>Só depois disso</strong> você volta pra cá e coloca o login e a senha
              que você acabou de criar lá — não antes.
            </span>
          </li>
        </ol>

        <div className="rounded-lg border-2 border-gold-400 bg-gold-100/70 p-4">
          <p className="text-lg font-bold leading-snug text-navy-900 sm:text-xl">
            Se o login e a senha que você colocar aqui não existirem de verdade no site do
            programa, a conta não funciona — e isso só é descoberto depois, quando já é tarde
            pra resolver rápido.
          </p>
        </div>
      </div>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}

      <form action={acao}>
        <input type="hidden" name="token" value={token} />
        <button
          type="submit"
          disabled={pendente}
          className="w-full rounded-md bg-gold-500 px-5 py-3.5 text-lg font-bold text-navy-950 transition-colors hover:bg-gold-600 disabled:opacity-50 sm:w-auto"
        >
          {pendente ? "Um instante…" : "Entendi, vou criar as contas agora"}
        </button>
      </form>
    </div>
  );
}
