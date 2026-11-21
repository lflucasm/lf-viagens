"use client";

import { useActionState } from "react";
import { criarColaborador, type EstadoUsuarios } from "./actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

const estadoInicial: EstadoUsuarios = { erro: null, sucesso: null };

export function NovoColaboradorForm() {
  const [estado, acao] = useActionState(criarColaborador, estadoInicial);

  return (
    <form
      action={acao}
      className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white/90 p-4"
    >
      <Campo label="Nome">
        <input name="nome" required className="rounded-md border border-gray-300 px-2 py-1 text-sm" />
      </Campo>
      <Campo label="E-mail">
        <input
          name="email"
          type="email"
          required
          className="rounded-md border border-gray-300 px-2 py-1 text-sm"
        />
      </Campo>
      <Campo label="Senha provisória">
        <input
          name="senha"
          type="password"
          required
          minLength={6}
          className="rounded-md border border-gray-300 px-2 py-1 text-sm"
        />
      </Campo>
      <Campo label="Papel">
        <select name="papel" defaultValue="atendente" className="rounded-md border border-gray-300 px-2 py-1 text-sm">
          <option value="atendente">Atendente</option>
          <option value="admin">Admin</option>
        </select>
      </Campo>

      <BotaoEnviar variante="principal" pendente="Criando…">
        Criar colaborador
      </BotaoEnviar>

      {estado.erro && <p className="w-full text-sm text-perigo">{estado.erro}</p>}
      {estado.sucesso && <p className="w-full text-sm text-ok">{estado.sucesso}</p>}
    </form>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-gray-500">
      {label}
      {children}
    </label>
  );
}
