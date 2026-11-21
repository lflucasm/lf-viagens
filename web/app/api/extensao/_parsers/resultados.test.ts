/**
 * node --test web/app/api/extensao/_parsers/resultados.test.ts
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { PARSERS_RESULTADOS } from "./resultados.ts";

const fx = (nome: string) =>
  JSON.parse(readFileSync(new URL(`./__fixtures__/${nome}.json`, import.meta.url), "utf8"));

test("latam: extrai voos com milhas, taxa e chave", () => {
  const voos = PARSERS_RESULTADOS.latam(fx("latam-resultados"));
  assert.equal(voos.length, 2);
  assert.deepEqual(voos[0], {
    chave: "GRU-REC-0705-1010",
    origem: "GRU",
    destino: "REC",
    dataIda: "2026-12-12",
    horaPartida: "07:05",
    horaChegada: "10:10",
    milhas: 22664, // menor brand economy
    taxa: 35.75,
    escalas: 0,
  });
  assert.equal(voos[1].milhas, 118719);
  assert.equal(voos[1].escalas, 1);
});

test("azpm: usa points.value e a fee da recomendação", () => {
  const voos = PARSERS_RESULTADOS.azpm(fx("azpm-resultados"));
  assert.equal(voos.length, 2);
  assert.deepEqual(voos[0], {
    chave: "GRU-BCN-1825-0900",
    origem: "GRU",
    destino: "BCN",
    dataIda: "2026-12-12",
    horaPartida: "18:25",
    horaChegada: "09:00",
    milhas: 304500,
    taxa: 68.61,
    escalas: 0,
  });
  assert.equal(voos[1].milhas, 206000);
  assert.equal(voos[1].escalas, 1);
});

test("smiles: pega a tarifa SMILES_CLUB e a costTax", () => {
  const voos = PARSERS_RESULTADOS.smiles(fx("smiles-resultados"));
  assert.equal(voos.length, 2);
  assert.deepEqual(voos[0], {
    chave: "GRU-REC-1325-1630",
    origem: "GRU",
    destino: "REC",
    dataIda: "2026-12-12",
    horaPartida: "13:25",
    horaChegada: "16:30",
    milhas: 40600, // type SMILES_CLUB, não os 42700 do SMILES nem 35000 do TIER
    taxa: 35.75,
    escalas: 0,
  });
  assert.equal(voos[1].milhas, 60100);
  assert.equal(voos[1].escalas, 1);
});

test("smiles: sem tarifa clube, cai na SMILES (nunca na SMILES_MONEY)", () => {
  const payload = fx("smiles-resultados") as { requestedFlightSegmentList: { flightList: { fareList: { type: string }[] }[] }[] };
  for (const seg of payload.requestedFlightSegmentList)
    for (const f of seg.flightList) f.fareList = f.fareList.filter((x) => x.type !== "SMILES_CLUB");
  const voos = PARSERS_RESULTADOS.smiles(payload);
  assert.equal(voos[0].milhas, 42700);
  assert.equal(voos[1].milhas, 65300);
});

test("azul: amountLevel 1 = pontos cheios; taxa = taxesAndFees + convenienceFee", () => {
  const voos = PARSERS_RESULTADOS.azul(fx("azul-resultados"));
  assert.equal(voos.length, 2);
  assert.deepEqual(voos[0], {
    chave: "GRU-REC-0500-0800",
    origem: "GRU",
    destino: "REC",
    dataIda: "2026-12-12",
    horaPartida: "05:00",
    horaChegada: "08:00",
    milhas: 128000, // points.amount, não o discountedAmount 115200
    milhasTitular: 115200, // desconto do titular ("DiscountForContactPax")
    taxa: 75.65, // 35.75 + 39.9
    escalas: 0,
  });
});

test("azul: sem desconto aplicado → sem milhasTitular", () => {
  const payload = fx("azul-resultados");
  for (const t of payload.data.trips)
    for (const j of t.journeys)
      for (const f of j.fares)
        for (const pp of f.paxPoints) for (const l of pp.levels) delete l.points.discount;
  const voos = PARSERS_RESULTADOS.azul(payload);
  assert.equal(voos[0].milhas, 128000);
  assert.equal(voos[0].milhasTitular, undefined);
});

test("payload vazio / lixo → lista vazia, sem lançar", () => {
  for (const cia of ["latam", "azpm", "smiles", "azul"] as const) {
    assert.deepEqual(PARSERS_RESULTADOS[cia]({}), []);
    assert.deepEqual(PARSERS_RESULTADOS[cia](null), []);
    assert.deepEqual(PARSERS_RESULTADOS[cia]("nada"), []);
  }
});
