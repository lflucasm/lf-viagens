// Leitura da demanda de emissão que a agência manda no Telegram: o print do
// app da cia (trecho, data, horário, tarifa, opção milhas + R$) e o texto que
// vem junto. A IA só transcreve o que está no print; a conferência do que foi
// lido contra a tela da cia é feita na extensão.

export const DEMANDA_JSON_SCHEMA = {
  type: "object" as const,
  properties: {
    cia: { type: "string", description: "'latam', 'smiles', 'azul', 'tap' ou 'outra'; vazio se não der pra saber" },
    origem: { type: "string", description: "código IATA de 3 letras da origem, ou vazio" },
    destino: { type: "string", description: "código IATA de 3 letras do destino, ou vazio" },
    data: { type: "string", description: "data do voo, formato dd/mm/aaaa, ou vazio" },
    horario_saida: { type: "string", description: "horário de saída, formato HH:MM, ou vazio" },
    horario_chegada: { type: "string", description: "horário de chegada, formato HH:MM, ou vazio" },
    numero_voo: { type: "string", description: "número do voo (ex.: LA3045), ou vazio" },
    data_volta: { type: "string", description: "data do voo de volta, dd/mm/aaaa; vazio se for só ida" },
    horario_saida_volta: { type: "string", description: "horário de saída do voo de volta, HH:MM; vazio se for só ida" },
    horario_chegada_volta: { type: "string", description: "horário de chegada do voo de volta, HH:MM; vazio se for só ida" },
    tarifa_volta: { type: "string", description: "tarifa do voo de volta em maiúsculas; vazio se for só ida" },
    tarifa: { type: "string", description: "nome da tarifa em maiúsculas (LIGHT, STANDARD, FULL, PREMIUM ECONOMY, CLUBE...), ou vazio" },
    milhas: { type: "number", description: "milhas por passageiro da opção do print (ida e volta somadas); 0 se não aparecer" },
    taxa: { type: "number", description: "valor em reais somado às milhas, por passageiro (ida e volta somadas); 0 se for só milhas ou não aparecer" },
    adultos: { type: "number", description: "adultos da reserva; 0 se o print não disser" },
    criancas: { type: "number", description: "crianças (2 a 11 anos); 0 se não disser" },
    bebes: { type: "number", description: "bebês de colo; 0 se não disser" },
    turbinada: { type: "boolean", description: "true só se o print ou o texto da agência disser que é tarifa turbinada (ou pedir para turbinar); senão false" },
    observacoes: { type: "string", description: "vazio, exceto se algo impedir a leitura" },
  },
  required: [
    "cia", "origem", "destino", "data", "horario_saida", "horario_chegada", "numero_voo",
    "data_volta", "horario_saida_volta", "horario_chegada_volta", "tarifa_volta", "tarifa", "milhas", "taxa", "adultos", "criancas", "bebes", "turbinada", "observacoes",
  ],
  additionalProperties: false,
};

export const PROMPT_EXTRACAO_DEMANDA = `Você lê o pedido de emissão de passagem aérea com milhas que uma agência parceira manda pelo Telegram: um ou mais prints do app/site da companhia (e às vezes texto solto).

Transcreva só o que está visível. Nunca invente, nunca complete por palpite.

Regras:
- cia: 'latam' (LATAM Airlines/LATAM Pass), 'smiles' (GOL/Smiles), 'azul' (Azul/TudoAzul), 'tap' (TAP Air Portugal/Miles&Go), 'outra'. Vazio se não der pra saber.
- origem/destino: código IATA de 3 letras. Se o print mostra o código do aeroporto (CGH, GRU, REC...), use o código do aeroporto do print. Se só mostra a cidade, use o código de cidade (São Paulo = SAO, Rio de Janeiro = RIO, Belo Horizonte = BHZ).
- data: dd/mm/aaaa. Se o print não mostrar o ano, assuma o próximo ano em que a data ainda não passou a partir de hoje.
- horario_saida/horario_chegada: HH:MM com dois dígitos (07:10, não 7:10).
- numero_voo: só se aparecer.
- tarifa: o nome da cabine/tarifa escolhida (LIGHT, STANDARD, FULL, PREMIUM ECONOMY, CLUBE), em maiúsculas. Se a agência pedir só "tarifa econômica", "mais barata" ou "básica" sem dizer o nome, deixe vazio.
- Ida e volta: se o print mostra dois trechos (ida A→B e volta B→A, ex.: "Salvador a Rio sex., 22 de jan." e "Rio a Salvador seg., 25 de jan."), origem/destino/data/horários/tarifa são do trecho de ida e data_volta/horario_saida_volta/horario_chegada_volta/tarifa_volta são do trecho de volta. Só ida: deixe os campos _volta vazios.
- milhas e taxa: da opção que o print mostra como escolhida, POR PASSAGEIRO. Em ida e volta é a soma dos dois trechos (normalmente o total da opção marcada embaixo, ex.: "41.534 milhas + BRL 91,53"). Ex.: "19.890 milhas + R$ 62,14" → milhas = 19890, taxa = 62.14. Se o print mostra o total de vários passageiros, divida pelo número de passageiros. Se aparecem várias opções e nenhuma está marcada, use 0 em ambos.
- turbinada: true só se o print ou o texto disser tarifa turbinada ("turbinada", "turbinar", "tarifa turbinada"); na dúvida, false. Quando for turbinada, milhas é o total do print (já com o acréscimo).
- adultos/criancas/bebes: só o que o print ou o texto disser; senão 0. Se o print mostra só o total (ex.: "5 Passageiros"), adultos = esse total (as idades são conferidas depois pelas datas de nascimento).
- Se o print tiver mais de um voo, use o voo que estiver selecionado/destacado; se nenhum estiver, deixe os campos do voo vazios e explique em observacoes.
- observacoes: deixe vazio. Só preencha se algo impedir a leitura.`;

export type DemandaBruta = {
  cia?: unknown;
  origem?: unknown;
  destino?: unknown;
  data?: unknown;
  horario_saida?: unknown;
  horario_chegada?: unknown;
  numero_voo?: unknown;
  data_volta?: unknown;
  horario_saida_volta?: unknown;
  horario_chegada_volta?: unknown;
  tarifa_volta?: unknown;
  tarifa?: unknown;
  milhas?: unknown;
  taxa?: unknown;
  adultos?: unknown;
  criancas?: unknown;
  bebes?: unknown;
  turbinada?: unknown;
  observacoes?: unknown;
};

export type Demanda = {
  cia: "latam" | "smiles" | "azul" | "tap" | "outra" | "";
  origem: string;
  destino: string;
  data: string;
  horario_saida: string;
  horario_chegada: string;
  numero_voo: string;
  data_volta: string;
  horario_saida_volta: string;
  horario_chegada_volta: string;
  tarifa_volta: string;
  tarifa: string;
  milhas: number;
  taxa: number;
  adultos: number;
  criancas: number;
  bebes: number;
  turbinada: boolean;
  observacoes: string;
};

const texto = (v: unknown) => String(v ?? "").trim();

function inteiro(v: unknown): number {
  const n = Math.round(Number(v));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function reais(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : 0;
}

export function normalizarHorario(v: unknown): string {
  const m = /^(\d{1,2})[:h](\d{2})$/.exec(texto(v));
  if (!m) return "";
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return "";
  return `${String(h).padStart(2, "0")}:${m[2]}`;
}

export function normalizarData(v: unknown): string {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(texto(v));
  if (!m) return "";
  const [d, mes, a] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const data = new Date(a, mes - 1, d);
  if (data.getFullYear() !== a || data.getMonth() !== mes - 1 || data.getDate() !== d) return "";
  return `${String(d).padStart(2, "0")}/${String(mes).padStart(2, "0")}/${a}`;
}

const CIAS = ["latam", "smiles", "azul", "tap", "outra"] as const;

export function normalizarDemanda(bruta: DemandaBruta): Demanda {
  const cia = texto(bruta.cia).toLowerCase();
  const iata = (v: unknown) => (/^[A-Za-z]{3}$/.test(texto(v)) ? texto(v).toUpperCase() : "");
  return {
    cia: (CIAS as readonly string[]).includes(cia) ? (cia as Demanda["cia"]) : "",
    origem: iata(bruta.origem),
    destino: iata(bruta.destino),
    data: normalizarData(bruta.data),
    horario_saida: normalizarHorario(bruta.horario_saida),
    horario_chegada: normalizarHorario(bruta.horario_chegada),
    numero_voo: texto(bruta.numero_voo).replace(/\s+/g, "").toUpperCase(),
    data_volta: normalizarData(bruta.data_volta),
    horario_saida_volta: normalizarHorario(bruta.horario_saida_volta),
    horario_chegada_volta: normalizarHorario(bruta.horario_chegada_volta),
    tarifa_volta: texto(bruta.tarifa_volta).toUpperCase(),
    tarifa: texto(bruta.tarifa).toUpperCase(),
    milhas: inteiro(bruta.milhas),
    taxa: reais(bruta.taxa),
    adultos: inteiro(bruta.adultos),
    criancas: inteiro(bruta.criancas),
    bebes: inteiro(bruta.bebes),
    turbinada: bruta.turbinada === true,
    observacoes: texto(bruta.observacoes),
  };
}

/**
 * Campos sem os quais a extensão não consegue buscar o voo sozinha. Devolve a
 * lista do que falta — vazia quando dá pra seguir.
 */
export function camposQueFaltam(d: Demanda): string[] {
  const falta: string[] = [];
  if (!d.cia) falta.push("companhia");
  if (!d.origem) falta.push("origem");
  if (!d.destino) falta.push("destino");
  if (!d.data) falta.push("data");
  if (!d.horario_saida) falta.push("horário de saída");
  if (d.data_volta && !d.horario_saida_volta) falta.push("horário de saída da volta");
  return falta;
}

// Linhas com data que não é de nascimento (emissão/validade de documento).
const DATA_DE_DOCUMENTO = /emissao|expedicao|validade|vencimento|valid[oa] ate/;

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// Formatos de data de nascimento no texto da agência: 29/10/1986, 29/10/86,
// 29.10.1986, 29-10-86, 29 10 1986, 29101986, 29 de outubro de 1986, 29 out 86.
const FORMATOS_DE_DATA = [
  /(?<![\d/.-])(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/.-])/g,
  /(?<![\d/.-])(\d{1,2})( )(\d{1,2}) (\d{4})(?![\d/.-])/g,
  /(?<!\d)(\d{2})()(\d{2})((?:19|20)\d{2})(?!\d)/g,
  new RegExp(`(?<!\\d)(\\d{1,2})()\\s*(?:de\\s*)?(${MESES.join("|")})[a-z]*\\.?\\s*(?:de\\s*)?(\\d{4}|\\d{2})(?!\\d)`, "g"),
];

const semAcento = (v: string) => v.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Datas de nascimento (dd/mm/aaaa) achadas no texto, em qualquer dos formatos
 * acima. Ano com 2 dígitos vira 20aa se não passar do ano atual, senão 19aa.
 * Data futura ou de mais de 120 anos não é nascimento e fica de fora.
 */
export function datasDeNascimento(textos: string[], hoje = new Date()): string[] {
  const datas: string[] = [];
  for (const linha of semAcento(textos.join("\n")).split("\n")) {
    if (DATA_DE_DOCUMENTO.test(linha)) continue;
    for (const formato of FORMATOS_DE_DATA) {
      for (const m of linha.matchAll(formato)) {
        const mes = MESES.includes(m[3]) ? MESES.indexOf(m[3]) + 1 : Number(m[3]);
        let ano = Number(m[4]);
        if (m[4].length === 2) ano += ano <= hoje.getFullYear() % 100 ? 2000 : 1900;
        const data = normalizarData(`${m[1]}/${mes}/${ano}`);
        if (!data) continue;
        const nasc = new Date(ano, mes - 1, Number(m[1]));
        if (nasc > hoje || hoje.getFullYear() - ano > 120) continue;
        datas.push(data);
      }
    }
  }
  return datas;
}

/**
 * Conta adultos/crianças/bebês pelas datas de nascimento, com a idade no dia
 * do voo (regra da LATAM e da Smiles: bebê < 2 anos, criança 2 a 11, adulto
 * 12+). Devolve null sem nenhuma data.
 */
export function contarPorNascimento(
  datas: string[],
  dataVoo: string,
  hoje = new Date(),
): { adultos: number; criancas: number; bebes: number } | null {
  const [dv, mv, av] = (normalizarData(dataVoo) || hoje.toLocaleDateString("pt-BR")).split("/").map(Number);
  const conta = { adultos: 0, criancas: 0, bebes: 0 };
  for (const data of datas.map(normalizarData).filter(Boolean)) {
    const [d, mes, a] = data.split("/").map(Number);
    const idade = av - a - (mv < mes || (mv === mes && dv < d) ? 1 : 0);
    if (idade < 2) conta.bebes++;
    else if (idade < 12) conta.criancas++;
    else conta.adultos++;
  }
  return conta.adultos + conta.criancas + conta.bebes ? conta : null;
}

/**
 * Acerta a contagem da demanda com as datas de nascimento (do texto ou dos
 * documentos das fotos): crianças e bebês vêm das datas; adultos são os das
 * datas ou o que sobra do total do print (adulto às vezes vem sem data).
 */
export function acertarPassageiros(d: Demanda, datas: string[], hoje = new Date()): Demanda {
  const porData = contarPorNascimento(datas, d.data, hoje);
  if (!porData) return d;
  const totalPrint = d.adultos + d.criancas + d.bebes;
  const adultos = Math.max(porData.adultos, totalPrint - porData.criancas - porData.bebes);
  return { ...d, adultos, criancas: porData.criancas, bebes: porData.bebes };
}
