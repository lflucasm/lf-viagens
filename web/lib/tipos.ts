import type { Database } from "@/lib/database.types";

export type Voo = Database["public"]["Tables"]["voos"]["Row"];
export type Historico = Database["public"]["Tables"]["historico"]["Row"];
export type Observacao = Database["public"]["Tables"]["observacoes"]["Row"];
export type Perfil = Database["public"]["Tables"]["perfis"]["Row"];
export type Nota = Database["public"]["Tables"]["notas"]["Row"];
export type SolicitacaoChecagem =
  Database["public"]["Tables"]["solicitacoes_checagem"]["Row"];
export type Pendencia = Database["public"]["Tables"]["pendencias"]["Row"];
export type LinkPdfRow = Database["public"]["Tables"]["links_pdf"]["Row"];

export const ROTULO_EVENTO: Record<string, string> = {
  novo: "Nova reserva",
  alterado: "Alterado pela companhia",
  confirmado: "Confirmado por outra fonte",
  sumiu: "Sumiu do CRM",
  reapareceu: "Reapareceu",
};

export const ICONE_EVENTO: Record<string, string> = {
  novo: "🆕",
  alterado: "🟠",
  confirmado: "✔️",
  sumiu: "🔴",
  reapareceu: "🟢",
};

/**
 * Nome legível de cada fonte gravada em historico.origem / observacoes.origem.
 * As "-cloud" e "volly-monitor" são os checadores da nuvem (src/checar_*_cloud.py);
 * as sem sufixo são as do Mac (rodada.py / checar_malha.py), que ainda aparecem
 * no histórico antigo.
 */
export const ROTULO_ORIGEM: Record<string, string> = {
  "volly-monitor": "Monitor Volly",
  "volly-monitor-plano": "Monitor Volly (simulação)",
  "malha-cloud": "Malha",
  "portal-latam-cloud": "Portal LATAM",
  "portal-gol-cloud": "Portal GOL",
  "portal-azul-cloud": "Portal Azul",
  "email-gol": "E-mail da GOL",
  "email-latam": "E-mail da LATAM",
  "email-azul": "E-mail da Azul",
  "email-tap": "E-mail da TAP",
  "email-copa": "E-mail da Copa",
  "email-qatar": "E-mail da Qatar",
  "email-iberia": "E-mail da Iberia",
  malha: "Malha (Mac)",
  "portal-latam": "Portal LATAM (Mac)",
  "portal-gol": "Portal GOL (Mac)",
  "portal-azul": "Portal Azul (Mac)",
  milhasflow: "CRM (Volly)",
};

/**
 * Texto claro para cada historico.campo — os tipos de src/alertas.py:ICONE e
 * os que malha.py, comparacao.py, latam.py, gol.py e azul.py emitem. Tipo
 * fora daqui aparece com o código cru (ver descreverAlerta).
 */
export const ROTULO_TIPO: Record<string, string> = {
  passageiro_remanejado: "Passageiro remanejado?",
  horario_venda_diverge: "Horário da companhia diferente da venda",
  horario_alterado: "Horário alterado",
  alterado_pela_companhia: "Alterado pela companhia",
  alteracao_voo: "Voo alterado",
  data_alterada: "Data do voo mudou",
  rota_alterada: "Rota alterada",
  voo_desviado: "Voo desviado",
  trecho_cancelado: "Trecho cancelado",
  cancelamento: "Cancelamento",
  possivel_cancelamento: "Possível cancelamento",
  reserva_perdida: "Reserva perdida",
  ausente_na_companhia: "Trecho não aparece na companhia",
  sem_voo_no_trecho: "Voo não encontrado no trecho",
  atraso: "Atraso",
  pagamento_pendente: "Pagamento pendente",
  em_contingencia: "Voo em contingência",
  reembolso: "Reembolso",
  status_desconhecido: "Status desconhecido na companhia",
  fontes_divergem: "Fontes discordam",
  sem_confirmacao: "Reserva sem confirmação",
  acao_necessaria: "Companhia pede ação na reserva",
  verificacao_incompleta: "Não deu para conferir o trecho",
  voo_novo_na_companhia: "Voo novo na companhia",
  // eventos do sync com o CRM (src/db.py:CAMPOS_MONITORADOS)
  embarque: "Embarque mudou no CRM",
  chegada: "Chegada mudou no CRM",
  numero_voo: "Número do voo mudou no CRM",
  origem: "Origem mudou no CRM",
  destino: "Destino mudou no CRM",
  status: "Status mudou no CRM",
};

const DIA = /(\d{4})-(\d{2})-(\d{2})/;

function diaCurto(texto: string): string {
  const m = DIA.exec(texto);
  return m ? `${m[3]}/${m[2]}` : texto;
}

/**
 * Reescreve o valor cru gravado pelos checadores (src/malha.py,
 * comparacao.py, checar_volly_cloud.divergencia_venda) num texto legível.
 * Formato que não reconhece volta cru, só com "->" virando "→".
 */
function detalheLegivel(campo: string | null, valor: string): string {
  let m: RegExpExecArray | null;
  // "em 2026-11-19: vendido MCZ-CGH 07:10 -> companhia GYN-CGH 08:40"
  if ((m = /^em (\S+): vendido (\w{3})-(\w{3}) ?(\S*) -> companhia (\w{3})-(\w{3}) ?(\S*)$/.exec(valor))) {
    const venda = `${m[2]} → ${m[3]}${m[4] ? ` ${m[4]}` : ""}`;
    const cia = `${m[5]} → ${m[6]}${m[7] ? ` ${m[7]}` : ""}`;
    return `${diaCurto(m[1])}: vendido ${venda} · hoje ${cia}`;
  }
  // "na venda 2026-10-28 09:00 -> na companhia 09:25"
  if ((m = /^na venda (?:\d{4}-\d{2}-\d{2} )?(\d{2}:\d{2}) -> na companhia (\d{2}:\d{2})$/.exec(valor))) {
    return `venda ${m[1]} → companhia ${m[2]}`;
  }
  // "visto antes 09:00 -> agora 09:25" (horário e rota)
  if ((m = /^visto antes (.+) -> agora (.+)$/.exec(valor))) {
    return `antes ${m[1]} → agora ${m[2]}`;
  }
  // "CRM 2026-10-28 -> companhia 2026-10-29"
  if (campo === "data_alterada" && (m = /^CRM (\S+) -> companhia (\S+)$/.exec(valor))) {
    return `venda ${diaCurto(m[1])} → companhia ${diaCurto(m[2])}`;
  }
  // "a companhia revisou o horario publicado: 09:00 -> 09:25"
  if ((m = /^a companhia revisou o horario publicado: (.+) -> (.+)$/.exec(valor))) {
    return `horário publicado ${m[1]} → ${m[2]}`;
  }
  return valor.replaceAll(" -> ", " → ");
}

/**
 * Rótulo, texto e fonte de um evento do histórico, prontos pra tela — em vez
 * de "horario_venda_diverge: na venda 2026-10-28 09:00 -> na companhia 09:25",
 * "Horário da venda não bate com a companhia" + "venda 09:00 → companhia 09:25"
 * + "Monitor Volly". Evento "confirmado" é a mesma mudança vista por uma
 * segunda fonte (src/nuvem_comum.gravar_achado): não é alerta novo.
 */
function minutos(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** Diferença pelo caminho mais curto (23:50 → 00:10 = 20 min mais tarde). */
function deltaMinutos(antes: string, depois: string): number {
  return ((minutos(depois) - minutos(antes) + 720) % 1440 + 1440) % 1440 - 720;
}

export function diferencaHorario(antes: string, depois: string): string {
  const delta = deltaMinutos(antes, depois);
  if (delta === 0) return "mesmo horário";
  const h = Math.floor(Math.abs(delta) / 60);
  const m = Math.abs(delta) % 60;
  const tamanho = h ? (m ? `${h}h${String(m).padStart(2, "0")}` : `${h}h`) : `${m} min`;
  return `${tamanho} ${delta > 0 ? "mais tarde" : "mais cedo"}`;
}

/**
 * Título com o essencial e o que provavelmente aconteceu, em texto curto —
 * pra ter o panorama antes de abrir a reserva (pedido do proprietário, 23/10/2026).
 * Mesma regra de src/alertas.py:explicar (Telegram).
 */
export function explicarAlerta(
  campo: string | null,
  valor: string,
  cia?: string | null,
): { titulo?: string; hipotese?: string } {
  const aCia = cia ? `a ${cia}` : "a companhia";
  const ACia = aCia[0].toUpperCase() + aCia.slice(1);
  const daCia = cia ? `da ${cia}` : "da companhia";
  let m: RegExpExecArray | null;

  if (campo === "passageiro_remanejado") {
    m = /vendido (\w{3})-(\w{3}).* -> companhia (\w{3})-(\w{3})/.exec(valor);
    if (!m) return { hipotese: "Esse voo agora faz outra rota: o passageiro deve ter sido remanejado. Confira a reserva no site da cia." };
    if (m[1] !== m[3]) {
      return { hipotese: `${ACia} tirou esse voo de ${m[1]} (agora sai de ${m[3]}). Provável que o passageiro tenha sido remanejado para outro voo: confira a reserva no site da cia.` };
    }
    return { hipotese: `O voo agora termina em ${m[4]}, não em ${m[2]}. Pode ser escala nova ou remanejamento: confira a reserva no site da cia.` };
  }

  if (campo === "horario_venda_diverge" || campo === "horario_alterado") {
    m = /(?:na venda (?:\d{4}-\d{2}-\d{2} )?|visto antes )(\d{2}:\d{2}) -> (?:na companhia |agora )(\d{2}:\d{2})/.exec(valor);
    if (!m) return {};
    const titulo = `Horário mudou: ${m[1]} → ${m[2]} (${diferencaHorario(m[1], m[2])})`;
    if (campo === "horario_alterado") {
      return { titulo, hipotese: `${ACia} mudou o horário desde a última conferência. Avise o passageiro.` };
    }
    if (Math.abs(deltaMinutos(m[1], m[2])) >= 30) {
      return { titulo, hipotese: `Provável: ${aCia} mudou o horário depois da venda (ou a venda foi digitada errada). Confirme e avise o passageiro.` };
    }
    return { titulo, hipotese: `Provável: ajuste pequeno ${daCia} na malha ou arredondamento na venda.` };
  }

  if (campo === "data_alterada") {
    m = /CRM (\S+) -> companhia (\S+)/.exec(valor);
    return {
      titulo: m ? `Data mudou: ${diaCurto(m[1])} → ${diaCurto(m[2])}` : undefined,
      hipotese: `Provável: ${aCia} passou o voo para outro dia (ou a venda está com a data errada).`,
    };
  }
  if (campo === "sem_voo_no_trecho") {
    return { hipotese: "O voo não aparece mais nesse trecho: pode ter sido cancelado ou trocado de número. Confira a reserva." };
  }
  if (campo === "rota_alterada") {
    return { hipotese: `${ACia} mudou a rota desde a última conferência; o passageiro pode ter sido remanejado.` };
  }
  return {};
}

function nomeBonito(nome: string): string {
  return nome
    .toLowerCase()
    .replace(/(^|\s)(\p{L})/gu, (_, espaco, letra) => espaco + letra.toUpperCase())
    .replace(/ (Da|De|Do|Das|Dos|E)(?= )/g, (p) => p.toLowerCase());
}

/**
 * Mensagem pronta pra copiar e mandar ao passageiro (19/11/2026, ideia da
 * Traveos "Notificar passageiro"). Só pros tipos em que a mudança é certa;
 * remanejamento, rota e "não aparece na companhia" pedem conferir a reserva
 * antes e devolvem null. Leva o nome de todos os passageiros.
 */
export function mensagemPassageiro(
  campo: string | null,
  valor: string,
  voo: {
    cia: string | null;
    numero_voo: string | null;
    origem: string | null;
    destino: string | null;
    embarque: string | null;
    passageiros: string | null;
  },
): string | null {
  const nomes = nomesPassageiros(voo.passageiros, 10);
  const saudacao = nomes ? `Olá, ${nomeBonito(nomes)}!` : "Olá!";
  const aCia = voo.cia ? `a ${voo.cia}` : "a companhia";
  const trecho = voo.origem && voo.destino ? ` (${voo.origem} → ${voo.destino})` : "";
  const dia = voo.embarque ? ` de ${diaCurto(voo.embarque)}` : "";
  const numero = voo.numero_voo ? ` ${voo.numero_voo}` : "";
  const fim = "Qualquer dúvida, estamos à disposição. LF Viagens";
  let m: RegExpExecArray | null;

  if (campo === "horario_alterado" || campo === "horario_venda_diverge") {
    m = /(?:na venda (?:\d{4}-\d{2}-\d{2} )?|visto antes )(\d{2}:\d{2}) -> (?:na companhia |agora )(\d{2}:\d{2})/.exec(valor);
    if (!m || m[1] === m[2]) return null;
    return `${saudacao} Passando para avisar que ${aCia} alterou o horário do voo${numero}${trecho}${dia}: era ${m[1]} e agora é ${m[2]} (${diferencaHorario(m[1], m[2])}). Sua reserva continua confirmada. ${fim}`;
  }
  if (campo === "data_alterada") {
    m = /CRM (\S+) -> companhia (\S+)/.exec(valor);
    if (!m) return null;
    return `${saudacao} Passando para avisar que ${aCia} mudou a data do voo${numero}${trecho}: era ${diaCurto(m[1])} e agora é ${diaCurto(m[2])}. Se a nova data não servir, fale com a gente que verificamos as opções. ${fim}`;
  }
  if (campo === "cancelamento" || campo === "trecho_cancelado") {
    return `${saudacao} ${aCia[0].toUpperCase() + aCia.slice(1)} cancelou o voo${numero}${trecho}${dia}. Já estamos vendo as opções de remarcação e retornamos em seguida. ${fim}`;
  }
  return null;
}

export function descreverAlerta(
  h: {
    evento: string;
    campo: string | null;
    valor_antigo: string | null;
    valor_novo: string | null;
    origem: string;
  },
  cia?: string | null,
): { titulo: string; detalhe: string; fonte: string; hipotese?: string } {
  const fonte = ROTULO_ORIGEM[h.origem] ?? h.origem;
  const explicacao = explicarAlerta(h.campo, (h.valor_novo ?? "").trim(), cia);
  const tipo =
    explicacao.titulo ??
    (h.campo ? (ROTULO_TIPO[h.campo] ?? h.campo) : (ROTULO_EVENTO[h.evento] ?? h.evento));
  const titulo = h.evento === "confirmado" ? "Confirmado por outra fonte" : tipo;

  const novo = (h.valor_novo ?? "").trim();
  const antigo = (h.valor_antigo ?? "").trim();
  let detalhe = novo ? detalheLegivel(h.campo, novo) : "";
  if (antigo) detalhe = `${antigo} → ${novo || "(vazio)"}`;
  // no "confirmado" o título já é fixo; o tipo vai junto pra saber o que foi
  // confirmado
  if (h.evento === "confirmado" && h.campo) {
    detalhe = detalhe ? `${tipo}: ${detalhe}` : tipo;
  }
  // confirmação não repete a explicação: ela já está no alerta original
  const hipotese = h.evento === "confirmado" ? undefined : explicacao.hipotese;
  return { titulo, detalhe, fonte, hipotese };
}

/**
 * Mesma regra de src/rodada.py:alertas_pendentes — só evento "alterado" que
 * não veio do próprio sync do MilhasFlow vira alerta de verdade (é o que vai
 * pro Telegram hoje). "novo"/"reapareceu" são só registro; sem isso todo
 * evento de histórico aparecia como pendência na aba Urgente.
 */
export function ehAlerta(h: { evento: string; origem: string }): boolean {
  return h.evento === "alterado" && h.origem !== "milhasflow";
}

/**
 * Todos os passageiros da reserva pra mostrar junto de cada mensagem de voo
 * ("A, B e C" / "... +2") — pedido do proprietário em 27/09/2026. Mesma regra de
 * src/qualidade.py:nomes_passageiros (o CRM separa por " / ").
 */
function semAcento(texto: string): string {
  return texto.normalize("NFD").replace(/\p{Diacritic}+/gu, "").toLowerCase();
}

/**
 * Busca por nome de passageiro: cada palavra digitada precisa aparecer em
 * algum dos nomes, sem diferenciar maiúscula nem acento — "joao silva" acha
 * "JOÃO PEDRO DA SILVA".
 */
export function passageiroCorresponde(passageiros: string | null | undefined, busca: string): boolean {
  const palavras = semAcento(busca).split(/\s+/).filter(Boolean);
  if (palavras.length === 0) return true;
  const nomes = (passageiros ?? "").split(" / ").map(semAcento);
  return nomes.some((nome) => palavras.every((p) => nome.includes(p)));
}

export function nomesPassageiros(passageiros: string | null | undefined, limite = 4): string {
  const nomes: string[] = [];
  for (const bruto of (passageiros ?? "").split(" / ")) {
    const nome = bruto.split(/\s+/).filter(Boolean).join(" ");
    if (nome && !nomes.includes(nome)) nomes.push(nome);
  }
  if (nomes.length === 0) return "";
  if (nomes.length > limite) return `${nomes.slice(0, limite).join(", ")} +${nomes.length - limite}`;
  if (nomes.length === 1) return nomes[0];
  return `${nomes.slice(0, -1).join(", ")} e ${nomes[nomes.length - 1]}`;
}
