import Link from "next/link";
import { BadgePrioridade } from "@/components/BadgePrioridade";
import { BotaoAbrirLink } from "@/components/BotaoAbrirLink";
import { BotaoChecarAgora } from "@/components/BotaoChecarAgora";
import { BotaoEnviar } from "@/components/BotaoEnviar";
import { marcarVerificado, ignorarAlerta, checarAgora } from "@/app/(painel)/reserva/[id]/actions";
import { descreverAlerta, ICONE_EVENTO } from "@/lib/tipos";
import { textoLocal } from "@/lib/fusos";
import type { LinhaVoo } from "@/lib/painel";

export function TabelaVoos({ linhas }: { linhas: LinhaVoo[] }) {
  if (linhas.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white/90 p-6 text-center text-sm text-gray-500">
        Nenhuma reserva encontrada com esse filtro.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
      <table className="w-full min-w-[960px] text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-[11px] font-medium uppercase tracking-wider text-gray-500">
            <th className="px-3 py-2">Urgência</th>
            <th className="px-3 py-2">Cia</th>
            <th className="px-3 py-2">Localizador</th>
            <th className="px-3 py-2">Trecho</th>
            <th className="px-3 py-2">Embarque</th>
            <th className="px-3 py-2">Passageiro</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Atendente</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {linhas.map(({ voo, pendente, atendenteNome, link, prioridade, checagemPendente }) => {
            const alerta = pendente ? descreverAlerta(pendente, voo.cia) : null;
            return (
              <tr key={voo.id} className="border-b border-gray-100 transition-colors last:border-0 hover:bg-gray-50/80">
                <td className="px-3 py-2">
                  <BadgePrioridade prioridade={prioridade} />
                </td>
                <td className="px-3 py-2">{voo.cia}</td>
                <td className="px-3 py-2 font-mono font-semibold">
                  <Link
                    href={`/reserva/${voo.id}`}
                    className="underline decoration-gray-300 underline-offset-4 transition-colors hover:decoration-gold-500"
                  >
                    {voo.localizador}
                  </Link>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {voo.origem} → {voo.destino}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {textoLocal(voo.embarque, voo.origem)}
                </td>
                <td className="px-3 py-2 max-w-[220px] truncate" title={voo.passageiros ?? ""}>
                  {voo.passageiros}
                </td>
                <td className="px-3 py-2">
                  {pendente ? (
                    <div className="flex max-w-[340px] flex-wrap items-center gap-1.5">
                      <span
                        className="mr-1 inline-flex items-center gap-1 font-medium"
                        title={[alerta?.detalhe, alerta?.hipotese, alerta?.fonte].filter(Boolean).join(" · ")}
                      >
                        <span>{ICONE_EVENTO[pendente.evento] ?? "⚪"}</span>
                        <span>{alerta?.titulo}</span>
                      </span>
                      <form action={marcarVerificado}>
                        <input type="hidden" name="historico_id" value={pendente.id} />
                        <input type="hidden" name="voo_id" value={voo.id} />
                        <BotaoEnviar
                          tamanho="sm"
                          pendente="Registrando…"
                          title="Registra quem avisou o passageiro e pede à companhia a proposta de atualização da Volly"
                        >
                          Verificado — passageiro avisado
                        </BotaoEnviar>
                      </form>
                      <form action={ignorarAlerta}>
                        <input type="hidden" name="historico_id" value={pendente.id} />
                        <input type="hidden" name="voo_id" value={voo.id} />
                        <BotaoEnviar
                          variante="discreto"
                          tamanho="sm"
                          pendente="Ignorando…"
                          title="Tira o alerta da lista sem reconferir nem propor nada pra Volly"
                        >
                          Ignorar
                        </BotaoEnviar>
                      </form>
                    </div>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-xs text-gray-500">
                      <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
                      ok
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">{atendenteNome ?? "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                    <BotaoAbrirLink link={link} />
                    <BotaoChecarAgora
                      action={checarAgora}
                      vooId={voo.id}
                      localizador={voo.localizador ?? ""}
                      cia={voo.cia ?? ""}
                      pendente={Boolean(checagemPendente)}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
