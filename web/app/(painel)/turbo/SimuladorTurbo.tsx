"use client";

import { useState } from "react";
import { INPUT_CLASSE } from "@/components/CadastroSecao";

type Titular = { id: string; nome: string; saldoLivelo: number; cpmLivelo: number | null };

const milhar = (n: number) => Math.round(n).toLocaleString("pt-BR");
const reais = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const decimal = (v: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num = (s: string) => Number(s.replace(/\./g, "").replace(",", ".")) || 0;

// Máscaras: o campo guarda o texto já formatado ("100.000", "1.234,56"); num() lê de volta.
const digitos = (s: string) => s.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
const mascaraInteiro = (s: string) => (digitos(s) ? Number(digitos(s)).toLocaleString("pt-BR") : "");
const mascaraDecimal = (s: string) => (digitos(s) ? decimal(Number(digitos(s)) / 100) : "");

/** Simula uma transferência Livelo → LATAM: parte do estoque, parte comprada no carrinho. */
export function SimuladorTurbo({ titulares }: { titulares: Titular[] }) {
  const [id, setId] = useState(titulares[0]?.id ?? "");
  const [quantidade, setQuantidade] = useState("100.000");
  const [bonus, setBonus] = useState("30");
  const [comprados, setComprados] = useState("");
  const [valorCompra, setValorCompra] = useState("");
  const [cpmManual, setCpmManual] = useState("");

  const t = titulares.find((x) => x.id === id);
  const base = num(quantidade);
  const doCarrinho = Math.min(num(comprados), base);
  const doEstoque = base - doCarrinho;
  const cpmEstoque = cpmManual ? num(cpmManual) : (t?.cpmLivelo ?? 0);
  const custoEstoque = (doEstoque * cpmEstoque) / 1000;
  const custoCarrinho = num(valorCompra);
  const custo = custoEstoque + custoCarrinho;
  const extra = (base * num(bonus)) / 100;
  const creditado = base + extra;
  const faltaSaldo = t ? doEstoque - t.saldoLivelo : 0;

  const campo = (
    rotulo: string,
    valor: string,
    set: (v: string) => void,
    mascara: (v: string) => string,
    { dica, prefixo, placeholder }: { dica?: string; prefixo?: string; placeholder?: string } = {},
  ) => (
    <label className="block text-sm">
      <span className="text-xs text-gray-500">{rotulo}</span>
      <span className="relative block">
        {prefixo && (
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-500">{prefixo}</span>
        )}
        <input
          inputMode="numeric"
          value={valor}
          placeholder={placeholder}
          onChange={(e) => set(mascara(e.target.value))}
          className={`${INPUT_CLASSE} text-right tabular-nums ${prefixo ? "pl-10" : ""}`}
        />
      </span>
      {dica && <span className="text-xs text-gray-500">{dica}</span>}
    </label>
  );

  return (
    <section className="space-y-2">
      <h2 className="font-semibold">Simulador de transferência</h2>
      <div className="grid gap-4 rounded-lg border border-gray-200 bg-white/90 p-4 lg:grid-cols-2">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm sm:col-span-2">
            <span className="text-xs text-gray-500">Titular</span>
            <select value={id} onChange={(e) => setId(e.target.value)} className={INPUT_CLASSE}>
              {titulares.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.nome} — Livelo {milhar(x.saldoLivelo)}
                </option>
              ))}
            </select>
          </label>
          {campo("Pontos Livelo a transferir", quantidade, setQuantidade, mascaraInteiro)}
          <label className="block text-sm">
            <span className="text-xs text-gray-500">Bônus (%)</span>
            <input inputMode="numeric" list="bonus-turbo" value={bonus} onChange={(e) => setBonus(digitos(e.target.value).slice(0, 3))} className={`${INPUT_CLASSE} text-right tabular-nums`} />
            <datalist id="bonus-turbo">
              <option value="30" />
              <option value="35" />
              <option value="80" />
            </datalist>
          </label>
          {campo("Pontos comprados no carrinho", comprados, setComprados, mascaraInteiro, { placeholder: "0", dica: "vazio = só estoque" })}
          {campo("Valor pago no carrinho", valorCompra, setValorCompra, mascaraDecimal, { prefixo: "R$", placeholder: "0,00" })}
          {campo("CPM do estoque Livelo", cpmManual, setCpmManual, mascaraDecimal, {
            prefixo: "R$",
            placeholder: t?.cpmLivelo != null ? decimal(t.cpmLivelo) : "0,00",
            dica: t?.cpmLivelo != null ? `vazio = CPM da Volly (${decimal(t.cpmLivelo)})` : "conta sem CPM na Volly",
          })}
        </div>
        <dl className="grid grid-cols-2 content-start gap-x-4 gap-y-2 text-sm">
          <dt className="text-gray-500">Do estoque</dt>
          <dd className="text-right tabular-nums">
            {milhar(doEstoque)} pts · {reais(custoEstoque)}
          </dd>
          <dt className="text-gray-500">Do carrinho</dt>
          <dd className="text-right tabular-nums">
            {milhar(doCarrinho)} pts · {reais(custoCarrinho)}
            {doCarrinho > 0 && <span className="text-gray-500"> (CPM {decimal((custoCarrinho / doCarrinho) * 1000)})</span>}
          </dd>
          <dt className="text-gray-500">Custo total</dt>
          <dd className="text-right font-medium tabular-nums">{reais(custo)}</dd>
          <dt className="text-gray-500">Milhas base / bônus</dt>
          <dd className="text-right tabular-nums">
            {milhar(base)} + {milhar(extra)}
          </dd>
          <dt className="text-gray-500">Total creditado</dt>
          <dd className="text-right font-medium tabular-nums">{milhar(creditado)} mi</dd>
          <dt className="text-gray-500">CPM sobre milhas base</dt>
          <dd className="text-right tabular-nums">{base ? decimal((custo / base) * 1000) : "—"}</dd>
          <dt className="text-gray-500">CPM real (sobre creditado)</dt>
          <dd className="text-right text-lg font-semibold tabular-nums">{creditado ? decimal((custo / creditado) * 1000) : "—"}</dd>
          {faltaSaldo > 0 && (
            <dd className="col-span-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              Saldo Livelo insuficiente: faltam {milhar(faltaSaldo)} pontos no estoque. Aumente a compra no carrinho.
            </dd>
          )}
        </dl>
      </div>
    </section>
  );
}
