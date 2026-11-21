// node --experimental-strip-types --test lib/mensagemPassageiro.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mensagemPassageiro } from "./tipos.ts";

const voo = {
  cia: "GOL", numero_voo: "G3 1541", origem: "MCZ", destino: "CGH",
  embarque: "2026-12-20 07:10", passageiros: "JOÃO DA SILVA / MARIA SOUZA",
};

test("horário: antes, depois, diferença e todos os passageiros", () => {
  const m = mensagemPassageiro("horario_alterado", "visto antes 07:10 -> agora 08:40", voo);
  assert.match(m, /^Olá, João da Silva e Maria Souza!/);
  assert.match(m, /a GOL alterou o horário do voo G3 1541 \(MCZ → CGH\) de 20\/12: era 07:10 e agora é 08:40 \(1h30 mais tarde\)/);
});

test("venda × companhia também gera aviso", () => {
  assert.ok(mensagemPassageiro("horario_venda_diverge", "na venda 2026-12-20 07:10 -> na companhia 06:50", voo).includes("20 min mais cedo"));
});

test("data e cancelamento", () => {
  assert.match(mensagemPassageiro("data_alterada", "CRM 2026-12-20 -> companhia 2026-12-21", voo), /mudou a data do voo G3 1541 \(MCZ → CGH\): era 20\/12 e agora é 21\/12/);
  assert.match(mensagemPassageiro("trecho_cancelado", "", voo), /A GOL cancelou o voo G3 1541/);
});

test("tipos duvidosos não geram mensagem", () => {
  assert.equal(mensagemPassageiro("passageiro_remanejado", "em 2026-12-20: vendido MCZ-CGH 07:10 -> companhia GYN-CGH 08:40", voo), null);
  assert.equal(mensagemPassageiro("rota_alterada", "visto antes MCZ-CGH -> agora GYN-CGH", voo), null);
  assert.equal(mensagemPassageiro("horario_alterado", "formato estranho", voo), null);
});
