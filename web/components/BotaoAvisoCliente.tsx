"use client";

import { useActionState } from "react";
import { classesBotao } from "@/components/botao";
import { enviarAvisoAoCliente } from "@/app/(painel)/reserva/[id]/actions";

/**
 * Envia o aviso pronto pro WhatsApp do cliente (via Volly) e marca o alerta
 * como verificado. Pede confirmação: a mensagem vai pra um cliente real.
 */
export function BotaoAvisoCliente({
  historicoId,
  vooId,
  mensagem,
}: {
  historicoId: number;
  vooId: string;
  mensagem: string;
}) {
  const [estado, acao, pendente] = useActionState(enviarAvisoAoCliente, null);

  return (
    <form
      action={acao}
      onSubmit={(e) => {
        if (!window.confirm(`Enviar esta mensagem ao cliente pelo WhatsApp?\n\n${mensagem}`)) e.preventDefault();
      }}
      className="contents"
    >
      <input type="hidden" name="historico_id" value={historicoId} />
      <input type="hidden" name="voo_id" value={vooId} />
      <button type="submit" disabled={pendente} className={classesBotao("marca", "sm")}>
        {pendente ? "Enviando…" : "Enviar aviso ao cliente"}
      </button>
      {estado?.erro && (
        <p role="alert" className="basis-full text-xs text-red-600">
          Não enviado: {estado.erro}
        </p>
      )}
    </form>
  );
}
