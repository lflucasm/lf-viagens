import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { linkPara } from "@/lib/linkReserva";
import { descreverAlerta, ehAlerta, ICONE_EVENTO, ROTULO_ORIGEM } from "@/lib/tipos";
import { textoLocal } from "@/lib/fusos";
import { BotaoAbrirLink } from "@/components/BotaoAbrirLink";
import { BotaoChecarAgora } from "@/components/BotaoChecarAgora";
import { BotaoEnviar, Giro } from "@/components/BotaoEnviar";
import { PropostaVolly } from "@/components/PropostaVolly";
import { marcarVerificado, ignorarAlerta, atribuir, adicionarNota, checarAgora } from "./actions";

// Instantes gravados em UTC (timestamptz) mostrados na hora de Brasília, que
// é a da equipe.
const FORMATO_BRASILIA = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function dataHoraBrasilia(iso: string | null): string {
  if (!iso) return "—";
  const momento = new Date(iso);
  return Number.isNaN(momento.getTime()) ? iso : FORMATO_BRASILIA.format(momento);
}

// resultado da última tentativa de "Aplicar na Volly" (propostas_volly.resultado)
type ResultadoAplicacao = { em?: string; simulado?: boolean; erro?: string };

export default async function PaginaReserva({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();

  const { data: voo, error: erroVoo } = await supabase
    .from("voos")
    .select("*")
    .eq("id", id)
    .maybeSingle();

  if (erroVoo) throw new Error(erroVoo.message);
  if (!voo) notFound();

  const [{ data: historico }, { data: observacoes }, { data: notas }, { data: atendentes },
         { data: linkPdf }, { data: checagemPendente }, { data: proposta }] =
    await Promise.all([
      supabase.from("historico").select("*").eq("voo_id", id).order("detectado_em", { ascending: false }),
      supabase.from("observacoes").select("*").eq("voo_id", id).order("visto_em", { ascending: false }),
      supabase
        .from("notas")
        .select("*, autor:perfis(nome)")
        .eq("voo_id", id)
        .order("criado_em", { ascending: false }),
      supabase.from("perfis").select("*").eq("ativo", true).order("nome"),
      voo.localizador
        ? supabase.from("links_pdf").select("url").eq("localizador", voo.localizador.toUpperCase()).maybeSingle()
        : Promise.resolve({ data: null }),
      supabase
        .from("solicitacoes_checagem")
        .select("*")
        .eq("voo_id", id)
        .eq("status", "pendente")
        .limit(1)
        .maybeSingle(),
      // última proposta de atualização da Volly (reconferência depois do
      // "verificado" - src/reconferir_cloud.py)
      supabase
        .from("propostas_volly")
        .select("*")
        .eq("voo_id", id)
        .order("criado_em", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]);

  const doPdf = new Map<string, string>();
  if (voo.localizador && linkPdf?.url) {
    doPdf.set(voo.localizador.toUpperCase(), linkPdf.url);
  }
  const link = linkPara(voo, doPdf);

  const pendente = (historico ?? []).find((h) => !h.resolvido && ehAlerta(h)) ?? null;
  const atendentePorId = new Map((atendentes ?? []).map((p) => [p.id, p.nome]));

  // Reconferência em andamento: alguém verificou depois da última proposta
  // (ou ainda não há proposta nenhuma). O workflow leva 1-3 min.
  const ultimoVerificado = (historico ?? [])
    .map((h) => h.verificado_em)
    .filter((v): v is string => Boolean(v))
    .sort()
    .at(-1);
  const reconferindo = Boolean(
    ultimoVerificado &&
      (!proposta || new Date(ultimoVerificado) > new Date(proposta.criado_em)),
  );
  const alertaPendente = pendente ? descreverAlerta(pendente, voo.cia) : null;

  // "Aplicar na Volly": pedido registrado (pedir_aplicacao_volly) e ainda sem
  // resultado posterior = o robô está rodando (1-2 min).
  const resultadoAplicacao = (proposta?.resultado ?? {}) as ResultadoAplicacao;
  const aplicando = Boolean(
    proposta?.pedido_em &&
      proposta.status === "proposta" &&
      (!resultadoAplicacao.em || new Date(proposta.pedido_em) > new Date(resultadoAplicacao.em)),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-mono text-2xl font-semibold tracking-wide">{voo.localizador}</h1>
          <p className="text-sm text-gray-500">
            {voo.cia} {voo.numero_voo} · {voo.origem} → {voo.destino} ·{" "}
            {textoLocal(voo.embarque, voo.origem)} (hora local)
          </p>
          <p className="mt-0.5 text-sm text-gray-700">{voo.passageiros}</p>
        </div>
        <div className="flex items-center gap-2">
          <BotaoAbrirLink link={link} />
          <BotaoChecarAgora
            action={checarAgora}
            vooId={voo.id}
            localizador={voo.localizador ?? ""}
            cia={voo.cia ?? ""}
            pendente={Boolean(checagemPendente)}
          />
        </div>
      </div>

      {pendente && (
        <section className="relative overflow-hidden rounded-lg border border-gray-200 bg-white/90 py-4 pl-5 pr-4">
          <span className="absolute inset-y-0 left-0 w-1 bg-atencao" aria-hidden="true" />
          <p className="text-sm font-semibold text-gray-900">
            {ICONE_EVENTO[pendente.evento] ?? "⚪"} {alertaPendente?.titulo}
            {alertaPendente?.detalhe && (
              <span className="font-normal text-gray-700"> — {alertaPendente.detalhe}</span>
            )}
          </p>
          {alertaPendente?.hipotese && (
            <p className="mt-1 text-sm text-gray-700">💡 {alertaPendente.hipotese}</p>
          )}
          <p className="mt-1 text-xs text-gray-500">
            Detectado em {dataHoraBrasilia(pendente.detectado_em)} · fonte: {alertaPendente?.fonte}
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
            <form action={marcarVerificado}>
              <input type="hidden" name="historico_id" value={pendente.id} />
              <input type="hidden" name="voo_id" value={voo.id} />
              <BotaoEnviar
                variante="marca"
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

            <form action={atribuir} className="ml-auto flex items-center gap-2">
              <input type="hidden" name="historico_id" value={pendente.id} />
              <input type="hidden" name="voo_id" value={voo.id} />
              <select
                name="atendente_id"
                defaultValue={pendente.atendente_id ?? ""}
                aria-label="Atendente"
                className="h-7 rounded-md border border-gray-300 bg-white px-2 text-xs"
              >
                <option value="">Sem atribuição</option>
                {(atendentes ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome}
                  </option>
                ))}
              </select>
              <BotaoEnviar tamanho="sm" pendente="Salvando…">
                Atribuir
              </BotaoEnviar>
            </form>
          </div>
        </section>
      )}

      {(reconferindo || proposta) && (
        <section>
          <h2 className="mb-2 text-base font-semibold">Atualização da Volly</h2>
          {reconferindo ? (
            <p className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white/90 p-3 text-sm text-gray-600">
              <Giro />
              Reconferindo com a companhia (verificado em {dataHoraBrasilia(ultimoVerificado ?? null)}). A
              proposta chega em 1 a 3 minutos; recarregue a página.
            </p>
          ) : (
            proposta && (
              <PropostaVolly
                proposta={proposta}
                passageiros={voo.passageiros}
                aplicando={aplicando}
                detalhe={
                  <>
                    {proposta.fonte ? `Fonte: ${ROTULO_ORIGEM[proposta.fonte] ?? proposta.fonte} · ` : ""}
                    {dataHoraBrasilia(proposta.criado_em)}
                    {proposta.status === "descartada" &&
                      ` · ignorada${
                        proposta.descartado_por ? ` por ${atendentePorId.get(proposta.descartado_por) ?? "?"}` : ""
                      }${proposta.descartado_em ? ` em ${dataHoraBrasilia(proposta.descartado_em)}` : ""}, nada foi gravado na Volly`}
                    {proposta.status === "aplicada" &&
                      ` · aplicada em ${dataHoraBrasilia(proposta.aplicado_em)}` +
                        (proposta.pedido_por ? ` por ${atendentePorId.get(proposta.pedido_por) ?? "?"}` : "")}
                  </>
                }
                aviso={
                  proposta.status === "proposta" && !aplicando && resultadoAplicacao.em
                    ? resultadoAplicacao.erro
                      ? `Última tentativa não aplicou: ${resultadoAplicacao.erro}`
                      : resultadoAplicacao.simulado
                        ? `Simulação em ${dataHoraBrasilia(resultadoAplicacao.em)}: aplicaria exatamente esta correção (a gravação real ainda está desligada)`
                        : null
                    : null
                }
              />
            )
          )}
        </section>
      )}

      <section>
        <h2 className="mb-2 text-base font-semibold">O que cada fonte viu</h2>
        {observacoes && observacoes.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-3 py-2">Fonte</th>
                  <th className="px-3 py-2">Partida</th>
                  <th className="px-3 py-2">Rota</th>
                  <th className="px-3 py-2">Situação</th>
                  <th className="px-3 py-2">Visto em</th>
                </tr>
              </thead>
              <tbody>
                {observacoes.map((o) => (
                  <tr key={`${o.voo_id}-${o.origem}`} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2">{o.origem}</td>
                    <td className="px-3 py-2">{o.partida}</td>
                    <td className="px-3 py-2">{o.rota}</td>
                    <td className="px-3 py-2">{o.situacao}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{o.visto_em}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-500">Nenhuma fonte reportou essa reserva ainda.</p>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold">Histórico</h2>
        {historico && historico.length > 0 ? (
          <ul className="space-y-2">
            {historico.map((h) => {
              const alerta = descreverAlerta(h, voo.cia);
              return (
                <li key={h.id} className="rounded-lg border border-gray-200 bg-white/90 p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span>
                      {ICONE_EVENTO[h.evento] ?? "⚪"} {alerta.titulo}
                      {alerta.detalhe && (
                        <span className="text-gray-600"> — {alerta.detalhe}</span>
                      )}
                    </span>
                    {ehAlerta(h) && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${h.resolvido ? "bg-ok/10 text-ok" : "bg-atencao/10 text-atencao"}`}
                      >
                        {h.resolvido
                          ? h.verificado_em
                            ? "verificado"
                            : h.ignorado_em
                              ? "ignorado"
                              : "resolvido"
                          : "pendente"}
                      </span>
                    )}
                  </div>
                  {alerta.hipotese && ehAlerta(h) && (
                    <p className="mt-1 text-xs text-gray-700">💡 {alerta.hipotese}</p>
                  )}
                  <p className="mt-1 text-xs text-gray-500">
                    {dataHoraBrasilia(h.detectado_em)} · fonte: {alerta.fonte}
                    {h.atendente_id && ` · atendente: ${atendentePorId.get(h.atendente_id) ?? "—"}`}
                  </p>
                  {h.ignorado_em && (
                    <p className="mt-1 text-xs text-gray-500">
                      Ignorado por{" "}
                      {(h.ignorado_por && atendentePorId.get(h.ignorado_por)) ?? "alguém da equipe"} em{" "}
                      {dataHoraBrasilia(h.ignorado_em)}
                    </p>
                  )}
                  {h.verificado_em && (
                    <p className="mt-1 text-xs text-ok">
                      Verificado por{" "}
                      {(h.verificado_por && atendentePorId.get(h.verificado_por)) ?? "alguém da equipe"} em{" "}
                      {dataHoraBrasilia(h.verificado_em)}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">Sem alterações registradas.</p>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold">Notas</h2>
        <form action={adicionarNota} className="mb-3 flex gap-2">
          <input type="hidden" name="voo_id" value={voo.id} />
          <input
            type="text"
            name="texto"
            placeholder="Deixar uma nota sobre essa reserva…"
            required
            className="h-9 flex-1 rounded-md border border-gray-300 bg-white px-3 text-sm"
          />
          <BotaoEnviar variante="principal" pendente="Salvando…">
            Adicionar nota
          </BotaoEnviar>
        </form>

        {notas && notas.length > 0 ? (
          <ul className="space-y-2">
            {notas.map((n) => (
              <li key={n.id} className="rounded-lg border border-gray-200 bg-white/90 p-3 text-sm">
                <p>{n.texto}</p>
                <p className="mt-1 text-xs text-gray-500">
                  {n.autor?.nome ?? "—"} · {n.criado_em}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">Nenhuma nota ainda.</p>
        )}
      </section>
    </div>
  );
}
