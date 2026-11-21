"use client";

import { useActionState } from "react";
import { LogoLF } from "@/components/LogoLF";
import { ThemeToggle } from "@/components/ThemeToggle";
import { entrar, type EstadoLogin } from "./actions";
import { BotaoEnviar } from "@/components/BotaoEnviar";

const estadoInicial: EstadoLogin = { erro: null };

export function LoginForm() {
  const [estado, acao] = useActionState(entrar, estadoInicial);

  return (
    <form
      action={acao}
      className="relative w-full max-w-sm space-y-5 rounded-xl border border-navy-700 bg-navy-800 p-6 shadow-lg"
    >
      <ThemeToggle className="absolute right-3 top-3" />
      <div className="space-y-2 text-center">
        <LogoLF size={34} className="mx-auto" />
        <h1 className="text-xl text-cream-50">LF Viagens</h1>
        <p className="text-sm text-haze-400">Painel de monitoramento de voos</p>
      </div>

      <div className="space-y-1">
        <label htmlFor="email" className="block text-sm font-medium text-haze-400">
          E-mail
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          className="w-full rounded-md border border-navy-600 bg-navy-900 px-3 py-2 text-sm text-cream-50 placeholder:text-haze-500 focus:border-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-400/40"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="senha" className="block text-sm font-medium text-haze-400">
          Senha
        </label>
        <input
          id="senha"
          name="senha"
          type="password"
          required
          autoComplete="current-password"
          className="w-full rounded-md border border-navy-600 bg-navy-900 px-3 py-2 text-sm text-cream-50 placeholder:text-haze-500 focus:border-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-400/40"
        />
      </div>

      {estado.erro && <p className="text-sm text-red-400">{estado.erro}</p>}

      <BotaoEnviar variante="marca" pendente="Entrando…" className="w-full font-semibold">
        Entrar
      </BotaoEnviar>
    </form>
  );
}
