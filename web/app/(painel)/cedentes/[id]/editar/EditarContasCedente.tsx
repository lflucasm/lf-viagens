"use client";

import { useActionState } from "react";
import { INPUT_CLASSE } from "@/components/CadastroSecao";
import { PROGRAMAS, ROTULO_PROGRAMA, type Programa } from "@/lib/cedentes";
import { atualizarContaCedente, type EstadoContaAdmin } from "../../actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

type Conta = {
  programa: string;
  status: string;
  login: string | null;
  observacao: string | null;
};

const estadoInicial: EstadoContaAdmin = { erro: null, sucesso: null };

function LinhaConta({
  cedenteId,
  conta,
  temSenha,
}: {
  cedenteId: string;
  conta: Conta;
  temSenha: boolean;
}) {
  const [estado, acao] = useActionState(atualizarContaCedente, estadoInicial);
  const programa = conta.programa as Programa;

  return (
    <form action={acao} className="space-y-3 rounded-lg border border-gray-200 bg-white/90 p-4">
      <input type="hidden" name="cedente_id" value={cedenteId} />
      <input type="hidden" name="programa" value={programa} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900">{ROTULO_PROGRAMA[programa]}</h3>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            conta.status === "concluida" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
          }`}
        >
          {conta.status === "concluida"
            ? "criada"
            : conta.status === "nao_criada"
              ? "não conseguiu criar"
              : "não começou"}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="block text-xs font-medium text-gray-600">
            {programa === "email" ? "E-mail criado" : "Login (e-mail ou CPF)"}
          </span>
          <input name="login" defaultValue={conta.login ?? ""} autoComplete="off" className={INPUT_CLASSE} />
        </label>
        <label className="block space-y-1">
          <span className="block text-xs font-medium text-gray-600">
            Senha
            {temSenha && <span className="ml-1 font-normal text-gold-600">· já guardada</span>}
          </span>
          <input
            name="senha"
            type="password"
            autoComplete="new-password"
            placeholder={temSenha ? "Deixe em branco para manter" : ""}
            className={INPUT_CLASSE}
          />
        </label>
      </div>

      <label className="block space-y-1">
        <span className="block text-xs font-medium text-gray-600">Observação</span>
        <input name="observacao" defaultValue={conta.observacao ?? ""} className={INPUT_CLASSE} />
      </label>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}
      {estado.sucesso && <p className="text-sm text-green-700">{estado.sucesso}</p>}

      <BotaoEnviar tamanho="sm" pendente="Salvando…">
        Salvar
      </BotaoEnviar>
    </form>
  );
}

export function EditarContasCedente({
  cedenteId,
  contas,
  comSenha,
}: {
  cedenteId: string;
  contas: Conta[];
  comSenha: string[];
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">Contas e credenciais</h2>
        <p className="text-xs text-gray-500">
          Deixe a senha em branco pra manter a que já está guardada.
        </p>
      </div>
      <div className="space-y-3">
        {PROGRAMAS.map((p) => {
          const conta = contas.find((c) => c.programa === p.chave) ?? {
            programa: p.chave,
            status: "pendente",
            login: null,
            observacao: null,
          };
          return (
            <LinhaConta
              key={p.chave}
              cedenteId={cedenteId}
              conta={conta}
              temSenha={comSenha.includes(p.chave)}
            />
          );
        })}
      </div>
    </section>
  );
}
