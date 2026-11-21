import { createClient } from "@/lib/supabase/server";
import { SimuladorTurbo } from "./SimuladorTurbo";

export const dynamic = "force-dynamic";

type Transf = { data: string; pontos: number; milhas: number; bonus: number; cpm_latam: number | null };
type Liberacao = { data: string; qtd: number };

const LOTE_PADRAO = 100_000; // transferência mensal típica (Livelo → LATAM)
const milhar = (n: number) => n.toLocaleString("pt-BR");
const reais = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const ddmmaa = (iso: string) => `${ddmm(iso)}/${iso.slice(0, 4)}`;
const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function chaveMes(ano: number, mes: number) {
  const d = new Date(ano, mes, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default async function PaginaTurbo() {
  const supabase = await createClient();
  const { data } = await supabase.from("turbo").select("*").order("titular");
  const todos = data ?? [];

  const hoje = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  const ano = hoje.getFullYear();
  const mes = hoje.getMonth();
  const ciclo = [-1, 0, 1].map((d) => ({ chave: chaveMes(ano, mes + d), rotulo: MES[(mes + d + 12) % 12], futuro: d > 0 }));
  const atual = ciclo[1].chave;
  const diasNoMes = new Date(ano, mes + 1, 0).getDate();
  const faltamDias = diasNoMes - hoje.getDate();
  const hojeIso = `${atual}-${String(hoje.getDate()).padStart(2, "0")}`;

  const linhas = todos.map((t) => {
    const transf = (t.transferencias as Transf[]) ?? [];
    const lib = ((t.liberacoes as Liberacao[]) ?? []).filter((l) => l.data > hojeIso);
    const doMes = transf.find((x) => x.data.startsWith(atual));
    const usoCpf = t.cpf_limite ? t.cpf_usados / t.cpf_limite : 0;
    const liveloCurto = !doMes && t.saldo_livelo < LOTE_PADRAO;
    const alertas: { nivel: "critico" | "atencao"; texto: string }[] = [];
    if (t.clube_ativo && !doMes && faltamDias <= 5)
      alertas.push({ nivel: "critico", texto: `transferência do mês não feita (faltam ${faltamDias}d)` });
    if (usoCpf >= 0.9) alertas.push({ nivel: "critico", texto: "CPFs quase esgotados" });
    else if (usoCpf >= 0.7) alertas.push({ nivel: "atencao", texto: "CPFs acima de 70%" });
    if (t.clube_ativo && liveloCurto)
      alertas.push({ nivel: "atencao", texto: `Livelo abaixo de ${milhar(LOTE_PADRAO)} (faltam ${milhar(LOTE_PADRAO - t.saldo_livelo)})` });
    return { t, transf, lib, doMes, usoCpf, alertas };
  });

  // Clube ativo e pendente primeiro, depois quem já transferiu, por último quem não tem clube.
  const peso = (l: (typeof linhas)[number]) => (!l.t.clube_ativo ? 2 : l.doMes ? 1 : 0);
  linhas.sort((a, b) => peso(a) - peso(b) || a.t.titular.localeCompare(b.t.titular, "pt-BR"));

  const ativos = linhas.filter((l) => l.t.clube_ativo);
  const feitas = ativos.filter((l) => l.doMes).length;
  const criticos = linhas.filter((l) => l.alertas.some((a) => a.nivel === "critico")).length;
  const cpfLivres = ativos.reduce((s, l) => s + Math.max(0, l.t.cpf_limite - l.t.cpf_usados), 0);
  const custo = ativos.reduce((s, l) => s + Number(l.t.custo_mensal ?? 0), 0);
  const ultimas = linhas
    .flatMap((l) => l.transf.map((x) => ({ ...x, titular: l.t.titular })))
    .sort((a, b) => b.data.localeCompare(a.data))
    .slice(0, 15);
  const atualizado = todos.reduce((m, t) => (t.atualizado_em > m ? t.atualizado_em : m), "");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Turbo LATAM</h1>
        <p className="text-sm text-gray-500">
          Clube LATAM Pass + Turbo e transferências Livelo → LATAM, lidos da Volly a cada ciclo. O ciclo do mês
          fica verde sozinho quando a transferência é lançada na Volly.
          {atualizado &&
            ` Atualizado ${new Date(atualizado).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}.`}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[
          ["Turbo ativo", String(ativos.length)],
          [`Transferidos em ${ciclo[1].rotulo}`, `${feitas} de ${ativos.length}`],
          ["Alertas críticos", String(criticos)],
          ["CPFs livres (ativos)", String(cpfLivres)],
          ["Custo mensal clubes", reais(custo)],
        ].map(([rotulo, valor]) => (
          <div key={rotulo} className="rounded-lg border border-gray-200 bg-white/90 p-4">
            <p className="text-xs text-gray-500">{rotulo}</p>
            <p className="text-xl font-semibold">{valor}</p>
          </div>
        ))}
      </div>

      <section className="space-y-2">
        <h2 className="font-semibold">Titulares</h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
          <table className="w-full min-w-[1100px] text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                <th className="p-2">Titular</th>
                <th className="p-2">Clube</th>
                <th className="p-2 text-right">Livelo</th>
                <th className="p-2 text-right">LATAM</th>
                <th className="p-2">Ciclo</th>
                <th className="p-2">Transferência do mês</th>
                <th className="p-2">CPFs</th>
                <th className="p-2">Alertas</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map(({ t, transf, lib, doMes, usoCpf, alertas }) => (
                <tr key={t.conta_id} className={`border-b border-gray-100 last:border-0 ${t.clube_ativo ? "" : "opacity-60"}`}>
                  <td className="p-2 font-medium">{t.titular}</td>
                  <td className="p-2 text-xs">
                    {t.clube_ativo ? (
                      <>
                        dia {t.dia_venc ?? "?"} · {t.custo_mensal != null ? reais(Number(t.custo_mensal)) : "?"}
                        {t.milhas_mes ? ` · ${milhar(t.milhas_mes)} mi` : ""}
                      </>
                    ) : (
                      <span className="text-gray-500">sem clube</span>
                    )}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {milhar(t.saldo_livelo)}
                    {t.cpm_livelo != null && <div className="text-xs text-gray-500">CPM {Number(t.cpm_livelo).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>}
                  </td>
                  <td className="p-2 text-right tabular-nums">{milhar(t.saldo_latam)}</td>
                  <td className="p-2">
                    <div className="flex gap-1">
                      {ciclo.map((c) => {
                        const x = transf.find((y) => y.data.startsWith(c.chave));
                        return (
                          <span
                            key={c.chave}
                            title={x ? `${ddmm(x.data)}: ${milhar(x.pontos)} pts → ${milhar(x.milhas)} mi (+${x.bonus}%)` : undefined}
                            className={`rounded border px-1.5 py-0.5 text-xs ${
                              x
                                ? "border-green-200 bg-green-50 text-green-700"
                                : c.futuro
                                  ? "border-gray-200 text-gray-400"
                                  : "border-gray-200 bg-gray-50 text-gray-500"
                            }`}
                          >
                            {x ? "✓ " : ""}
                            {c.rotulo}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                  <td className="p-2 text-xs">
                    {doMes ? (
                      <span className="text-green-700">
                        feita {ddmm(doMes.data)} · {milhar(doMes.milhas)} mi (+{doMes.bonus}%)
                      </span>
                    ) : t.clube_ativo ? (
                      <span className={faltamDias <= 5 ? "font-medium text-red-700" : ""}>
                        pendente · {faltamDias === 0 ? "último dia do mês" : `faltam ${faltamDias} dias`}
                      </span>
                    ) : (
                      <span className="text-gray-500">—</span>
                    )}
                  </td>
                  <td className="p-2 text-xs">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-200" aria-hidden="true">
                        <div
                          className={`h-full ${usoCpf >= 0.9 ? "bg-red-500" : usoCpf >= 0.7 ? "bg-amber-500" : "bg-green-500"}`}
                          style={{ width: `${Math.min(100, usoCpf * 100)}%` }}
                        />
                      </div>
                      <span className="tabular-nums">
                        {t.cpf_usados}/{t.cpf_limite}
                      </span>
                    </div>
                    {lib[0] && (
                      <div className="text-gray-500">
                        {lib[0].qtd} libera{lib[0].qtd > 1 ? "m" : ""} em {ddmmaa(lib[0].data)}
                      </div>
                    )}
                  </td>
                  <td className="p-2 text-xs">
                    {alertas.length === 0 ? (
                      <span className="text-gray-400">—</span>
                    ) : (
                      <ul className="space-y-0.5">
                        {alertas.map((a) => (
                          <li key={a.texto} className={a.nivel === "critico" ? "text-red-700" : "text-amber-700"}>
                            {a.texto}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-500">
          CPFs usados/limite vêm da Volly (campo mantido pela equipe). A data de liberação conta 12 meses a partir de
          cada emissão lançada na Volly, então só enxerga emissões feitas desde que a agência passou a usar a Volly.
        </p>
      </section>

      <SimuladorTurbo
        titulares={ativos.map(({ t }) => ({
          id: t.conta_id,
          nome: t.titular,
          saldoLivelo: t.saldo_livelo,
          cpmLivelo: t.cpm_livelo != null ? Number(t.cpm_livelo) : null,
        }))}
      />

      <section className="space-y-2">
        <h2 className="font-semibold">Últimas transferências Livelo → LATAM</h2>
        {ultimas.length === 0 ? (
          <p className="text-sm text-gray-500">Nenhuma transferência nos últimos 12 meses.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {ultimas.map((x, i) => (
              <li key={i}>
                <span className="text-gray-500">{ddmmaa(x.data)}</span> — {x.titular}: {milhar(x.pontos)} pts →{" "}
                {milhar(x.milhas)} mi (+{x.bonus}%)
                {x.cpm_latam != null && ` · CPM ${Number(x.cpm_latam).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
