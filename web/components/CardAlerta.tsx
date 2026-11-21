import Link from "next/link";
import { BadgePrioridade } from "@/components/BadgePrioridade";
import { BotaoAbrirLink } from "@/components/BotaoAbrirLink";
import { BotaoAvisoCliente } from "@/components/BotaoAvisoCliente";
import { BotaoChecarAgora } from "@/components/BotaoChecarAgora";
import { BotaoCopiar } from "@/components/BotaoCopiar";
import { BotaoEnviar } from "@/components/BotaoEnviar";
import {
  adiarAlerta,
  checarAgora,
  ignorarAlerta,
  marcarVerificado,
} from "@/app/(painel)/reserva/[id]/actions";
import { textoLocal } from "@/lib/fusos";
import { descreverAlerta, mensagemPassageiro, nomesPassageiros } from "@/lib/tipos";
import type { LinhaVoo } from "@/lib/painel";

function haQuanto(iso: string): string {
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 60) return `há ${Math.max(min, 1)} min`;
  const h = Math.floor(min / 60);
  return h < 24 ? `há ${h}h` : `há ${Math.floor(h / 24)}d`;
}

function dataHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Um alerta pendente como card de decisão (19/11/2026, modelo da Traveos):
 * o que mudou, a hipótese e as ações lado a lado. Com mensagem pronta, o
 * passo seguinte é avisar o passageiro; sem ela, conferir a reserva.
 */
export function CardAlerta({ linha }: { linha: LinhaVoo }) {
  const { voo, pendente, link, prioridade, checagemPendente, atendenteNome, adiadoAte } = linha;
  if (!pendente) return null;
  const alerta = descreverAlerta(pendente, voo.cia);
  const mensagem = mensagemPassageiro(pendente.campo, (pendente.valor_novo ?? "").trim(), voo);
  const ids = (
    <>
      <input type="hidden" name="historico_id" value={pendente.id} />
      <input type="hidden" name="voo_id" value={voo.id} />
    </>
  );

  return (
    <article className="flex h-full flex-col gap-3 rounded-lg border border-gray-200 bg-white/90 p-4">
      <header className="flex flex-wrap items-center gap-2 text-sm">
        <BadgePrioridade prioridade={prioridade} />
        <Link
          href={`/reserva/${voo.id}`}
          className="font-mono font-semibold underline decoration-gray-300 underline-offset-4 hover:decoration-gold-500"
        >
          {voo.localizador}
        </Link>
        <span className="text-gray-600">{voo.cia}</span>
        <span className="ml-auto text-xs text-gray-500" title={dataHora(pendente.detectado_em)}>
          {haQuanto(pendente.detectado_em)}
        </span>
      </header>

      <div className="space-y-1">
        <h3 className="font-semibold text-gray-900">{alerta.titulo}</h3>
        {alerta.detalhe && <p className="text-sm text-gray-700">{alerta.detalhe}</p>}
        {alerta.hipotese && <p className="text-sm text-gray-500">{alerta.hipotese}</p>}
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-gray-600">
        <dt className="text-gray-400">Voo</dt>
        <dd>
          {voo.numero_voo} · {voo.origem} → {voo.destino} · {textoLocal(voo.embarque, voo.origem)}
        </dd>
        <dt className="text-gray-400">Passageiros</dt>
        <dd>{nomesPassageiros(voo.passageiros) || "—"}</dd>
        <dt className="text-gray-400">Fonte</dt>
        <dd>
          {alerta.fonte}
          {atendenteNome && <> · com {atendenteNome}</>}
        </dd>
        {adiadoAte && (
          <>
            <dt className="text-gray-400">Adiado</dt>
            <dd>volta em {dataHora(adiadoAte)}</dd>
          </>
        )}
      </dl>

      {mensagem && (
        <details className="rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-700">
          <summary className="cursor-pointer font-medium text-gray-600">Mensagem que vai pro cliente</summary>
          <p className="mt-1.5 whitespace-pre-line">{mensagem}</p>
        </details>
      )}

      <footer className="mt-auto flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
        {mensagem && (
          <>
            <BotaoAvisoCliente historicoId={pendente.id} vooId={voo.id} mensagem={mensagem} />
            <BotaoCopiar texto={mensagem} rotulo="Copiar" />
          </>
        )}
        <form action={marcarVerificado}>
          {ids}
          <BotaoEnviar
            variante={mensagem ? "contorno" : "marca"}
            tamanho="sm"
            pendente="Registrando…"
            title="Registra quem avisou o passageiro e pede à companhia a proposta de atualização da Volly"
          >
            Verificado — passageiro avisado
          </BotaoEnviar>
        </form>
        <BotaoAbrirLink link={link} />
        <BotaoChecarAgora
          action={checarAgora}
          vooId={voo.id}
          localizador={voo.localizador ?? ""}
          cia={voo.cia ?? ""}
          pendente={Boolean(checagemPendente)}
        />
        <div className="ml-auto flex gap-1">
          {!adiadoAte && (
            <form action={adiarAlerta}>
              {ids}
              <input type="hidden" name="horas" value={24} />
              <BotaoEnviar
                variante="discreto"
                tamanho="sm"
                pendente="Adiando…"
                title="Tira da lista por 24h sem resolver; volta sozinho"
              >
                Adiar 24h
              </BotaoEnviar>
            </form>
          )}
          <form action={ignorarAlerta}>
            {ids}
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
      </footer>
    </article>
  );
}
