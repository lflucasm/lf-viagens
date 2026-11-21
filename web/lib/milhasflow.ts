import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { dataIsoParaBr, formatarCpf, type Programa } from "@/lib/cedentes";

// Cabeçalho de navegador comum nas chamadas à Volly, em vez do padrão do
// Node — mesmo cabeçalho do lado Python (src/milhasflow.py,
// USER_AGENT_NAVEGADOR), pedido do proprietário em 28/09/2026.
const USER_AGENT_NAVEGADOR =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";

/**
 * Envio de uma conta de cedente aprovada para o MilhasFlow (o CRM de
 * terceiros que a agência já usa, fora deste repo).
 *
 * Schema descoberto na prática em 20/08/2026 (não documentado — MilhasFlow
 * não expõe o /rest/v1/ raiz, então não dá pra introspectar; ver
 * scripts/descobrir_tabelas_milhasflow.py). A tabela é `miles_accounts`, com
 * UMA LINHA POR CONTA DE PROGRAMA, não uma por cedente: quem tem LATAM Pass
 * + Smiles + Livelo vira três linhas lá, cada uma repetindo nome/CPF/e-mail/
 * nascimento e com program/username/password próprios. Por isso o envio
 * aqui também é por conta — ver enviarConta() — e o rastro de "já subiu"
 * fica em cedente_contas, não em cedentes.
 *
 * Nomes de programa confirmados na tabela: 'LATAM Pass', 'Smiles', 'Livelo',
 * 'Esfera' (também existem 'Azul Fidelidade', 'C6 Átomos' e 'TAP', que a
 * gente não cadastra). E-mail não é um programa de milhas — não gera linha.
 */

const URL_PADRAO = "https://SEU_PROJETO_MILHASFLOW.supabase.co";
const ORGANIZATION_ID_PADRAO = "00000000-0000-0000-0000-000000000000";

const NOME_PROGRAMA_MILHASFLOW: Partial<Record<Programa, string>> = {
  latam: "LATAM Pass",
  smiles: "Smiles",
  livelo: "Livelo",
  esfera: "Esfera",
};

export type ContaParaCrm = {
  nomeCompleto: string;
  cpf: string;
  dataNascimentoIso: string;
  emailCriado: string | null;
  telefone: string | null;
  programa: Programa;
  senha: string;
  pontosIniciais: number;
};

type TelefoneMilhasflow = { id: string; type: string; label: string; number: string };

export type ResultadoEnvio =
  | { ok: true; id: string | null }
  | { ok: false; motivo: "nao_configurado" | "programa_invalido" | "falha"; detalhe: string };

// MILHASFLOW_EMAIL/MILHASFLOW_SENHA não entram mais aqui: eram só pro login
// por senha (grant_type=password), desativado pelo captcha que o MilhasFlow
// ligou em 14/09/2026 — ver o comentário em token(), mais abaixo.
export function milhasflowConfigurado() {
  return Boolean(process.env.MILHASFLOW_ANON_KEY);
}

const MILHASFLOW_AUTH_ID = "lfviagens";

/**
 * Cliente pro Supabase DESTA agência (não o do MilhasFlow) — é onde fica
 * milhasflow_auth_state. Sem tipo <Database> de propósito: essa tabela é
 * infraestrutura de integração, não schema do app (mesmo padrão de
 * app/api/extensao/milhasflow-token/route.ts, que é quem escreve nela a
 * partir do token que a extensão captura).
 */
function clienteEstadoAuth() {
  return createSupabaseClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );
}

type EstadoAuthMilhasflow = { access_token: string | null; refresh_token: string; expira_em: number | null };

async function lerEstadoAuth(): Promise<EstadoAuthMilhasflow | null> {
  const { data } = await clienteEstadoAuth()
    .from("milhasflow_auth_state")
    .select("access_token, refresh_token, expira_em")
    .eq("id", MILHASFLOW_AUTH_ID)
    .maybeSingle();
  return (data as EstadoAuthMilhasflow | null) ?? null;
}

/**
 * Perder essa escrita é grave: o refresh_token que acabou de ser trocado já
 * foi consumido do lado do MilhasFlow (é rotativo, uso único) — se o valor
 * novo não for salvo, a próxima chamada (daqui, dos scripts em Python ou da
 * extensão) tenta reusar um token já queimado e cai em
 * "refresh_token_already_used". Por isso repete com espera crescente em vez
 * de deixar passar batido (mesma receita de src/milhasflow.py).
 */
async function salvarEstadoAuth(novo: {
  access_token: string;
  refresh_token: string;
  expira_em: number;
}) {
  let ultimoErro: unknown = null;
  for (let tentativa = 0; tentativa < 3; tentativa++) {
    const { error } = await clienteEstadoAuth()
      .from("milhasflow_auth_state")
      .upsert(
        {
          id: MILHASFLOW_AUTH_ID,
          access_token: novo.access_token,
          refresh_token: novo.refresh_token,
          expira_em: novo.expira_em,
          updated_at: new Date().toISOString(),
        },
        { onConflict: "id" },
      );
    if (!error) return;
    ultimoErro = error;
    if (tentativa < 2) await new Promise((r) => setTimeout(r, 1500 * (tentativa + 1)));
  }
  console.error("MilhasFlow: não consegui salvar o token renovado depois de 3 tentativas", ultimoErro);
}

async function autenticarViaRefresh(refreshToken: string) {
  const base = process.env.MILHASFLOW_URL || URL_PADRAO;
  const resposta = await fetch(`${base}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: {
      apikey: process.env.MILHASFLOW_ANON_KEY!,
      "User-Agent": USER_AGENT_NAVEGADOR,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });

  if (!resposta.ok) {
    const detalhe = (await resposta.text()).slice(0, 400);
    throw new Error(`HTTP ${resposta.status}: ${detalhe}`);
  }

  const dados = (await resposta.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  };
  if (!dados.access_token || !dados.refresh_token) {
    throw new Error("refresh no MilhasFlow não devolveu token");
  }
  return dados as { access_token: string; refresh_token: string; expires_in?: number };
}

let tokenCache: { token: string; expiraEm: number } | null = null;

/**
 * O MilhasFlow ligou proteção de captcha no login por senha em 14/09/2026 —
 * grant_type=password sempre falha aqui (nunca temos como resolver o
 * desafio num processo sem navegador). grant_type=refresh_token não passa
 * por captcha, então a autenticação depende inteiramente do refresh_token
 * guardado em milhasflow_auth_state — a mesma linha que a extensão Chrome
 * mantém renovada captando a sessão de uma aba logada de verdade (ver
 * app/api/extensao/milhasflow-token/route.ts) e que os scripts em Python já
 * usam (src/milhasflow.py). Se essa linha ficar vazia (extensão nunca abriu
 * a aba, ou o refresh morreu de vez), não tem contorno automático — precisa
 * de alguém logado no MilhasFlow com a extensão ativa pra repovoar.
 */
async function token() {
  const agora = Date.now();
  if (tokenCache && tokenCache.expiraEm - 60_000 > agora) return tokenCache.token;

  const estado = await lerEstadoAuth();
  if (!estado?.refresh_token) {
    throw new Error(
      "login no MilhasFlow falhou: nenhum token de sessão guardado — abra o MilhasFlow no Chrome com a extensão da LF Viagens ativa pra renovar",
    );
  }

  let tentativa = estado.refresh_token;
  let ultimoErro: unknown = null;

  for (let indice = 0; indice < 5; indice++) {
    try {
      const dados = await autenticarViaRefresh(tentativa);
      await salvarEstadoAuth({
        access_token: dados.access_token,
        refresh_token: dados.refresh_token,
        expira_em: Math.floor(agora / 1000) + (dados.expires_in ?? 3600),
      });
      tokenCache = {
        token: dados.access_token,
        expiraEm: agora + (dados.expires_in ?? 3600) * 1000,
      };
      return tokenCache.token;
    } catch (e) {
      ultimoErro = e;
      if (indice < 4) {
        await new Promise((r) => setTimeout(r, 2000 * (indice + 1)));
        // Outro processo (script em Python, extensão) pode ter girado o
        // token entre a leitura e agora — confere se já tem um mais novo
        // antes de desistir, mesma corrida tratada em src/milhasflow.py.
        const relido = await lerEstadoAuth();
        if (relido?.refresh_token && relido.refresh_token !== tentativa) {
          tentativa = relido.refresh_token;
        }
      }
    }
  }

  throw new Error(
    `login no MilhasFlow falhou: ${ultimoErro instanceof Error ? ultimoErro.message : String(ultimoErro)}`,
  );
}

/**
 * O WhatsApp de contato de um programa é UMA lista compartilhada por todos
 * os cedentes daquele programa na agência (tabela `loyalty_program_contacts`,
 * uma linha por par organization_id+program — descoberto pela tela
 * "Contatos" no painel do MilhasFlow: o aviso "compartilhado entre todas as
 * contas deste programa" é literal, é o org inteiro, não por cedente). Por
 * isso NUNCA sobrescreve a lista — busca a atual, acrescenta o número do
 * cedente só se ainda não estiver lá (reenviar uma conta já enviada não deve
 * duplicar a entrada), e grava a lista de volta inteira.
 *
 * Falha aqui nunca derruba o envio da conta em si — é um extra, não o
 * cadastro da conta de milhas.
 */
async function garantirTelefoneNoPrograma(
  base: string,
  organizationId: string,
  programaMilhasflow: string,
  nomeCompleto: string,
  telefone: string,
) {
  const cabecalhosComuns = {
    apikey: process.env.MILHASFLOW_ANON_KEY!,
    "User-Agent": USER_AGENT_NAVEGADOR,
    Authorization: `Bearer ${await token()}`,
  };

  const respostaAtual = await fetch(
    `${base}/rest/v1/loyalty_program_contacts` +
      `?organization_id=eq.${encodeURIComponent(organizationId)}` +
      `&program=eq.${encodeURIComponent(programaMilhasflow)}` +
      `&select=phones`,
    { headers: cabecalhosComuns, cache: "no-store" },
  );
  if (!respostaAtual.ok) return;

  const linhas = (await respostaAtual.json()) as Array<{ phones: TelefoneMilhasflow[] | null }>;
  const telefonesAtuais = linhas[0]?.phones ?? [];

  if (telefonesAtuais.some((t) => t.number === telefone)) return;

  const novoTelefone: TelefoneMilhasflow = {
    id: Math.random().toString(36).slice(2, 10),
    type: "whatsapp",
    label: nomeCompleto,
    number: telefone,
  };

  await fetch(`${base}/rest/v1/loyalty_program_contacts?on_conflict=organization_id,program`, {
    method: "POST",
    headers: {
      ...cabecalhosComuns,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify({
      organization_id: organizationId,
      program: programaMilhasflow,
      phones: [...telefonesAtuais, novoTelefone],
    }),
    cache: "no-store",
  });
}

export async function enviarConta(conta: ContaParaCrm): Promise<ResultadoEnvio> {
  if (!milhasflowConfigurado()) {
    return {
      ok: false,
      motivo: "nao_configurado",
      detalhe: "Envio para o MilhasFlow ainda não está configurado nesta instalação.",
    };
  }

  const programaMilhasflow = NOME_PROGRAMA_MILHASFLOW[conta.programa];
  if (!programaMilhasflow) {
    return {
      ok: false,
      motivo: "programa_invalido",
      detalhe: `"${conta.programa}" não é uma conta de milhas — não é enviado ao MilhasFlow.`,
    };
  }

  const base = process.env.MILHASFLOW_URL || URL_PADRAO;
  const organizationId = process.env.MILHASFLOW_ORGANIZATION_ID || ORGANIZATION_ID_PADRAO;

  // username é o CPF (é como o MilhasFlow identifica a conta na listagem,
  // não o login que o cedente usa no site do programa em si — confirmado
  // comparando contas corrigidas manualmente no painel deles).
  // status fica de fora: a conta acabou de ser criada, deixa o MilhasFlow
  // aplicar o default dele em vez de mandar "ativa" sem ter certeza do que
  // significa pra conta como um todo.
  // club_active vai explícito como false: é campo separado de status (visto
  // no payload real de uma conta com clube configurado — tem club_active,
  // club_due_day, club_monthly_cost, club_points_monthly, club_reminder_enabled
  // além de status), e o default do MilhasFlow pra ele é true — sem mandar
  // false aqui, toda conta recém-criada nasce com "Clube Ativo" marcado antes
  // da adesão ao clube realmente acontecer (etapa posterior e manual).
  const payload = {
    name: conta.nomeCompleto,
    program: programaMilhasflow,
    username: formatarCpf(conta.cpf),
    password: conta.senha,
    balance: conta.pontosIniciais,
    holder_email: conta.emailCriado,
    holder_birthday: dataIsoParaBr(conta.dataNascimentoIso),
    holder_cpf: formatarCpf(conta.cpf),
    organization_id: organizationId,
    club_active: false,
  };

  try {
    const resposta = await fetch(`${base}/rest/v1/miles_accounts`, {
      method: "POST",
      headers: {
        apikey: process.env.MILHASFLOW_ANON_KEY!,
        "User-Agent": USER_AGENT_NAVEGADOR,
        Authorization: `Bearer ${await token()}`,
        "Content-Type": "application/json",
        Prefer: "return=representation",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    if (!resposta.ok) {
      const detalhe = (await resposta.text()).slice(0, 400);
      return { ok: false, motivo: "falha", detalhe: `HTTP ${resposta.status}: ${detalhe}` };
    }

    if (conta.telefone) {
      try {
        await garantirTelefoneNoPrograma(
          base,
          organizationId,
          programaMilhasflow,
          conta.nomeCompleto,
          conta.telefone,
        );
      } catch {
        // Extra, não o cadastro da conta — segue o jogo mesmo se falhar.
      }
    }

    const criado = (await resposta.json()) as Array<{ id?: string }>;
    return { ok: true, id: criado[0]?.id ? String(criado[0].id) : null };
  } catch (e) {
    return { ok: false, motivo: "falha", detalhe: e instanceof Error ? e.message : String(e) };
  }
}

/**
 * "Enviar aviso ao cliente" (20/11/2026): agenda `mensagem` na Volly pro
 * cliente da emissão, com horário = agora. A Volly manda pelo WhatsApp dela
 * em ~1 min (mesma fila que o robô do CRM usa, src/milhasflow.py
 * mover_cotacao_crm). Formato copiado das linhas reais de embarque/
 * aniversário: sem cotação, is_auto=false e sem auto_key, pra nenhuma
 * rotina automática da Volly cancelar ou repetir.
 */
export async function enviarAvisoCliente(
  emissaoId: string,
  mensagem: string,
): Promise<{ ok: true; id: string } | { ok: false; detalhe: string }> {
  if (!milhasflowConfigurado()) return { ok: false, detalhe: "Volly não configurada nesta instalação." };
  const base = process.env.MILHASFLOW_URL || URL_PADRAO;
  const organizationId = process.env.MILHASFLOW_ORGANIZATION_ID || ORGANIZATION_ID_PADRAO;

  try {
    const cabecalhos = {
      apikey: process.env.MILHASFLOW_ANON_KEY!,
      "User-Agent": USER_AGENT_NAVEGADOR,
      Authorization: `Bearer ${await token()}`,
    };
    const r = await fetch(
      `${base}/rest/v1/emissions?id=eq.${encodeURIComponent(emissaoId)}` +
        `&select=client_id,client:clients(phone,phone_country_code)`,
      { headers: cabecalhos, cache: "no-store" },
    );
    if (!r.ok) return { ok: false, detalhe: `Volly: HTTP ${r.status} ao ler a emissão` };
    const [emissao] = (await r.json()) as Array<{
      client_id: string | null;
      client: { phone: string | null; phone_country_code: string | null } | null;
    }>;
    const telefone = (emissao?.client?.phone ?? "").replace(/\D/g, "");
    if (!emissao?.client_id || !telefone) {
      return { ok: false, detalhe: "Cliente da venda sem telefone na Volly." };
    }

    const criado = await fetch(`${base}/rest/v1/crm_quote_scheduled_messages`, {
      method: "POST",
      headers: { ...cabecalhos, "Content-Type": "application/json", Prefer: "return=representation" },
      body: JSON.stringify({
        organization_id: organizationId,
        client_id: emissao.client_id,
        client_phone: telefone,
        phone_country_code: emissao.client?.phone_country_code || "55",
        message: mensagem,
        scheduled_at: new Date().toISOString(),
        status: "pending",
        context_type: "embarque",
        is_auto: false,
        auto_key: null,
        quote_id: null,
      }),
      cache: "no-store",
    });
    if (!criado.ok) return { ok: false, detalhe: `Volly: HTTP ${criado.status} ${(await criado.text()).slice(0, 200)}` };
    const [linha] = (await criado.json()) as Array<{ id: string }>;
    return { ok: true, id: linha.id };
  } catch (e) {
    return { ok: false, detalhe: e instanceof Error ? e.message : String(e) };
  }
}
