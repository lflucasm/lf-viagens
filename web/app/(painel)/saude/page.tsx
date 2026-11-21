import { nomesPassageiros } from "@/lib/tipos";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { textoLocal } from "@/lib/fusos";
import {
  ETAPAS,
  ha,
  horaBrasilia,
  objeto,
  semCobertura,
  statusEtapa,
  type Cor,
} from "./regras";

const COR_BOLINHA: Record<Cor, string> = {
  verde: "bg-green-500",
  amarelo: "bg-amber-400",
  vermelho: "bg-red-500",
  cinza: "bg-gray-300",
};

const COR_TEXTO: Record<Cor, string> = {
  verde: "text-green-700",
  amarelo: "text-amber-700",
  vermelho: "text-red-700",
  cinza: "text-gray-500",
};

const ICONE_NIVEL: Record<string, string> = { vermelho: "🔴", laranja: "🟠", amarelo: "🟡" };

const LISTA_MAX = 60;

// Limite medido da Volly em 26/09/2026: 120 consultas reais por hora por
// organização (robô + equipe). Mesmo valor de LIMITE_VOLLY_HORA em
// src/checar_volly_cloud.py.
const LIMITE_VOLLY_HORA = 120;

/**
 * Tudo o que a página mostra, lido na hora (o supervisor de verdade roda no
 * Actions — aqui é o retrato de agora). Fora do componente pra o "agora"
 * não ficar dentro do render.
 */
async function carregarSaude() {
  const supabase = await createClient();
  const agora = Date.now();
  const seteDias = new Date(agora - 7 * 24 * 36e5).toISOString();

  const [{ data: batimentos }, { data: estado }, { data: voos }, { data: observacoes }] =
    await Promise.all([
      supabase
        .from("batimentos")
        .select("*")
        .gte("inicio", seteDias)
        .order("inicio", { ascending: false })
        .limit(2000),
      supabase
        .from("supervisor_estado")
        .select("*")
        .like("chave", "sup:%")
        .neq("chave", "sup:resumo_diario")
        .order("aberto_em", { ascending: true }),
      supabase
        .from("voos")
        .select("id, localizador, numero_voo, origem, destino, embarque, incompleto, passageiros")
        .eq("ativo", true)
        .gt("embarque", new Date(agora).toISOString()),
      supabase.from("observacoes").select("voo_id, origem, visto_em"),
    ]);

  const lista = batimentos ?? [];
  return {
    agora,
    etapas: ETAPAS.map((e) => statusEtapa(e, lista, agora)),
    problemas: estado ?? [],
    cobertura: semCobertura(voos ?? [], observacoes ?? [], lista, agora),
    incompletos: (voos ?? [])
      .filter((v) => v.incompleto)
      .sort((a, b) => (a.embarque ?? "").localeCompare(b.embarque ?? "")),
  };
}

function resumoDetalhe(etapa: string, detalhe: Record<string, unknown>): string {
  const partes: string[] = [];
  const n = (k: string) => (typeof detalhe[k] === "number" ? (detalhe[k] as number) : null);
  if (etapa === "ingestao" && n("futuros_ativos") !== null) {
    partes.push(`${n("futuros_ativos")} voos futuros`);
    if (n("incompletos")) partes.push(`${n("incompletos")} incompletos`);
  }
  if (etapa === "monitor-volly") {
    if (n("chamadas") !== null) partes.push(`${n("chamadas")} chamadas`);
    if (n("orcamento") !== null) partes.push(`orçamento ${n("orcamento")}`);
    if (n("lookups_ultima_hora") !== null) {
      partes.push(`${n("lookups_ultima_hora")} de ${LIMITE_VOLLY_HORA} consultas/h da org`);
    }
    if (n("sem_leitura")) partes.push(`${n("sem_leitura")} sem leitura`);
    if (detalhe.limite_batido) partes.push("limite da Volly batido");
  }
  if (n("bloqueios")) partes.push(`${n("bloqueios")} bloqueios`);
  if (typeof detalhe.erro === "string") partes.push(`erro: ${detalhe.erro.slice(0, 120)}`);
  return partes.join(" · ");
}

export default async function PaginaSaude() {
  const { agora, etapas, problemas, cobertura, incompletos } = await carregarSaude();
  const { elegiveis, faltando } = cobertura;
  const pct = elegiveis ? Math.round((100 * (elegiveis - faltando.length)) / elegiveis) : 100;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Saúde do sistema</h1>
        <p className="text-sm text-gray-500">
          Cada etapa do monitoramento na nuvem pela última rodada gravada. O supervisor confere
          isto a cada ciclo (de 2 em 2h, das 07h às 23h) e avisa no Telegram; o resumo diário chega por volta das 07h — se não
          chegar, o próprio agendador parou.
        </p>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-gray-700">Etapas</h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-3 py-2">Etapa</th>
                <th className="px-3 py-2">Situação</th>
                <th className="px-3 py-2">Última rodada</th>
                <th className="px-3 py-2">Lidos / falhas</th>
                <th className="px-3 py-2">Detalhe</th>
              </tr>
            </thead>
            <tbody>
              {etapas.map(({ etapa, cor, motivo, ultima }) => (
                <tr key={etapa.etapa} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2">
                    <div className="font-medium">{etapa.nome}</div>
                    <div className="text-xs text-gray-500">{etapa.cadencia}</div>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-2">
                      <span
                        className={`h-2.5 w-2.5 rounded-full ${COR_BOLINHA[cor]}`}
                        aria-hidden="true"
                      />
                      <span className={COR_TEXTO[cor]}>{motivo}</span>
                    </span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {ultima ? (
                      <>
                        {horaBrasilia(ultima.inicio)}
                        <span className="ml-1 text-xs text-gray-500">({ha(ultima.inicio, agora)})</span>
                        {ultima.ok === false && (
                          <span className="ml-1.5 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">
                            falhou
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    {ultima ? `${ultima.lidos ?? 0} / ${ultima.falhas ?? 0}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {ultima ? resumoDetalhe(etapa.etapa, objeto(ultima.detalhe)) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-gray-700">
          Problemas abertos ({problemas.length})
        </h2>
        {problemas.length === 0 ? (
          <p className="text-sm text-gray-500">Nenhum problema aberto pelo supervisor.</p>
        ) : (
          <ul className="space-y-2">
            {problemas.map((p) => {
              const d = objeto(p.detalhe);
              return (
                <li
                  key={p.chave}
                  className="rounded-lg border border-gray-200 bg-white/90 px-3 py-2 text-sm"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="whitespace-pre-line">
                      {ICONE_NIVEL[String(d.nivel)] ?? "⚪"} {String(d.texto ?? p.chave)}
                    </span>
                    <span className="text-xs text-gray-500">
                      aberto {horaBrasilia(p.aberto_em)} ({ha(p.aberto_em, agora)})
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-gray-700">
          Voos sem cobertura ({faltando.length} de {elegiveis} · cobertura {pct}%)
        </h2>
        <p className="mb-2 text-xs text-gray-500">
          Voo elegível (ativo, embarque futuro, dados completos) sem leitura de nenhuma fonte
          nas últimas 24h — ou 4h se embarca em menos de 24h.
        </p>
        {faltando.length === 0 ? (
          <p className="text-sm text-gray-500">Todos os voos elegíveis foram lidos no prazo.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-3 py-2">Localizador</th>
                  <th className="px-3 py-2">Voo</th>
                  <th className="px-3 py-2">Embarque (local)</th>
                  <th className="px-3 py-2">Última leitura</th>
                  <th className="px-3 py-2">Motivo (monitor Volly)</th>
                </tr>
              </thead>
              <tbody>
                {faltando.slice(0, LISTA_MAX).map(({ voo, ultimaLeitura, motivo }) => (
                  <tr key={voo.id} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-mono">
                      <Link href={`/reserva/${voo.id}`} className="hover:underline">
                        {voo.localizador ?? "?"}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      {voo.numero_voo ?? "—"}
                      <span className="ml-1 text-xs text-gray-500">
                        {voo.origem}–{voo.destino}
                      </span>
                      {voo.passageiros && (
                        <span className="block text-xs text-gray-500">👤 {nomesPassageiros(voo.passageiros, 2)}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {textoLocal(voo.embarque, voo.origem)}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {ultimaLeitura === null ? "nunca" : ha(ultimaLeitura, agora)}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">{motivo ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {faltando.length > LISTA_MAX && (
              <p className="px-3 py-2 text-xs text-gray-500">
                … e mais {faltando.length - LISTA_MAX}
              </p>
            )}
          </div>
        )}
      </section>

      {incompletos.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-gray-700">
            Trechos incompletos ({incompletos.length}) — não são checados
          </h2>
          <ul className="space-y-1 text-sm">
            {incompletos.map((v) => (
              <li key={v.id}>
                <Link href={`/reserva/${v.id}`} className="font-mono hover:underline">
                  {v.localizador ?? "?"}
                </Link>{" "}
                <span className="text-gray-600">
                  {v.numero_voo ?? "sem número"} · {v.origem}–{v.destino} ·{" "}
                  {textoLocal(v.embarque, v.origem)}
                </span>
                {v.passageiros && (
                  <span className="ml-1 text-xs text-gray-500">👤 {nomesPassageiros(v.passageiros, 2)}</span>
                )}
                <span className="ml-1 text-xs text-gray-500">— {v.incompleto}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
