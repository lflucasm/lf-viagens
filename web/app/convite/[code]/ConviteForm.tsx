"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Campo, INPUT_CLASSE, Secao } from "@/components/CadastroSecao";
import { mascararDataBr, normalizarTelefone } from "@/lib/cedentes";
import { iniciarCadastro, type EstadoConvite } from "./actions";

const estadoInicial: EstadoConvite = { erro: null, token: null };

export function ConviteForm({ codigo }: { codigo: string }) {
  const router = useRouter();
  const [estado, acao, pendente] = useActionState(iniciarCadastro, estadoInicial);
  const [nascimento, setNascimento] = useState("");
  const [telefone, setTelefone] = useState("");

  // Deu certo: sai daqui e vai pro link que vale como ponto de retomada —
  // dali em diante (pontos, PIX, contas dos programas) tudo já fica salvo
  // aos poucos, mesmo que o titular feche a aba no meio do caminho.
  useEffect(() => {
    if (estado.token) router.replace(`/cedente/${estado.token}`);
  }, [estado.token, router]);

  return (
    <form action={acao} className="space-y-6">
      <input type="hidden" name="codigo" value={codigo} />

      <Secao titulo="Seus dados">
        <Campo label="Nome completo" className="sm:col-span-2">
          <input name="nome_completo" required autoComplete="name" className={INPUT_CLASSE} />
        </Campo>
        <Campo label="CPF">
          <input name="cpf" required inputMode="numeric" placeholder="000.000.000-00" className={INPUT_CLASSE} />
        </Campo>
        <Campo label="Data de nascimento">
          <input
            name="data_nascimento"
            required
            inputMode="numeric"
            placeholder="DD/MM/AAAA"
            value={nascimento}
            onChange={(e) => setNascimento(mascararDataBr(e.target.value))}
            className={INPUT_CLASSE}
          />
        </Campo>
        <Campo label="Telefone com DDD">
          <input
            name="telefone"
            required
            inputMode="tel"
            placeholder="81900000000"
            value={telefone}
            onChange={(e) => setTelefone(normalizarTelefone(e.target.value))}
            className={INPUT_CLASSE}
          />
        </Campo>
      </Secao>

      <p className="text-xs text-gray-500">
        No próximo passo você confirma onde recebe o pagamento e aceita o termo — e a partir
        daí a gente te acompanha na criação das contas dos programas, uma de cada vez.
      </p>

      {estado.erro && <p className="text-sm text-red-600">{estado.erro}</p>}

      <button
        type="submit"
        disabled={pendente}
        className="w-full rounded-md bg-gold-500 px-4 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-600 disabled:opacity-50 sm:w-auto"
      >
        {pendente ? "Enviando…" : "Continuar"}
      </button>
    </form>
  );
}
