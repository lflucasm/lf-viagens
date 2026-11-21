/**
 * Porta de src/painel.py:link_para/MONTADORES/corrigir_origem — mesma regra
 * usada hoje no conferencia.html e nos links prontos do Telegram: o link do
 * próprio bilhete (PDF) tem prioridade; só na ausência dele é que montamos
 * um link a partir do que o CRM tem.
 */

export type VooParaLink = {
  localizador: string | null;
  cia: string | null;
  origem: string | null;
  passageiros: string | null;
  numero_voo?: string | null;
};

function primeiroPassageiro(passageiros: string | null): string {
  return (passageiros ?? "").split(" / ")[0]?.trim() ?? "";
}

/** Último nome do primeiro passageiro — o que GOL e LATAM pedem no formulário. */
export function sobrenome(passageiros: string | null): string {
  const partes = primeiroPassageiro(passageiros)
    .split(/\s+/)
    .filter((p) => p.length > 1);
  return partes.length ? partes[partes.length - 1] : "";
}

/**
 * Tudo depois do primeiro nome, maiúsculo, sem acento e sem espaço —
 * "Rui Machado de Lima" -> "MACHADODELIMA". Porta de qualidade.sobrenome_completo:
 * é o que a TAP compara (só "LIRA" dá reserva não encontrada).
 */
export function sobrenomeCompleto(passageiros: string | null): string {
  const partes = primeiroPassageiro(passageiros)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .split(/\s+/);
  return partes.slice(1).join("").replace(/[^A-Z]/g, "");
}

// Porta de qualidade.PREFIXO_CIA: trecho do CRM sem cia (ex.: EF34GH, "TP58").
const PREFIXO_CIA: [string, string][] = [
  ["TAP", "TAP"], ["TAM", "LATAM"], ["LA", "LATAM"], ["JJ", "LATAM"],
  ["TP", "TAP"], ["G3", "GOL"], ["AD", "AZUL"], ["CM", "COPA"],
  ["QR", "QATAR AIRWAYS"], ["AF", "AIR FRANCE"],
];

export function ciaPeloVoo(cia: string | null, numeroVoo?: string | null): string | null {
  if (cia?.trim()) return cia.trim();
  const numero = (numeroVoo ?? "").trim().toUpperCase();
  return PREFIXO_CIA.find(([prefixo]) => numero.startsWith(prefixo))?.[1] ?? cia;
}

function linkTap(v: VooParaLink): string | null {
  const sobrenome = sobrenomeCompleto(v.passageiros);
  if (!sobrenome) return null;
  return `https://myb.flytap.com/my-bookings/details/${encodeURIComponent(v.localizador ?? "")}/${sobrenome}`;
}

function linkCopa(v: VooParaLink): string | null {
  const sobrenome = sobrenomeCompleto(v.passageiros);
  if (!sobrenome) return null;
  return `https://mytrips.copaair.com/trip-detail/${encodeURIComponent(v.localizador ?? "")}/${sobrenome}/pt`;
}

/**
 * Sem link direto possível (LATAM sem número de compra; Qatar abre sessão com
 * desafio anti-robô, sem rota por URL): página de busca da própria cia. Só no
 * site — no alerta do Telegram um link genérico seria ruído.
 */
const CONSULTA: Record<string, string> = {
  LATAM: "https://www.latamairlines.com/br/pt/minhas-viagens",
  "QATAR AIRWAYS": "https://www.qatarairways.com/pt-br/manage-booking.html",
};

function linkGol(v: VooParaLink): string {
  const params = new URLSearchParams({
    codigoReserva: v.localizador ?? "",
    origem: v.origem ?? "",
    sobrenome: sobrenome(v.passageiros),
  });
  return `https://b2c.voegol.com.br/minhas-viagens/encontrar-viagem?${params}`;
}

function linkAzul(v: VooParaLink): string {
  const params = new URLSearchParams({
    pnr: v.localizador ?? "",
    origin: v.origem ?? "",
  });
  return `https://www.voeazul.com.br/br/pt/home/minhas-viagens/confirmacao?${params}`;
}

function linkGenerico(_v: VooParaLink): string | null {
  return null;
}

function montadorPara(cia: string | null): (v: VooParaLink) => string | null {
  if (cia === "GOL") return linkGol;
  if (cia === "AZUL") return linkAzul;
  if (cia === "TAP") return linkTap;
  if (cia === "COPA") return linkCopa;
  return linkGenerico;
}

// Parâmetro de origem em cada portal.
const PARAM_ORIGEM: Record<string, string> = { GOL: "origem", AZUL: "origin" };

/**
 * Reescreve a origem do link para o trecho ainda não voado. O link do PDF é
 * gerado na emissão e congela a origem da ida — numa ida-e-volta consultada
 * depois da ida, ele aponta pro trecho que já aconteceu.
 */
function corrigirOrigem(
  url: string,
  voo: VooParaLink,
): { url: string; ajustada: boolean } {
  const chave = voo.cia ? PARAM_ORIGEM[voo.cia] : undefined;
  if (!chave || !voo.origem) return { url, ajustada: false };

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { url, ajustada: false };
  }

  const atual = (parsed.searchParams.get(chave) ?? "").toUpperCase();
  if (!atual || atual === voo.origem.toUpperCase()) return { url, ajustada: false };

  parsed.searchParams.set(chave, voo.origem);
  return { url: parsed.toString(), ajustada: true };
}

export type LinkReserva = { url: string; origemLink: string } | { url: null; origemLink: null };

/**
 * `doPdf`: mapa localizador (maiúsculo) -> url, vindo da tabela `links_pdf`
 * (alimentada pelo Mac na próxima leva — hoje fica vazia).
 */
export function linkPara(voo: VooParaLink, doPdf: Map<string, string>): LinkReserva {
  let url: string | null = doPdf.get((voo.localizador ?? "").toUpperCase()) ?? null;
  let origemLink = "PDF";

  if (url) {
    const corrigido = corrigirOrigem(url, voo);
    url = corrigido.url;
    if (corrigido.ajustada) origemLink = "PDF (origem ajustada)";
  }

  const cia = ciaPeloVoo(voo.cia, voo.numero_voo);
  if (!url) {
    const montador = montadorPara(cia);
    const podeMontar = sobrenome(voo.passageiros) !== "" || cia === "AZUL";
    url = podeMontar ? montador(voo) : null;
    origemLink = "montado";
  }

  if (!url && cia && CONSULTA[cia]) {
    url = CONSULTA[cia];
    origemLink = "busca da cia (digitar localizador)";
  }

  return url ? { url, origemLink } : { url: null, origemLink: null };
}
