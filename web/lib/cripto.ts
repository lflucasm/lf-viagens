import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

/**
 * Cifra as credenciais das contas dos cedentes antes de gravar.
 *
 * AES-256-GCM, não AES-CBC: GCM autentica o texto cifrado, então adulterar
 * uma linha do banco quebra na hora de decifrar em vez de devolver lixo
 * silenciosamente. O IV é sorteado a cada gravação e vai junto no valor —
 * reusar IV em GCM vaza a chave, então ele nunca é fixo.
 *
 * A chave vive só na env do servidor. Ela não protege contra quem tem a env
 * inteira; protege contra o cenário realista: dump do banco, backup vazado,
 * ou alguém com acesso de leitura ao Postgres.
 */
const ALGORITMO = "aes-256-gcm";

export class CriptoNaoConfigurada extends Error {
  constructor() {
    super("CREDENCIAIS_CHAVE não está configurada.");
    this.name = "CriptoNaoConfigurada";
  }
}

function chave() {
  const bruta = process.env.CREDENCIAIS_CHAVE;
  if (!bruta) throw new CriptoNaoConfigurada();

  const bytes = Buffer.from(bruta, "base64");
  if (bytes.length !== 32) {
    throw new Error("CREDENCIAIS_CHAVE precisa ter 32 bytes em base64.");
  }
  return bytes;
}

export function criptoConfigurada() {
  try {
    chave();
    return true;
  } catch {
    return false;
  }
}

/** texto claro -> "iv.tag.cifrado", tudo em base64. */
export function cifrar(valor: string) {
  const iv = randomBytes(12);
  const cifra = createCipheriv(ALGORITMO, chave(), iv);
  const cifrado = Buffer.concat([cifra.update(valor, "utf8"), cifra.final()]);
  return [iv, cifra.getAuthTag(), cifrado].map((b) => b.toString("base64")).join(".");
}

/** Inverso de cifrar(). Estoura se o valor foi adulterado ou a chave mudou. */
export function decifrar(guardado: string) {
  const partes = guardado.split(".");
  if (partes.length !== 3) throw new Error("Valor cifrado em formato inesperado.");

  const [iv, tag, cifrado] = partes.map((p) => Buffer.from(p, "base64"));
  const decifra = createDecipheriv(ALGORITMO, chave(), iv);
  decifra.setAuthTag(tag);
  return Buffer.concat([decifra.update(cifrado), decifra.final()]).toString("utf8");
}
