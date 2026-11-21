import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const reais = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dia = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

// Dias até o próximo vencimento (mês de 30 dias: dia 31 vence no último dia).
function diasParaVencer(diaVenc: number, hoje: Date) {
  const alvo = (ano: number, mes: number) =>
    new Date(ano, mes, Math.min(diaVenc, new Date(ano, mes + 1, 0).getDate()));
  let v = alvo(hoje.getFullYear(), hoje.getMonth());
  if (v < hoje) v = alvo(hoje.getFullYear(), hoje.getMonth() + 1);
  return Math.round((v.getTime() - hoje.getTime()) / 86_400_000);
}

const EVENTO: Record<string, (de: string | null, para: string | null) => string> = {
  ativou: () => "ativou o clube",
  desativou: () => "saiu do clube",
  custo: (de, para) => `custo ${de ?? "?"} → ${para ?? "?"}`,
  pontos: (de, para) => `pontos/mês ${de ?? "?"} → ${para ?? "?"}`,
  vencimento: (de, para) => `vencimento dia ${de ?? "?"} → ${para ?? "?"}`,
};

export default async function PaginaClubes() {
  const supabase = await createClient();
  const [{ data: clubes }, { data: eventos }] = await Promise.all([
    supabase.from("clubes").select("*").order("titular"),
    supabase.from("clubes_eventos").select("*").order("em", { ascending: false }).limit(40),
  ]);
  const todos = clubes ?? [];
  const ativos = todos.filter((c) => c.ativo);

  const agora = new Date();
  const hoje = new Date(agora.toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  hoje.setHours(0, 0, 0, 0);

  const programas = [...new Set(todos.map((c) => c.programa))].sort();
  const titulares = [...new Set(todos.map((c) => c.titular))];
  const celula = (t: string, p: string) => todos.find((c) => c.titular === t && c.programa === p);

  const proximos = ativos
    .filter((c) => c.dia_venc)
    .map((c) => ({ c, dias: diasParaVencer(c.dia_venc!, hoje) }))
    .filter((x) => x.dias <= 7)
    .sort((a, b) => a.dias - b.dias);

  const custo = ativos.reduce((s, c) => s + Number(c.custo_mensal ?? 0), 0);
  const pontos = ativos.reduce((s, c) => s + (c.pontos_mes ?? 0), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Clubes</h1>
        <p className="text-sm text-gray-500">
          Espelho dos clubes cadastrados na Volly (atualiza a cada ciclo). O histórico de mudanças
          começa em 18/11/2026 — a Volly só guarda o estado atual.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[
          ["Clubes ativos", String(ativos.length)],
          ["Custo mensal", reais(custo)],
          ["Pontos por mês", pontos.toLocaleString("pt-BR")],
        ].map(([rotulo, valor]) => (
          <div key={rotulo} className="rounded-lg border border-gray-200 bg-white/90 p-4">
            <p className="text-xs text-gray-500">{rotulo}</p>
            <p className="text-xl font-semibold">{valor}</p>
          </div>
        ))}
      </div>

      <section className="space-y-2">
        <h2 className="font-semibold">Vencem nos próximos 7 dias</h2>
        {proximos.length === 0 ? (
          <p className="text-sm text-gray-500">Nenhum vencimento na semana.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                  <th className="p-2">Quando</th>
                  <th className="p-2">Titular</th>
                  <th className="p-2">Programa</th>
                  <th className="p-2 text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {proximos.map(({ c, dias }) => (
                  <tr key={c.conta_id} className="border-b border-gray-100 last:border-0">
                    <td className={`whitespace-nowrap p-2 ${dias <= 1 ? "font-medium text-amber-700" : ""}`}>
                      {dias === 0 ? "hoje" : dias === 1 ? "amanhã" : `em ${dias} dias`}
                      <span className="text-gray-500"> (dia {c.dia_venc})</span>
                    </td>
                    <td className="p-2">{c.titular}</td>
                    <td className="p-2">{c.programa}</td>
                    <td className="whitespace-nowrap p-2 text-right tabular-nums">
                      {c.custo_mensal != null ? reais(Number(c.custo_mensal)) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">Titular × programa</h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                <th className="p-2">Titular</th>
                {programas.map((p) => (
                  <th key={p} className="p-2">
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {titulares.map((t) => (
                <tr key={t} className="border-b border-gray-100 last:border-0">
                  <td className="p-2 font-medium">{t}</td>
                  {programas.map((p) => {
                    const c = celula(t, p);
                    return (
                      <td key={p} className="p-2 align-top">
                        {!c ? (
                          <span className="text-gray-300">—</span>
                        ) : c.ativo ? (
                          <span className="inline-block rounded border border-green-200 bg-green-50 px-2 py-0.5 text-xs text-green-700">
                            dia {c.dia_venc} · {c.custo_mensal != null ? reais(Number(c.custo_mensal)) : "?"}
                            {c.pontos_mes ? ` · ${(c.pontos_mes / 1000).toLocaleString("pt-BR")}k` : ""}
                          </span>
                        ) : (
                          <span className="inline-block rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-500">
                            saiu
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">Últimas mudanças</h2>
        {(eventos ?? []).length === 0 ? (
          <p className="text-sm text-gray-500">Nenhuma mudança registrada desde a primeira carga.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {(eventos ?? []).map((e) => (
              <li key={e.id}>
                <span className="text-gray-500">{dia(e.em)}</span> — {e.titular} · {e.programa}:{" "}
                {(EVENTO[e.tipo] ?? (() => e.tipo))(e.de, e.para)}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
