import OpenAI from "openai";

export function getOpenAI() {
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
}

// A busca de voo (gpt-4.1-nano saiu do ar em 23/10/2026; teste de 25/10 com 12 frases:
// gpt-6-luna acertou 100% a US$ 0,10 por mil buscas, contra US$ 0,29 do gpt-4.1-mini)
// só interpreta uma frase curta e o texto colado é extração com
// regras fixas: modelo menor dá conta e custa uma fração do gpt-4o. A leitura
// de foto de documento fica no gpt-4o, onde modelo menor erra mais. Dá pra
// trocar cada rota sem mexer no código (LF_MODELO_BUSCA, LF_MODELO_TEXTO,
// LF_MODELO_FOTO) — voltar ao gpt-4o é só uma variável.
const MODELO_PADRAO = {
  "flight-search": "gpt-6-luna",
  "extract-text": "gpt-4.1-mini",
  "extract-image": "gpt-4o",
  "extract-demanda": "gpt-4o",
} as const;

const VARIAVEL_DO_MODELO = {
  "flight-search": "LF_MODELO_BUSCA",
  "extract-text": "LF_MODELO_TEXTO",
  "extract-image": "LF_MODELO_FOTO",
  "extract-demanda": "LF_MODELO_DEMANDA",
} as const;

export function modeloDaRota(rota: keyof typeof MODELO_PADRAO): string {
  return process.env[VARIAVEL_DO_MODELO[rota]]?.trim() || MODELO_PADRAO[rota];
}

export const PASSAGEIRO_JSON_SCHEMA = {
  type: "object" as const,
  properties: {
    passageiros: {
      type: "array" as const,
      items: {
        type: "object" as const,
        properties: {
          nome: { type: "string" },
          sobrenome: { type: "string" },
          data_nascimento: { type: "string", description: "formato dd/mm/aaaa, ou vazio se não souber" },
          cpf: { type: "string", description: "apenas números, ou vazio" },
          email: { type: "string" },
          telefone: { type: "string", description: "apenas números com DDD, ou vazio" },
          genero: { type: "string", description: "'masculino' ou 'feminino', ou vazio" },
          numero_documento: { type: "string", description: "número de RG ou passaporte, ou vazio" },
          pais_emissao_documento: {
            type: "string",
            description: "país que emitiu o documento/passaporte, como código ISO de 2 letras maiúsculas (BR, AR, US, PT...), ou vazio se não aparecer",
          },
          classificacao_etaria: { type: "string", description: "'adulto', 'crianca' ou 'bebe', deduzido pela idade" },
        },
        required: ["nome", "sobrenome", "data_nascimento", "cpf", "email", "telefone", "genero", "numero_documento", "pais_emissao_documento", "classificacao_etaria"],
        additionalProperties: false,
      },
    },
  },
  required: ["passageiros"],
  additionalProperties: false,
};

export const PROMPT_EXTRACAO_PASSAGEIRO = `Extraia dados de passageiros de voo do conteúdo fornecido (texto colado ou foto de documento de identidade/passaporte).

Regras:
- nome = todos os prenomes; sobrenome = todos os sobrenomes. Nome composto é
  comum no Brasil e não pode ser quebrado: em "Paulo Henrique de Moura Cunha",
  nome = "Paulo Henrique" e sobrenome = "de Moura Cunha"; em "Maria Eduarda
  Silva Santos", nome = "Maria Eduarda" e sobrenome = "Silva Santos"; em
  "João Pedro Alves", nome = "João Pedro" e sobrenome = "Alves".
  Como separar: uma partícula (de, da, do, dos, das, e) marca o início do
  sobrenome — tudo antes dela é prenome. Sem partícula, decida pelo que a
  palavra é: prenome (Ana, Maria, José, João, Pedro, Paulo, Henrique, Eduarda,
  Paula...) ou sobrenome (Silva, Santos, Souza, Moura, Cunha, Oliveira, Lima,
  Costa, Pereira, Ferreira, Almeida, Rodrigues...). Na dúvida entre as duas,
  trate a palavra como sobrenome.
  Se o conteúdo for um documento que já separa nome e sobrenome, respeite a
  separação impressa no documento em vez de deduzir.
- Nunca descarte parte do nome: toda palavra do nome entra em nome ou sobrenome,
  inclusive inicial solta ("M", "J."). Ex.: "Ana Lúcia M Oliveira" → nome =
  "Ana Lúcia", sobrenome = "M Oliveira".
- Se um campo não aparecer no conteúdo, retorne string vazia "" — nunca invente.
- email e telefone: quando o conteúdo trouxer um único email e/ou telefone
  que não esteja amarrado a uma pessoa específica (ex.: aparece solto no fim
  da mensagem, ou como "contato:", "WhatsApp:", "e-mail:"), repita esse mesmo
  email e telefone em TODOS os passageiros. Só use contato diferente por
  pessoa quando o texto ligar cada contato a um nome.
- data_nascimento sempre em dd/mm/aaaa.
- cpf e telefone só dígitos, sem pontuação.
- CPF e celular brasileiro têm 11 dígitos os dois. Para separar: o CPF tem
  dígito verificador (os 2 últimos), costuma vir com zero à esquerda e não
  começa com DDD; o celular começa com DDD (11 a 99) e tem 9 como terceiro
  dígito. Na dúvida, ponha o número no campo que parecer mais provável — há
  uma validação depois que corrige a troca.
- genero: "masculino" ou "feminino". Se o conteúdo não disser explicitamente,
  deduza pelo primeiro nome (nomes brasileiros são fortemente marcados por
  gênero — Beatriz, Ana, Maria = feminino; João, Paulo, Pedro = masculino).
  Só devolva "" se o nome for ambíguo de verdade.
- pais_emissao_documento: país que emitiu o documento (nacionalidade do passaporte)
  em código ISO de 2 letras maiúsculas: Brasil = "BR", Argentina = "AR", Chile = "CL",
  Estados Unidos = "US", Portugal = "PT". Só preencha quando o conteúdo disser o país
  ou o documento for claramente estrangeiro (passaporte impresso com outro país). Para
  passageiro brasileiro (mesmo com RG ou CNH brasileiro), ou se não der pra saber,
  retorne "" — nunca preencha "BR" e nunca chute.
- numero_documento: só o número de RG, CNH ou passaporte, quando o conteúdo o
  identificar como tal (rótulo "RG", "documento", "passaporte" ou documento
  fotografado). Nunca ponha aí o CPF nem o telefone: se o conteúdo só traz CPF
  e celular, deixe "". Copie o número inteiro, com todos os dígitos e letras —
  inclusive o dígito ou letra verificador depois do hífen (RG 12.345.678-9 vira
  "123456789") — sem cortar nenhum.
- classificacao_etaria: calcule pela data de nascimento se possível (menor que 2 anos = "bebe", 2 a 11 anos = "crianca", 12+ = "adulto"); se não der pra calcular, assuma "adulto".
- Se houver mais de uma pessoa, retorne um item por pessoa.`;

type Passageiro = { cpf?: string; telefone?: string; numero_documento?: string; pais_emissao_documento?: string; [k: string]: unknown };

const soDigitos = (v: unknown) => String(v ?? "").replace(/\D/g, "");

function cpfValido(valor: string): boolean {
  const d = soDigitos(valor);
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;

  const digitoAte = (ate: number) => {
    let soma = 0;
    for (let i = 0; i < ate; i++) soma += Number(d[i]) * (ate + 1 - i);
    const resto = (soma * 10) % 11;
    return resto === 10 ? 0 : resto;
  };

  return digitoAte(9) === Number(d[9]) && digitoAte(10) === Number(d[10]);
}

/** Primeiro CPF válido isolado no texto (com ou sem máscara), ignorando `ignorar`. */
function cpfDoTexto(texto: string, ignorar: string[]): string | undefined {
  for (const m of texto.matchAll(/(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)/g)) {
    const d = soDigitos(m[0]);
    if (cpfValido(d) && !ignorar.includes(d)) return d;
  }
  return undefined;
}

/** O texto chama esse número de RG, CNH ou passaporte? */
function rotuladoComoDocumento(texto: string, numero: string): boolean {
  const digitos = numero.split("").join("\\D*");
  return new RegExp(`(?:cnh|rg|identidade|documento|passaporte|passport)\\D{0,25}${digitos}`, "i").test(texto);
}

const PARECE_CELULAR = /^[1-9]{2}9\d{8}$/;

/**
 * O único celular (DDD + 9 + 8 dígitos) que aparece no texto, sem contar o que
 * é CPF ou documento. Se houver mais de um, não adivinha qual é.
 */
function celularDoTexto(texto: string, excluir: string[]): string | undefined {
  const achados = new Set<string>();
  for (const m of texto.matchAll(/(?<!\d)\(?[1-9]{2}\)?\s?9\d{4}-?\d{4}(?!\d)/g)) {
    const d = soDigitos(m[0]);
    if (!excluir.includes(d) && !rotuladoComoDocumento(texto, d)) achados.add(d);
  }
  return achados.size === 1 ? [...achados][0] : undefined;
}

const escaparRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Modelo menor às vezes descarta a inicial solta ("Luiz Fernando J Pires" vira
 * "Luiz Fernando" + "Gomes") ou a partícula do nome. Se o texto traz
 * literalmente nome + 1 ou 2 letras + sobrenome e a IA omitiu essas letras,
 * elas voltam para o início do sobrenome.
 */
function restaurarInicialDoNome<T extends Passageiro>(p: T, textoFonte: string): T {
  const nome = String(p.nome ?? "").trim();
  const sobrenome = String(p.sobrenome ?? "").trim();
  if (!nome || !sobrenome) return p;
  const palavras = (s: string) => s.split(/\s+/).map(escaparRegex).join("\\s+");
  const achou = new RegExp(`(?<!\\p{L})${palavras(nome)}\\s+(\\p{L}{1,2}\\.?)\\s+${palavras(sobrenome)}(?!\\p{L})`, "iu").exec(textoFonte);
  return achou ? { ...p, sobrenome: `${achou[1]} ${sobrenome}` } : p;
}

/**
 * CPF e celular brasileiro têm 11 dígitos — quando o texto colado traz os
 * dois sem rótulo, a IA troca um pelo outro com frequência, e às vezes põe um
 * deles no campo de documento ou deixa o CPF de fora. O dígito verificador do
 * CPF resolve isso sem depender de palpite: o número de 11 dígitos que for um
 * CPF válido, em qualquer um dos campos, é o CPF, e o outro é o telefone.
 * Se nenhum for, mantém o que a IA classificou (CPF com typo ainda é melhor
 * que campo vazio).
 *
 * `textoFonte` só vem da rota de texto. Com ele, o CPF ou o celular que a IA
 * deixou de fora são recuperados do texto (só com 1 passageiro, pra não
 * atribuir o dado de outra pessoa) e um celular parado no campo de documento
 * volta pro telefone, a menos que o texto o chame de RG/CNH. Na foto não há
 * texto: nada é mexido além da troca entre CPF e telefone.
 */
function normalizarCpfETelefone<T extends Passageiro>(p: T, textoFonte?: string, unico = false): T {
  const cpfInformado = soDigitos(p.cpf);
  const telefoneInformado = soDigitos(p.telefone);
  const documento = soDigitos(p.numero_documento);
  const modoTexto = textoFonte !== undefined;

  const camposDeCpf = modoTexto ? [cpfInformado, telefoneInformado, documento] : [cpfInformado, telefoneInformado];
  const cpf =
    camposDeCpf.filter((n) => n.length === 11).find(cpfValido) ??
    (modoTexto && unico ? cpfDoTexto(textoFonte, [telefoneInformado]) : undefined);

  if (!cpf) {
    const recuperado = modoTexto && unico && !telefoneInformado ? celularDoTexto(textoFonte, [cpfInformado, documento]) : undefined;
    return { ...p, cpf: cpfInformado, telefone: telefoneInformado || recuperado || "" };
  }

  const documentoComoTelefone =
    modoTexto && PARECE_CELULAR.test(documento) && !rotuladoComoDocumento(textoFonte, documento) ? documento : "";
  const candidatos = modoTexto ? [telefoneInformado, cpfInformado, documentoComoTelefone] : [telefoneInformado, cpfInformado];
  const encontrado = candidatos.find((n) => n && n !== cpf);
  const telefone =
    encontrado ?? (modoTexto && unico ? celularDoTexto(textoFonte, [cpf, cpfInformado, documento]) : undefined) ?? "";

  const limparDocumento = modoTexto && (documento === cpf || (documento !== "" && documento === telefone));
  return { ...p, cpf, telefone, ...(limparDocumento ? { numero_documento: "" } : {}) };
}

// A extensão procura esse código na lista de países do checkout, então só
// passa adiante algo no formato ISO de 2 letras; qualquer outra coisa vira
// vazio e o formulário fica no país padrão.
function normalizarPais<T extends Passageiro>(p: T): T {
  const codigo = String(p.pais_emissao_documento ?? "").trim().toUpperCase();
  return { ...p, pais_emissao_documento: /^[A-Z]{2}$/.test(codigo) ? codigo : "" };
}

/** dd/mm/aaaa a partir de "d/m/aaaa", "dd-mm-aaaa", "dd.mm.aaaa" ou "aaaa-mm-dd"; undefined se não for data. */
function dataBR(valor: unknown): string | undefined {
  const s = String(valor ?? "").trim();
  const br = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(s);
  if (br) return `${br[1].padStart(2, "0")}/${br[2].padStart(2, "0")}/${br[3]}`;
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return iso ? `${iso[3]}/${iso[2]}/${iso[1]}` : undefined;
}

/**
 * O modelo menor às vezes troca um dígito ao copiar a data de nascimento
 * (14/03/1968 virou 14/03/1962) e o formulário aceita uma data errada sem
 * reclamar. Se a data devolvida não aparece no texto colado, mas o texto tem
 * uma data com o mesmo dia e mês que nenhum outro passageiro usa, ela é a data
 * certa e substitui a da IA. Mais de uma candidata é ambíguo: mantém a da IA.
 */
function corrigirDatasDeNascimento<T extends Passageiro>(passageiros: T[], textoFonte: string): T[] {
  const doTexto = new Set<string>();
  for (const m of textoFonte.matchAll(/(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{4}(?!\d)/g)) {
    const data = dataBR(m[0]);
    if (data) doTexto.add(data);
  }
  const emUso = new Set(passageiros.map((p) => dataBR(p.data_nascimento)).filter((d): d is string => !!d && doTexto.has(d)));

  return passageiros.map((p) => {
    const atual = dataBR(p.data_nascimento);
    if (!atual || doTexto.has(atual)) return p;
    const candidatas = [...doTexto].filter((d) => d.slice(0, 5) === atual.slice(0, 5) && !emUso.has(d));
    return candidatas.length === 1 ? { ...p, data_nascimento: candidatas[0] } : p;
  });
}

export function normalizarPassageiros<T extends Passageiro>(passageiros: T[], textoFonte?: string): T[] {
  const unico = passageiros.length === 1;
  const normalizados = passageiros
    .map((p) => normalizarCpfETelefone(p, textoFonte, unico))
    .map((p) => (textoFonte === undefined ? p : restaurarInicialDoNome(p, textoFonte)))
    .map(normalizarPais);
  return textoFonte === undefined ? normalizados : corrigirDatasDeNascimento(normalizados, textoFonte);
}

const semAcento = (v: string) => v.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/**
 * A mesma data escrita de outro jeito no texto colado: ano com 2 dígitos
 * (20/12/80), separada por espaço, colada (20121980) ou com o mês por extenso
 * (20 de dezembro de 1980). Sem isso a conferência acusava data certa.
 */
function dataEscritaDeOutroJeito(nascimento: string, textoFonte: string): boolean {
  const [dia, mes, ano] = nascimento.split("/");
  const d = `0?${Number(dia)}`;
  const a = `(?:${ano}|${ano.slice(2)})`;
  const numerica = new RegExp(`(?<!\\d)${d}\\s*[/.\\-\\s]\\s*0?${Number(mes)}\\s*[/.\\-\\s]\\s*${a}(?!\\d)`);
  const colada = new RegExp(`(?<!\\d)${dia}${mes}${a}(?!\\d)`);
  const extenso = new RegExp(`(?<!\\d)${d}\\s*(?:de\\s*)?${MESES[Number(mes) - 1]}[a-z]*\\.?\\s*(?:de\\s*)?${a}(?!\\d)`);
  return numerica.test(textoFonte) || colada.test(textoFonte) || extenso.test(semAcento(textoFonte));
}

/**
 * Conferência sem IA: todo dado que a IA devolveu precisa estar no texto
 * colado. Não corrige nada, só lista o que não bate pra o operador olhar antes
 * de seguir (a IA pode ter trocado um dígito, inventado ou misturado
 * passageiros). Só faz sentido na rota de texto; na foto não há texto.
 */
export function conferirComTexto(passageiros: Passageiro[], textoFonte: string): string[] {
  const texto = semAcento(textoFonte);
  const digitosDoTexto = soDigitos(textoFonte);
  const datasDoTexto = new Set<string>();
  for (const m of textoFonte.matchAll(/(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{4}(?!\d)/g)) {
    const data = dataBR(m[0]);
    if (data) datasDoTexto.add(data);
  }

  const avisos: string[] = [];
  passageiros.forEach((p, i) => {
    const quem = `${String(p.nome ?? "").trim()} ${String(p.sobrenome ?? "").trim()}`.trim() || `Passageiro ${i + 1}`;
    const faltando: string[] = [];

    const palavras = semAcento(`${p.nome ?? ""} ${p.sobrenome ?? ""}`).split(/[^a-z]+/).filter((w) => w.length > 1);
    if (palavras.some((w) => !texto.includes(w))) faltando.push("nome");

    const email = String(p.email ?? "").trim().toLowerCase();
    if (email && !texto.includes(email)) faltando.push("e-mail");

    const cpf = soDigitos(p.cpf);
    if (cpf && !digitosDoTexto.includes(cpf)) faltando.push("CPF");

    const telefone = soDigitos(p.telefone);
    if (telefone && !digitosDoTexto.includes(telefone.replace(/^55(?=\d{10,11}$)/, ""))) faltando.push("telefone");

    const nascimento = dataBR(p.data_nascimento);
    if (nascimento && !datasDoTexto.has(nascimento) && !dataEscritaDeOutroJeito(nascimento, textoFonte)) faltando.push("data de nascimento");

    if (faltando.length) avisos.push(`${quem}: ${faltando.join(", ")} não confere com o texto colado`);
  });
  return avisos;
}

/**
 * Parâmetros de decisão do modelo. Os gpt-4.x aceitam temperature 0; os modelos
 * de raciocínio (gpt-5/6) recusam temperature (400) e cobram o raciocínio como
 * saída, então ficam em esforço "low" — suficiente pra interpretar a busca.
 */
export function parametrosDeDecisao(modelo: string): { temperature: 0 } | { reasoning_effort: "low" } {
  return /^gpt-4/.test(modelo) ? { temperature: 0 } : { reasoning_effort: "low" };
}

/** Lê passageiros das fotos de documento (identidade/passaporte) com visão. */
export async function lerDocumentosDasFotos(imagens: string[]): Promise<Passageiro[] | null> {
  const completion = await getOpenAI().chat.completions.create({
    model: modeloDaRota("extract-image"),
    temperature: 0,
    messages: [
      { role: "system", content: PROMPT_EXTRACAO_PASSAGEIRO },
      {
        role: "user",
        content: [
          { type: "text", text: "Leia o(s) documento(s) de identidade/passaporte a seguir:" },
          ...imagens.map((b64) => ({
            type: "image_url" as const,
            image_url: { url: b64.startsWith("data:") ? b64 : `data:image/jpeg;base64,${b64}` },
          })),
        ],
      },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "passageiros", schema: PASSAGEIRO_JSON_SCHEMA, strict: true },
    },
  });
  const raw = completion.choices[0]?.message?.content;
  return raw ? normalizarPassageiros(JSON.parse(raw).passageiros ?? []) : null;
}

/**
 * Passageiro lido de foto só vale com cara de documento: nome, sobrenome,
 * nascimento e CPF ou número de documento. O print do voo que a agência manda
 * junto não tem isso (mesma regra do lfPareceDocumento da extensão).
 */
export function pareceDocumento(p: Passageiro): boolean {
  const t = (v: unknown) => String(v ?? "").trim();
  return !!(t(p.nome) && t(p.sobrenome) && /^\d{2}\/\d{2}\/\d{4}$/.test(t(p.data_nascimento)) && (t(p.cpf) || t(p.numero_documento)));
}
