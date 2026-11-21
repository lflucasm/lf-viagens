import assert from "node:assert/strict";
import { test } from "node:test";
import { acertarPassageiros, camposQueFaltam, contarPorNascimento, datasDeNascimento, normalizarData, normalizarDemanda, normalizarHorario } from "./_demanda.ts";

test("normalizarHorario: completa o zero e rejeita hora inválida", () => {
  assert.equal(normalizarHorario("7:10"), "07:10");
  assert.equal(normalizarHorario("15h55"), "15:55");
  assert.equal(normalizarHorario("25:00"), "");
  assert.equal(normalizarHorario("de manhã"), "");
});

test("normalizarData: só aceita dd/mm/aaaa que existe no calendário", () => {
  assert.equal(normalizarData("4/11/2026"), "04/11/2026");
  assert.equal(normalizarData("31/02/2026"), "");
  assert.equal(normalizarData("2026-11-14"), "");
});

test("normalizarDemanda: limpa campos e zera o que não faz sentido", () => {
  const d = normalizarDemanda({
    cia: " LATAM ",
    origem: "cgh",
    destino: "REC1",
    data: "14/11/2026",
    horario_saida: "15:55",
    horario_chegada: "19:05",
    numero_voo: "la 3045",
    tarifa: "light",
    milhas: 19890.4,
    taxa: "62.14",
    adultos: 1,
    criancas: -1,
    bebes: null,
    turbinada: true,
    observacoes: "",
  });
  assert.equal(d.cia, "latam");
  assert.equal(d.origem, "CGH");
  assert.equal(d.destino, "");
  assert.equal(d.numero_voo, "LA3045");
  assert.equal(d.tarifa, "LIGHT");
  assert.equal(d.milhas, 19890);
  assert.equal(d.taxa, 62.14);
  assert.equal(d.criancas, 0);
  assert.equal(d.bebes, 0);
  assert.equal(d.turbinada, true);
  assert.equal(normalizarDemanda({ turbinada: "sim" }).turbinada, false);
  assert.equal(normalizarDemanda({}).turbinada, false);
});

test("camposQueFaltam: lista o que impede a busca sozinha", () => {
  assert.deepEqual(camposQueFaltam(normalizarDemanda({ cia: "latam", origem: "SAO", destino: "REC", data: "14/11/2026", horario_saida: "15:55" })), []);
  assert.deepEqual(camposQueFaltam(normalizarDemanda({ cia: "x", origem: "SAO" })), ["companhia", "destino", "data", "horário de saída"]);
});

test("ida e volta: normaliza o trecho de volta e exige o horário dele", () => {
  const ida = { cia: "latam", origem: "SSA", destino: "RIO", data: "22/01/2027", horario_saida: "9:25" };
  const d = normalizarDemanda({ ...ida, data_volta: "25/1/2027", horario_saida_volta: "21:05", horario_chegada_volta: "23h05", tarifa_volta: "light" });
  assert.equal(d.data_volta, "25/01/2027");
  assert.equal(d.horario_chegada_volta, "23:05");
  assert.equal(d.tarifa_volta, "LIGHT");
  assert.deepEqual(camposQueFaltam(d), []);
  assert.deepEqual(camposQueFaltam(normalizarDemanda({ ...ida, data_volta: "25/01/2027" })), ["horário de saída da volta"]);
  assert.equal(normalizarDemanda(ida).data_volta, "");
});

const HOJE = new Date(2026, 10, 7);
const contar = (textos: string[], voo = "27/03/2027") => contarPorNascimento(datasDeNascimento(textos, HOJE), voo, HOJE);

test("contarPorNascimento: classifica pela idade no dia do voo", () => {
  const texto = `Renan expedito lacerda rodrigues
29/10/1986
378812508/01

Luana maria dos santos rodrigues
24/04/1991
049009053/21

Elisa dos santos rodrigues
11/11/2016
520064618/93

Ellen dos santos rodrigues
17/02/2011
486924158/71

Isaac dos santos rodrigues
15/08/2025
118362188/42`;
  assert.deepEqual(contar([texto]), { adultos: 3, criancas: 1, bebes: 1 });
  // Faz 2 anos antes do voo: já é criança.
  assert.deepEqual(contar(["10/01/2025"], "10/01/2027"), { adultos: 0, criancas: 1, bebes: 0 });
  // Data futura (voo) e data de emissão de documento não contam; sem nascimento → null.
  assert.equal(contar(["voo 27/03/2027", "RG emissão 02/03/2015"]), null);
});

test("datasDeNascimento: lê a data escrita de vários jeitos", () => {
  const textos = [
    "Renan Expedito 29/10/86",
    "Luana 24.04.1991",
    "Elisa 11-11-16",
    "Ellen 17 02 2011",
    "Isaac 15082025",
    "Maria nascida em 3 de março de 1950",
    "José 20 dez. 80",
    "CPF 111.000.006-58, RG 776977449, tel (11) 98765-4321, CPF 11100000658",
  ];
  assert.deepEqual(datasDeNascimento(textos, HOJE), [
    "29/10/1986", "24/04/1991", "11/11/2016", "17/02/2011", "15/08/2025", "03/03/1950", "20/12/1980",
  ]);
});
test("acertarPassageiros: datas mandam em criança/bebê, total do print cobre adulto sem data", () => {
  const hoje = new Date(2026, 10, 7);
  const base = normalizarDemanda({ data: "27/03/2027", adultos: 1 });
  // Print leu 1 adulto, texto tem 3 adultos + 1 criança + 1 bebê.
  const d = acertarPassageiros(base, ["29/10/1986", "24/04/1991", "11/11/2016", "17/02/2011", "15/08/2025"], hoje);
  assert.deepEqual([d.adultos, d.criancas, d.bebes], [3, 1, 1]);
  // Print diz 5, texto só tem a data do bebê: 4 adultos + 1 bebê.
  const e = acertarPassageiros({ ...base, adultos: 5 }, ["15/08/2025"], hoje);
  assert.deepEqual([e.adultos, e.criancas, e.bebes], [4, 0, 1]);
  // Sem data no texto: fica o que o print disse.
  assert.equal(acertarPassageiros(base, [], hoje), base);
});
