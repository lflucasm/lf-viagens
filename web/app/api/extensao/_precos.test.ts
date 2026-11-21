/**
 * Testes das funções puras de precificação. Rodar com:
 *   node --test web/app/api/extensao/_precos.test.ts
 * (Node 23+ tira os tipos sozinho; não precisa de framework.)
 *
 * `buscarFaixas` / `lerConfig` fazem I/O e não são cobertas aqui — vão no
 * teste de integração pós-deploy da Fase 1.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  aplicarMarkup,
  custoVoo,
  cambioBRL,
  ehCia,
  MAPA_CIA_PROGRAMA,
  mesmoPrograma,
  normPrograma,
  parseJanela,
  resolverMilheiro,
  resolverMilheiroCascata,
  taxaEmBRL,
  type Faixas,
  type FaixasPorJanela,
  type ConfigPrecos,
} from "./_precos.ts";

const semConfig: ConfigPrecos = { overrides: new Map(), markup: { tipo: "pct", valor: 0, escopo: "venda" } };

const faixas: Faixas = {
  window: "7d",
  quantityFloors: [40000, 100000],
  bandStep: 10000,
  rows: [
    {
      programId: 3,
      programName: "LATAM",
      cells: [
        { quantityFloor: 40000, avgPrice: 19, offerCount: 5 },
        { quantityFloor: 100000, avgPrice: 18, offerCount: 0 },
      ],
      overallAvgPrice: 18.5,
      totalOfferCount: 5,
    },
  ],
};

test("parseJanela: default 24h, aceita 7d e 30d", () => {
  assert.equal(parseJanela(null), "24h");
  assert.equal(parseJanela("qualquer"), "24h");
  assert.equal(parseJanela("7d"), "7d");
  assert.equal(parseJanela("30d"), "30d");
});

test("resolverMilheiro: faixa que contém as milhas", () => {
  const r = resolverMilheiro("LATAM", 45000, faixas, semConfig);
  assert.deepEqual(r, { valor: 19, fonte: "faixa" });
});

test("resolverMilheiro: faixa sem oferta cai na média geral", () => {
  const r = resolverMilheiro("LATAM", 102000, faixas, semConfig);
  assert.deepEqual(r, { valor: 18.5, fonte: "geral" });
});

test("resolverMilheiro: programa sem row nenhuma → sem preço", () => {
  const r = resolverMilheiro("SMILES", 30000, faixas, semConfig);
  assert.deepEqual(r, { valor: null, fonte: null });
});

test("resolverMilheiro: override manual vence a faixa", () => {
  const config: ConfigPrecos = { overrides: new Map([["LATAM", 15]]), markup: semConfig.markup };
  const r = resolverMilheiro("LATAM", 45000, faixas, config);
  assert.deepEqual(r, { valor: 15, fonte: "override" });
});

test("resolverMilheiro: sem faixas (felip-ai fora do ar) mas com override", () => {
  const config: ConfigPrecos = { overrides: new Map([["LATAM", 21]]), markup: semConfig.markup };
  assert.deepEqual(resolverMilheiro("LATAM", 45000, null, config), { valor: 21, fonte: "override" });
  assert.deepEqual(resolverMilheiro("SMILES", 45000, null, config), { valor: null, fonte: null });
});

test("resolverMilheiro: casa programName do felip-ai com WORD JOINER (U+2060) no começo", () => {
  const f: Faixas = {
    window: "7d",
    quantityFloors: [40000],
    bandStep: 10000,
    rows: [
      {
        programId: 20,
        programName: "\u2060AZUL/TUDO AZUL",
        cells: [{ quantityFloor: 40000, avgPrice: 14.5, offerCount: 3 }],
        overallAvgPrice: 14.5,
        totalOfferCount: 3,
      },
    ],
  };
  const r = resolverMilheiro(MAPA_CIA_PROGRAMA.azul, 45000, f, semConfig);
  assert.deepEqual(r, { valor: 14.5, fonte: "faixa" });
});

test("resolverMilheiro: override casa mesmo com zero-width / caixa diferente", () => {
  const config: ConfigPrecos = {
    overrides: new Map([[normPrograma(" azul/tudo azul "), 12]]),
    markup: semConfig.markup,
  };
  const r = resolverMilheiro("\u2060AZUL/TUDO AZUL", 45000, null, config);
  assert.deepEqual(r, { valor: 12, fonte: "override" });
});

test("resolverMilheiroCascata: acha na janela pedida (24h), não precisa alargar", () => {
  const faixasPorJanela: FaixasPorJanela = { "24h": { faixas, stale: false } };
  const r = resolverMilheiroCascata("LATAM", 45000, faixasPorJanela, "24h", semConfig);
  assert.deepEqual(r, { valor: 19, fonte: "faixa", janelaUsada: "24h", stale: false });
});

test("resolverMilheiroCascata: sem oferta em 24h (mercado fino) alarga pra 7d", () => {
  const azulTudoAzul: Faixas = {
    window: "7d",
    quantityFloors: [40000],
    bandStep: 10000,
    rows: [
      {
        programId: 20,
        programName: "⁠AZUL/TUDO AZUL",
        cells: [{ quantityFloor: 40000, avgPrice: 14.5, offerCount: 3 }],
        overallAvgPrice: 14.5,
        totalOfferCount: 3,
      },
    ],
  };
  const faixasPorJanela: FaixasPorJanela = {
    "24h": { faixas: { ...azulTudoAzul, rows: [] }, stale: false }, // sem oferta hoje
    "7d": { faixas: azulTudoAzul, stale: false },
  };
  const r = resolverMilheiroCascata(MAPA_CIA_PROGRAMA.azul, 45000, faixasPorJanela, "24h", semConfig);
  assert.deepEqual(r, { valor: 14.5, fonte: "faixa", janelaUsada: "7d", stale: false });
});

test("resolverMilheiroCascata: sem oferta em nenhuma janela → sem preço", () => {
  const faixasPorJanela: FaixasPorJanela = {
    "24h": { faixas: null, stale: false },
    "7d": { faixas: null, stale: false },
    "30d": { faixas: null, stale: false },
  };
  const r = resolverMilheiroCascata("SMILES", 30000, faixasPorJanela, "24h", semConfig);
  assert.deepEqual(r, { valor: null, fonte: null, janelaUsada: null, stale: false });
});

test("resolverMilheiroCascata: override vence sem precisar de nenhuma faixa", () => {
  const config: ConfigPrecos = { overrides: new Map([["LATAM", 21]]), markup: semConfig.markup };
  const r = resolverMilheiroCascata("LATAM", 45000, {}, "24h", config);
  assert.deepEqual(r, { valor: 21, fonte: "override", janelaUsada: null, stale: false });
});

test("MAPA_CIA_PROGRAMA.azpm usa o nome real de produção", () => {
  assert.equal(MAPA_CIA_PROGRAMA.azpm, "AZUL INTERLINE/AZUL PELO MUNDO");
});

test("custoVoo: milhas/1000 * milheiro + taxa", () => {
  assert.equal(custoVoo(45000, 19, 120), 975);
  assert.equal(custoVoo(30000, 18.5, 0), 555);
});

test("aplicarMarkup: pct, abs e zero", () => {
  assert.equal(aplicarMarkup(1000, { tipo: "pct", valor: 10, escopo: "venda" }), 1100);
  assert.equal(aplicarMarkup(1000, { tipo: "abs", valor: 50, escopo: "venda" }), 1050);
  assert.equal(aplicarMarkup(1000, { tipo: "pct", valor: 0, escopo: "venda" }), 1000);
  assert.equal(aplicarMarkup(999.999, { tipo: "pct", valor: 0, escopo: "venda" }), 1000);
});

test("internacionais: casam por apelido, sem confundir programas", () => {
  assert.ok(ehCia("copa") && ehCia("tap") && ehCia("iberia") && ehCia("aa"));
  assert.ok(!ehCia("toString"));
  assert.ok(mesmoPrograma("\u2060COPA/CONNECTMILES", MAPA_CIA_PROGRAMA.copa));
  assert.ok(mesmoPrograma("american airlines/aadvantage", MAPA_CIA_PROGRAMA.aa));
  assert.ok(mesmoPrograma("TAP", MAPA_CIA_PROGRAMA.tap));
  assert.ok(!mesmoPrograma("BRITISH/AVIOS", MAPA_CIA_PROGRAMA.iberia));
  assert.ok(!mesmoPrograma("LATAM", MAPA_CIA_PROGRAMA.tap));
  assert.ok(!mesmoPrograma("AZUL/TUDO AZUL", MAPA_CIA_PROGRAMA.azpm));
});

test("resolverMilheiro: programa internacional pelo apelido (faixa e override)", () => {
  const f: Faixas = {
    ...faixas,
    rows: [{ programId: 9, programName: "COPA/CONNECTMILES", cells: [], overallAvgPrice: 52.1, totalOfferCount: 2 }],
  };
  assert.deepEqual(resolverMilheiro(MAPA_CIA_PROGRAMA.copa, 20000, f, semConfig), { valor: 52, fonte: "geral" });
  const config: ConfigPrecos = { ...semConfig, overrides: new Map([["COPA/CONNECTMILES", 60]]) };
  assert.deepEqual(resolverMilheiro(MAPA_CIA_PROGRAMA.copa, 20000, f, config), { valor: 60, fonte: "override" });
});

test("taxaEmBRL: converte moeda estrangeira e recusa sem cotação", () => {
  assert.equal(taxaEmBRL(35.75, undefined, {}), 35.75);
  assert.equal(taxaEmBRL(35.75, "BRL", {}), 35.75);
  assert.equal(taxaEmBRL(40.1, "USD", { USD: 5.5 }), 220.55);
  assert.equal(taxaEmBRL(40.1, "EUR", { USD: 5.5 }), null);
});

test("cambioBRL: sem cotação ao vivo usa a estimativa fixa", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new Error("sem rede");
  }) as typeof fetch;
  try {
    const taxas = await cambioBRL(Date.now() + 10 ** 12);
    assert.ok(taxas.USD > 0 && taxas.EUR > 0 && taxas.GBP > 0);
  } finally {
    globalThis.fetch = original;
  }
});

test("cambioBRL: AwesomeAPI fora do ar usa a próxima fonte (cotação do dia)", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    if (String(url).includes("awesomeapi")) throw new Error("fora");
    return Response.json({ rates: { BRL: 5.7, EUR: 0.9, GBP: 0.75 } });
  }) as typeof fetch;
  try {
    const taxas = await cambioBRL(Date.now() + 2 * 10 ** 12);
    assert.equal(taxas.USD, 5.7);
    assert.ok(Math.abs(taxas.EUR - 6.3333) < 0.001);
  } finally {
    globalThis.fetch = original;
  }
});
