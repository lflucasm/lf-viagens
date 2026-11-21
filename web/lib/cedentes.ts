import type { Database } from "@/lib/database.types";

export type Cedente = Database["public"]["Tables"]["cedentes"]["Row"];
export type Convite = Database["public"]["Tables"]["convites"]["Row"];
export type TermoIndicacao = Database["public"]["Tables"]["termos_indicacao"]["Row"];
export type CedenteConta = Database["public"]["Tables"]["cedente_contas"]["Row"];

/**
 * Versão da cartilha do cedente. A ciência fica em aceites_termo (termo_versao
 * é texto livre): mude esta versão quando o conteúdo da cartilha mudar, e quem
 * já leu passa a ver a nova pra ler e confirmar de novo.
 */
export const CARTILHA_VERSAO = "cartilha-v2-2026-10";
export const PREFIXO_CARTILHA = "cartilha-";

export const PIX_TIPOS = ["cpf", "cnpj", "email", "telefone", "aleatoria"] as const;
export type PixTipo = (typeof PIX_TIPOS)[number];

export const ROTULO_PIX: Record<PixTipo, string> = {
  cpf: "CPF",
  cnpj: "CNPJ",
  email: "E-mail",
  telefone: "Telefone",
  aleatoria: "Chave aleatória",
};

/**
 * As contas que o cedente cria, na ordem em que o passo a passo pede — o
 * e-mail vem primeiro porque todos os programas mandam confirmação pra ele.
 */
export const PROGRAMAS = [
  { chave: "email", rotulo: "E-mail" },
  { chave: "latam", rotulo: "LATAM Pass" },
  { chave: "smiles", rotulo: "Smiles" },
  { chave: "livelo", rotulo: "Livelo" },
  { chave: "esfera", rotulo: "Esfera" },
] as const;

export type Programa = (typeof PROGRAMAS)[number]["chave"];

export const ROTULO_PROGRAMA = Object.fromEntries(
  PROGRAMAS.map((p) => [p.chave, p.rotulo]),
) as Record<Programa, string>;

export const ROTULO_STATUS: Record<string, string> = {
  rascunho: "Rascunho",
  pendente: "Pendente",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
};

export function soDigitos(v: string) {
  return (v || "").replace(/\D+/g, "");
}

export function normalizarCpf(v: string) {
  return soDigitos(v).slice(0, 11);
}

export function normalizarTelefone(v: string) {
  return soDigitos(v).slice(0, 11);
}

export function formatarCpf(cpf: string) {
  const d = soDigitos(cpf);
  if (d.length !== 11) return cpf;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/**
 * Valida CPF pelos dois dígitos verificadores. Sem isso o formulário público
 * aceita qualquer sequência de 11 dígitos e o cadastro só quebra semanas
 * depois, na hora de pagar o PIX.
 */
export function cpfValido(valor: string) {
  const cpf = soDigitos(valor);
  if (cpf.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(cpf)) return false;

  const digito = (ate: number) => {
    let soma = 0;
    for (let i = 0; i < ate; i += 1) soma += Number(cpf[i]) * (ate + 1 - i);
    const resto = (soma * 10) % 11;
    return resto === 10 ? 0 : resto;
  };

  return digito(9) === Number(cpf[9]) && digito(10) === Number(cpf[10]);
}

/** "DD/MM/AAAA" digitado -> "AAAA-MM-DD", ou null se não der pra ler. */
export function dataBrParaIso(br: string): string | null {
  const v = (br || "").trim();
  if (!v) return null;
  const [dd, mm, yyyy] = v.split("/");
  if (!dd || !mm || !yyyy || dd.length !== 2 || mm.length !== 2 || yyyy.length !== 4) {
    return null;
  }
  const d = Number(dd);
  const m = Number(mm);
  const y = Number(yyyy);
  if (!Number.isFinite(d) || !Number.isFinite(m) || !Number.isFinite(y)) return null;
  if (y < 1900 || y > 2100 || m < 1 || m > 12 || d < 1 || d > 31) return null;
  return `${yyyy}-${mm}-${dd}`;
}

/** "AAAA-MM-DD" (o que a gente guarda) -> "DD/MM/AAAA" (o que o MilhasFlow espera). */
export function dataIsoParaBr(iso: string) {
  const [yyyy, mm, dd] = iso.split("-");
  return `${dd}/${mm}/${yyyy}`;
}

/** Máscara progressiva pro campo de data, enquanto a pessoa digita. */
export function mascararDataBr(v: string) {
  const digitos = (v || "").replace(/\D/g, "").slice(0, 8);
  let saida = digitos.slice(0, 2);
  if (digitos.length > 2) saida += "/" + digitos.slice(2, 4);
  if (digitos.length > 4) saida += "/" + digitos.slice(4, 8);
  return saida;
}

/**
 * Identificador interno do cedente: 3 letras do primeiro nome + tempo +
 * aleatório. Mesmo formato do trademiles, pra não ter que traduzir código
 * de cedente quando os dois sistemas conversarem.
 */
export function gerarIdentificador(nomeCompleto: string) {
  const limpo = (nomeCompleto || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}+/gu, "")
    .toUpperCase()
    .replace(/[^\p{L}\p{N}\s']/gu, " ")
    .trim();

  const primeiro = (limpo.split(/\s+/)[0] || "CED").replace(/[^A-Z0-9]/g, "");
  const prefixo = (primeiro.slice(0, 3) || "CED").padEnd(3, "X");
  const tempo = Date.now().toString().slice(-6);
  const aleatorio = Math.floor(Math.random() * 9000 + 1000);
  return `${prefixo}-${tempo}${aleatorio}`;
}

/**
 * Código de convite = nome do colaborador em PascalCase (sem espaços nem
 * acentos), pra quem recebe o link reconhecer de cara quem indicou — ex.:
 * "Paulo Henrique" -> "PauloHenrique". Colisão entre colaboradores de mesmo
 * nome é resolvida por quem chama, tentando sufixos numéricos.
 */
export function gerarCodigoConvite(nomeCompleto: string, sufixo = 0) {
  const limpo = (nomeCompleto || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}+/gu, "")
    .replace(/[^\p{L}\p{N}\s]+/gu, "")
    .trim();

  const partes = limpo.split(/\s+/).filter(Boolean);
  const pascal = partes
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
    .join("");

  const base = pascal || "Colaborador";
  return sufixo > 0 ? `${base}${sufixo + 1}` : base;
}

/** Token do cadastro guiado — comprido de propósito, é o que faz as vezes de senha. */
export function gerarTokenAcesso() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
