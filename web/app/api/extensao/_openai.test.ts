import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { conferirComTexto, modeloDaRota, normalizarPassageiros, parametrosDeDecisao } from "./_openai.ts";

const VARIAVEIS = ["LF_MODELO_BUSCA", "LF_MODELO_TEXTO", "LF_MODELO_FOTO"] as const;

afterEach(() => {
  for (const v of VARIAVEIS) delete process.env[v];
});

test("modeloDaRota: padrão é gpt-6-luna na busca, mini no texto e gpt-4o na foto", () => {
  assert.equal(modeloDaRota("flight-search"), "gpt-6-luna");
  assert.equal(modeloDaRota("extract-text"), "gpt-4.1-mini");
  assert.equal(modeloDaRota("extract-image"), "gpt-4o");
});

test("modeloDaRota: variável de ambiente troca o modelo só daquela rota", () => {
  process.env.LF_MODELO_TEXTO = "gpt-4o";
  assert.equal(modeloDaRota("extract-text"), "gpt-4o");
  assert.equal(modeloDaRota("flight-search"), "gpt-6-luna");
});

test("modeloDaRota: variável vazia ou só com espaços cai no padrão", () => {
  process.env.LF_MODELO_BUSCA = "   ";
  process.env.LF_MODELO_FOTO = "";
  assert.equal(modeloDaRota("flight-search"), "gpt-6-luna");
  assert.equal(modeloDaRota("extract-image"), "gpt-4o");
});

// ── normalizarPassageiros: CPF e telefone ─────────────────────────────────
// Casos reais que a IA errou nos testes de modelo (dados fictícios).
const CPF_BEATRIZ = "11100000143";
const CPF_CARLOS = "11100000224";
const CPF_SOUZA = "11100000305";
const CEL_BEATRIZ = "11912340001";
const CEL_CARLOS = "11912340002";
const CEL_SOUZA = "11912340003";

const pass = (campos: Record<string, string>) => ({ nome: "X", sobrenome: "Y", cpf: "", telefone: "", numero_documento: "", data_nascimento: "", ...campos });

test("normalizarPassageiros: celular que a IA pôs no documento volta pro telefone", () => {
  const texto = `Beatriz Souza Nunes 10/11/1986 ${CEL_BEATRIZ} 111.000.001-43 beatriz@exemplo.com`;
  const [p] = normalizarPassageiros([pass({ cpf: CPF_BEATRIZ, numero_documento: CEL_BEATRIZ })], texto);
  assert.equal(p.cpf, CPF_BEATRIZ);
  assert.equal(p.telefone, CEL_BEATRIZ);
  assert.equal(p.numero_documento, "");
});

test("normalizarPassageiros: CPF no documento e celular no campo do CPF são desfeitos", () => {
  const texto = `Carlos Lima Nunes 07/06/1987 ${CEL_CARLOS} 111.000.002-24 carlos@exemplo.com`;
  const [p] = normalizarPassageiros([pass({ cpf: CEL_CARLOS, numero_documento: CPF_CARLOS })], texto);
  assert.equal(p.cpf, CPF_CARLOS);
  assert.equal(p.telefone, CEL_CARLOS);
  assert.equal(p.numero_documento, "");
});

test("normalizarPassageiros: CPF que a IA deixou de fora é recuperado do texto (1 passageiro)", () => {
  const texto = `Carlos de Lima Rocha 23/09/1984 ${CEL_SOUZA} 111.000.003-05 carlos@exemplo.com`;
  const [p] = normalizarPassageiros([pass({ cpf: CEL_SOUZA })], texto);
  assert.equal(p.cpf, CPF_SOUZA);
  assert.equal(p.telefone, CEL_SOUZA);
});

test("normalizarPassageiros: com mais de um passageiro não recupera CPF do texto", () => {
  const texto = `Ana 01/01/1990 ${CPF_BEATRIZ}\nBia 02/02/1991 ${CPF_CARLOS}`;
  const lista = normalizarPassageiros([pass({ nome: "Ana" }), pass({ nome: "Bia" })], texto);
  assert.deepEqual(lista.map((p) => p.cpf), ["", ""]);
});

test("normalizarPassageiros: CNH que o texto rotula como documento não vira telefone", () => {
  const texto = `Maria Silva\nCNH 11912345678\nCPF ${CPF_BEATRIZ}`;
  const [p] = normalizarPassageiros([pass({ cpf: CPF_BEATRIZ, numero_documento: "11912345678" })], texto);
  assert.equal(p.numero_documento, "11912345678");
  assert.equal(p.telefone, "");
});

test("normalizarPassageiros: na foto (sem texto) o documento de 11 dígitos não é mexido", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CPF_BEATRIZ, numero_documento: "11912345678" })]);
  assert.equal(p.numero_documento, "11912345678");
  assert.equal(p.telefone, "");
});

test("normalizarPassageiros: RG comum e telefone fixo ficam como estão", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CPF_BEATRIZ, telefone: "1133334444", numero_documento: "776977449" })], "RG 77.697.744-9");
  assert.equal(p.cpf, CPF_BEATRIZ);
  assert.equal(p.telefone, "1133334444");
  assert.equal(p.numero_documento, "776977449");
});

test("normalizarPassageiros: troca clássica entre CPF e telefone continua valendo", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CEL_CARLOS, telefone: CPF_CARLOS })]);
  assert.equal(p.cpf, CPF_CARLOS);
  assert.equal(p.telefone, CEL_CARLOS);
});

test("normalizarPassageiros: sem nenhum CPF válido, mantém o que a IA classificou", () => {
  const [p] = normalizarPassageiros([pass({ cpf: "111.222.333-44", telefone: "(11) 98765-4321" })], "texto sem CPF válido");
  assert.equal(p.cpf, "11122233344");
  assert.equal(p.telefone, "11987654321");
});

// ── normalizarPassageiros: celular omitido e inicial perdida ──────────────
const CPF_ANA = "11100000496";
const CEL_ANA = "11912340004";
const CPF_COM_CARA_DE_CELULAR = "11900000164";

test("normalizarPassageiros: celular que a IA omitiu é recuperado do texto (1 passageiro)", () => {
  const texto = `Ana Clara Dias Rocha 01/06/1969 ${CEL_ANA} 111.000.004-96 ana.lima@exemplo.com`;
  const [p] = normalizarPassageiros([pass({ cpf: CPF_ANA })], texto);
  assert.equal(p.cpf, CPF_ANA);
  assert.equal(p.telefone, CEL_ANA);
});

test("normalizarPassageiros: celular com máscara também é recuperado", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CPF_ANA })], "Ana Lima, tel (11) 91234-0005, CPF 111.000.004-96");
  assert.equal(p.telefone, "11912340005");
});

test("normalizarPassageiros: celular recuperado mesmo sem nenhum CPF no texto", () => {
  const [p] = normalizarPassageiros([pass({})], "Ana Lima nasc 01/06/1969 whatsapp 11912340005");
  assert.equal(p.telefone, "11912340005");
});

test("normalizarPassageiros: dois celulares no texto é ambíguo e nada é recuperado", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CPF_ANA })], `Ana ${CEL_ANA} e ${CEL_BEATRIZ} CPF ${CPF_ANA}`);
  assert.equal(p.telefone, "");
});

test("normalizarPassageiros: CPF sem máscara com cara de celular não vira telefone", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CPF_COM_CARA_DE_CELULAR })], `Ana Lima ${CPF_COM_CARA_DE_CELULAR}`);
  assert.equal(p.cpf, CPF_COM_CARA_DE_CELULAR);
  assert.equal(p.telefone, "");
});

test("normalizarPassageiros: número que o texto rotula como CNH não vira telefone", () => {
  const [p] = normalizarPassageiros([pass({ cpf: CPF_ANA })], "Ana Lima CNH 11912345678 CPF 111.000.004-96");
  assert.equal(p.telefone, "");
});

test("normalizarPassageiros: com 2 passageiros não recupera celular do texto", () => {
  const lista = normalizarPassageiros([pass({ nome: "A" }), pass({ nome: "B" })], `A B ${CEL_ANA}`);
  assert.deepEqual(lista.map((p) => p.telefone), ["", ""]);
});

test("normalizarPassageiros: inicial que a IA descartou volta pro sobrenome", () => {
  const texto = "Luiz Fernando J Pires\nTelefone\n11912340006\nCPF\n11100000577";
  const [p] = normalizarPassageiros([pass({ nome: "Luiz Fernando", sobrenome: "Pires", cpf: "11100000577", telefone: "11912340006" })], texto);
  assert.equal(p.nome, "Luiz Fernando");
  assert.equal(p.sobrenome, "J Pires");
});

test("normalizarPassageiros: inicial com ponto e partícula descartada também voltam", () => {
  const [a] = normalizarPassageiros([pass({ nome: "Ana Lúcia", sobrenome: "Oliveira" })], "Ana Lúcia M. Oliveira");
  assert.equal(a.sobrenome, "M. Oliveira");
  const [b] = normalizarPassageiros([pass({ nome: "Pedro", sobrenome: "Silva" })], "Pedro da Silva, CPF 000");
  assert.equal(b.sobrenome, "da Silva");
});

test("normalizarPassageiros: nome que a IA já separou certo não é mexido", () => {
  const [a] = normalizarPassageiros([pass({ nome: "Ana Lúcia", sobrenome: "M Oliveira" })], "Ana Lúcia M Oliveira");
  assert.equal(a.sobrenome, "M Oliveira");
  const [b] = normalizarPassageiros([pass({ nome: "Ana Lúcia M", sobrenome: "Oliveira" })], "Ana Lúcia M Oliveira");
  assert.deepEqual([b.nome, b.sobrenome], ["Ana Lúcia M", "Oliveira"]);
  const [c] = normalizarPassageiros([pass({ nome: "Maria Eduarda", sobrenome: "de Souza" })], "Maria Eduarda de Souza");
  assert.equal(c.sobrenome, "de Souza");
});

test("normalizarPassageiros: na foto (sem texto) o nome não é mexido", () => {
  const [p] = normalizarPassageiros([pass({ nome: "Luiz Fernando", sobrenome: "Pires" })]);
  assert.equal(p.sobrenome, "Pires");
});

// ── normalizarPassageiros: data de nascimento ─────────────────────────────

test("normalizarPassageiros: dígito trocado na data volta pra data do texto", () => {
  const [p] = normalizarPassageiros([pass({ data_nascimento: "14/03/1962" })], "Ana Lima nasc 14/03/1968");
  assert.equal(p.data_nascimento, "14/03/1968");
});

test("normalizarPassageiros: data que já está no texto não é mexida", () => {
  const [p] = normalizarPassageiros([pass({ data_nascimento: "14/03/1968" })], "Ana Lima nasc 14/03/1968");
  assert.equal(p.data_nascimento, "14/03/1968");
});

test("normalizarPassageiros: com vários passageiros, cada data errada acha a sua", () => {
  const texto = "Ana nasc 14/03/1968. Bruno nasc 02/11/1982.";
  const lista = normalizarPassageiros(
    [pass({ nome: "Ana", data_nascimento: "14/03/1962" }), pass({ nome: "Bruno", data_nascimento: "02/11/1982" })],
    texto,
  );
  assert.deepEqual(lista.map((p) => p.data_nascimento), ["14/03/1968", "02/11/1982"]);
});

test("normalizarPassageiros: duas datas candidatas com mesmo dia e mês é ambíguo e mantém a da IA", () => {
  const [p] = normalizarPassageiros([pass({ data_nascimento: "14/03/1962" })], "Ana 14/03/1968 e filho 14/03/1998");
  assert.equal(p.data_nascimento, "14/03/1962");
});

test("normalizarPassageiros: data candidata já usada por outro passageiro não é reaproveitada", () => {
  const lista = normalizarPassageiros(
    [pass({ nome: "Ana", data_nascimento: "14/03/1968" }), pass({ nome: "Bia", data_nascimento: "14/03/1962" })],
    "Ana 14/03/1968, Bia 20/05/1990",
  );
  assert.deepEqual(lista.map((p) => p.data_nascimento), ["14/03/1968", "14/03/1962"]);
});

test("normalizarPassageiros: data sem correspondência no texto, ou na foto, fica como a IA devolveu", () => {
  const [a] = normalizarPassageiros([pass({ data_nascimento: "14/03/1962" })], "Ana Lima sem data");
  assert.equal(a.data_nascimento, "14/03/1962");
  const [b] = normalizarPassageiros([pass({ data_nascimento: "14/03/1962" })]);
  assert.equal(b.data_nascimento, "14/03/1962");
});

// ── conferirComTexto ──────────────────────────────────────────────────────

const TEXTO_OK = "Ana Lima, CPF 529.982.247-25, nasc 14/03/1968, ana@exemplo.com, (11) 91234-5678";
const ANA = { nome: "Ana", sobrenome: "Lima", cpf: "52998224725", telefone: "11912345678", email: "ana@exemplo.com", data_nascimento: "14/03/1968" };

test("conferirComTexto: tudo que a IA devolveu está no texto, sem avisos", () => {
  assert.deepEqual(conferirComTexto([ANA], TEXTO_OK), []);
});

test("conferirComTexto: acusa cada campo que não aparece no texto", () => {
  const avisos = conferirComTexto([{ ...ANA, cpf: "52998224726", email: "ana@outro.com", data_nascimento: "14/03/1962", telefone: "11912345679" }], TEXTO_OK);
  assert.deepEqual(avisos, ["Ana Lima: e-mail, CPF, telefone, data de nascimento não confere com o texto colado"]);
});

test("conferirComTexto: nome com acento e DDI no telefone não geram falso alarme", () => {
  const avisos = conferirComTexto(
    [{ ...ANA, nome: "Ana Lúcia", telefone: "5511912345678" }],
    "Ana Lúcia Lima, CPF 529.982.247-25, nasc 14-03-1968, ana@exemplo.com, +55 11 91234-5678",
  );
  assert.deepEqual(avisos, []);
});

test("conferirComTexto: data escrita de outro jeito não gera falso alarme", () => {
  for (const nasc of ["14/03/68", "14 03 1968", "14031968", "14 de março de 1968", "14 mar 68", "14.3.1968"]) {
    assert.deepEqual(conferirComTexto([ANA], TEXTO_OK.replace("14/03/1968", nasc)), [], nasc);
  }
  assert.deepEqual(conferirComTexto([ANA], TEXTO_OK.replace("14/03/1968", "14/03/62")), ["Ana Lima: data de nascimento não confere com o texto colado"]);
});

test("parametrosDeDecisao: gpt-4.x usa temperature 0; gpt-5/6 usam reasoning_effort low", () => {
  assert.deepEqual(parametrosDeDecisao("gpt-4.1-mini"), { temperature: 0 });
  assert.deepEqual(parametrosDeDecisao("gpt-6-luna"), { reasoning_effort: "low" });
  assert.deepEqual(parametrosDeDecisao("gpt-5-nano"), { reasoning_effort: "low" });
});
