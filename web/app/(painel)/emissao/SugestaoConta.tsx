"use client";

import { useState } from "react";
import { INPUT_CLASSE } from "@/components/CadastroSecao";
import { BotaoCopiar } from "@/components/BotaoCopiar";
import { EstadoVazio } from "@/components/EstadoVazio";
import { sugerirContas, type ContaEmissao, type Prioridade } from "@/lib/sugestaoConta";

const PROGRAMAS = ["LATAM Pass", "Smiles"];
const milhar = (n: number) => n.toLocaleString("pt-BR");
const ddmmaa = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const soDigitos = (s: string) => s.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
const mascaraMilhar = (s: string) => (soDigitos(s) ? Number(soDigitos(s)).toLocaleString("pt-BR") : "");

const ROTULO: Record<Prioridade, { texto: string; classe: string }> = {
  otima: { texto: "Ótima", classe: "border-green-200 bg-green-50 text-green-700" },
  boa: { texto: "Boa", classe: "border-amber-200 bg-amber-50 text-amber-700" },
  media: { texto: "Média", classe: "border-amber-200 bg-amber-50 text-amber-700" },
  baixa: { texto: "Baixa", classe: "border-gray-300 bg-gray-100 text-gray-600" },
  sem_saldo: { texto: "Sem saldo", classe: "border-red-200 bg-red-50 text-red-700" },
};

export function SugestaoConta({ contas, hoje, semSaldo }: { contas: ContaEmissao[]; hoje: string; semSaldo: number }) {
  const [programa, setPrograma] = useState("LATAM Pass");
  const [milhas, setMilhas] = useState("");
  const [adultos, setAdultos] = useState("1");
  const [criancas, setCriancas] = useState("0");
  const [bebes, setBebes] = useState("0");
  const [busca, setBusca] = useState("");

  const qtdMilhas = Number(soDigitos(milhas)) || 0;
  // Conservador: bebê conta CPF na LATAM (confirmado) e aqui também na Smiles (não confirmado).
  const cpfs = (Number(adultos) || 0) + (Number(criancas) || 0) + (Number(bebes) || 0);
  const pronto = qtdMilhas > 0 && cpfs > 0;

  const q = busca.trim().toLowerCase();
  const lista = pronto
    ? sugerirContas(contas, { programa, milhas: qtdMilhas, cpfs }, hoje).filter(
        (s) => !q || s.titular.toLowerCase().includes(q),
      )
    : [];
  const utilizaveis = lista.filter((s) => s.prioridade !== "sem_saldo");

  const numero = (rotulo: string, valor: string, set: (v: string) => void) => (
    <label className="block text-sm">
      <span className="text-xs text-gray-500">{rotulo}</span>
      <input
        type="number"
        min={0}
        max={9}
        inputMode="numeric"
        value={valor}
        onChange={(e) => set(e.target.value)}
        className={`${INPUT_CLASSE} text-right tabular-nums`}
      />
    </label>
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-lg border border-gray-200 bg-white/90 p-4 sm:grid-cols-2 lg:grid-cols-6">
        <label className="block text-sm">
          <span className="text-xs text-gray-500">Programa</span>
          <select value={programa} onChange={(e) => setPrograma(e.target.value)} className={INPUT_CLASSE}>
            {PROGRAMAS.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm lg:col-span-2">
          <span className="text-xs text-gray-500">Milhas necessárias (total)</span>
          <input
            inputMode="numeric"
            value={milhas}
            placeholder="ex.: 100.000"
            onChange={(e) => setMilhas(mascaraMilhar(e.target.value))}
            className={`${INPUT_CLASSE} text-right tabular-nums`}
          />
        </label>
        {numero("Adultos", adultos, setAdultos)}
        {numero("Crianças", criancas, setCriancas)}
        {numero("Bebês", bebes, setBebes)}
        <p className="text-xs text-gray-500 sm:col-span-2 lg:col-span-6">
          CPFs consumidos: <b className="tabular-nums">{cpfs}</b>. Bebê conta CPF na LATAM; na Smiles também contamos,
          por segurança.
        </p>
      </div>

      {!pronto ? (
        <EstadoVazio titulo="Informe as milhas e os passageiros">
          As contas com saldo aparecem aqui, da que melhor encaixa pra a que menos serve.
        </EstadoVazio>
      ) : (
        <section className="space-y-2">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <h2 className="font-semibold">
              {utilizaveis.length} {utilizaveis.length === 1 ? "conta serve" : "contas servem"} em {programa}
            </h2>
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar titular"
              aria-label="Buscar titular"
              className={`${INPUT_CLASSE} max-w-xs`}
            />
          </div>

          {lista.length === 0 ? (
            <EstadoVazio titulo="Nenhuma conta encontrada">
              {q ? "Nenhum titular bate com essa busca." : `Não há conta ${programa} com saldo.`}
            </EstadoVazio>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white/90">
              <table className="w-full min-w-[820px] text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                    <th className="p-2">Titular</th>
                    <th className="p-2 text-right">Saldo</th>
                    <th className="p-2 text-right">Sobra</th>
                    <th className="p-2">CPFs depois</th>
                    <th className="p-2">Clube</th>
                    <th className="p-2">Encaixe</th>
                    <th className="p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {lista.map((s) => {
                    const semSaldoConta = s.prioridade === "sem_saldo";
                    const r = ROTULO[s.prioridade];
                    return (
                      <tr key={s.id} className={`border-b border-gray-100 last:border-0 ${semSaldoConta ? "opacity-50" : ""}`}>
                        <td className="p-2 font-medium">{s.titular}</td>
                        <td className="p-2 text-right tabular-nums">
                          {milhar(s.saldo)}
                          {s.cpm != null && (
                            <div className="text-xs text-gray-500">
                              CPM {s.cpm.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </div>
                          )}
                        </td>
                        <td className={`p-2 text-right tabular-nums ${semSaldoConta ? "text-red-700" : ""}`}>
                          {semSaldoConta ? `faltam ${milhar(-s.sobra)}` : milhar(s.sobra)}
                        </td>
                        <td className="p-2 text-xs">
                          <span className={`tabular-nums ${s.estoura ? "font-medium text-red-700" : s.cpfsDepois <= 2 ? "text-amber-700" : ""}`}>
                            {Math.max(0, s.cpfsDepois)} livres
                          </span>
                          <span className="text-gray-500">
                            {" "}
                            ({s.cpfUsados}/{s.cpfLimite} usados)
                          </span>
                          {s.estoura && (
                            <div className="text-red-700">Estoura {-s.cpfsDepois}: pode bloquear a conta</div>
                          )}
                          {s.proximaLiberacao && (
                            <div className="text-gray-500">
                              {s.proximaLiberacao.qtd} libera{s.proximaLiberacao.qtd > 1 ? "m" : ""} em{" "}
                              {ddmmaa(s.proximaLiberacao.data)}
                            </div>
                          )}
                        </td>
                        <td className="p-2 text-xs">{s.clubeAtivo ? "ativo" : <span className="text-gray-400">—</span>}</td>
                        <td className="p-2">
                          <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${r.classe}`}>{r.texto}</span>
                        </td>
                        <td className="p-2 text-right">
                          {!semSaldoConta && <BotaoCopiar texto={s.titular} rotulo="Copiar nome" />}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-gray-500">
            Encaixe: ótima = sobra até 2.000 (zera a conta); boa = sobra acima de 10.000; baixa = sobra de 3.000 a
            10.000. Quem estoura os CPFs desce na lista. Bloqueio de conta não entra: a Volly não registra.
            {semSaldo > 0 && ` ${semSaldo} contas LATAM/Smiles sem saldo ficam ocultas.`}
          </p>
        </section>
      )}
    </div>
  );
}
