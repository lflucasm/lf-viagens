// node --experimental-strip-types --test lib/sugestaoConta.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { prioridadeDaSobra, sugerirContas } from "./sugestaoConta.ts";

const conta = (id, saldo, usados = 0, extra = {}) => ({
  id, titular: id, programa: "LATAM Pass", saldo, cpm: null, clubeAtivo: true,
  cpfUsados: usados, cpfLimite: 25, liberacoes: [], ...extra,
});

test("faixas de sobra (regra do Trademiles)", () => {
  assert.equal(prioridadeDaSobra(-1), "sem_saldo");
  assert.equal(prioridadeDaSobra(0), "otima");
  assert.equal(prioridadeDaSobra(2000), "otima");
  assert.equal(prioridadeDaSobra(2500), "media");
  assert.equal(prioridadeDaSobra(3000), "baixa");
  assert.equal(prioridadeDaSobra(10000), "baixa");
  assert.equal(prioridadeDaSobra(10001), "boa");
});

test("ordem: encaixe, CPF estourado desce, sem saldo por último, outro programa some", () => {
  const contas = [
    conta("sem-saldo", 50000),
    conta("boa", 120000),
    conta("otima-estoura", 101000, 24), // encaixe perfeito, mas 3 CPFs não cabem
    conta("otima", 100500, 5),
    conta("baixa", 105000),
    { ...conta("smiles", 100000), programa: "Smiles" },
  ];
  const r = sugerirContas(contas, { programa: "LATAM Pass", milhas: 100000, cpfs: 3 }, "2026-11-20");
  assert.deepEqual(r.map((x) => x.id), ["otima", "boa", "baixa", "otima-estoura", "sem-saldo"]);
  const estoura = r.find((x) => x.id === "otima-estoura");
  assert.equal(estoura.cpfsDepois, -2);
  assert.equal(estoura.estoura, true);
});

test("próxima liberação ignora datas passadas", () => {
  const c = conta("a", 1000, 3, { liberacoes: [{ data: "2026-01-01", qtd: 1 }, { data: "2027-07-26", qtd: 2 }] });
  const [r] = sugerirContas([c], { programa: "LATAM Pass", milhas: 500, cpfs: 1 }, "2026-11-20");
  assert.deepEqual(r.proximaLiberacao, { data: "2027-07-26", qtd: 2 });
});
