import "server-only";

// Dispara checagens via GitHub Actions workflow_dispatch, filtradas pra um
// localizador so - o "botao checar agora" do painel. Desde 26/09/2026 tudo
// roda na nuvem: monitor Volly, portal da companhia (LATAM/GOL/Azul) e
// malha. A fila do Mac (solicitacoes_checagem) nao recebe mais pedido
// daqui - o Mac esta parado desde 15/09 e ia ser desligado de vez.
const REPO = "lflucasm/lf-viagens";

async function dispararWorkflow(
  workflow: string,
  inputs: Record<string, string>,
): Promise<{ ok: boolean; erro?: string }> {
  const token = process.env.GITHUB_ACTIONS_TOKEN;
  if (!token) {
    return { ok: false, erro: "GITHUB_ACTIONS_TOKEN não configurado" };
  }

  const resposta = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    },
  );

  if (!resposta.ok) {
    const texto = await resposta.text();
    return { ok: false, erro: `GitHub API ${resposta.status}: ${texto.slice(0, 200)}` };
  }
  return { ok: true };
}

export async function dispararChecagemMalha(localizador: string) {
  return dispararWorkflow("checar-malha.yml", { loc: localizador });
}

// Portal de cada companhia (a unica fonte que ve a reserva do passageiro:
// cancelamento, reacomodacao). Companhia fora daqui nao tem portal na
// nuvem - quem chama cai pra malha.
const WORKFLOW_PORTAL: Record<string, string> = {
  LATAM: "checar-latam-cloud.yml",
  GOL: "checar-gol-cloud.yml",
  AZUL: "checar-azul-cloud.yml",
};

export function temPortal(cia: string) {
  return cia.toUpperCase() in WORKFLOW_PORTAL;
}

export async function dispararChecagemCia(cia: string, localizador: string) {
  const workflow = WORKFLOW_PORTAL[cia.toUpperCase()];
  if (!workflow) {
    return { ok: false, erro: `sem portal na nuvem para ${cia || "cia vazia"}` };
  }
  return dispararWorkflow(workflow, { loc: localizador });
}

// Monitor Volly so pra essa reserva: com --loc ele reconsulta mesmo com a
// leitura ainda dentro do intervalo de 10h (ver checar_volly_cloud.py).
export async function dispararChecagemVolly(localizador: string) {
  return dispararWorkflow("checar-volly-cloud.yml", { loc: localizador });
}

// Reconferencia depois do "Verificado — passageiro avisado": le a companhia
// de novo e grava em propostas_volly o que mudaria no cadastro da Volly
// (reconferir.yml / src/reconferir_cloud.py). So propoe - nao escreve na
// Volly (spec do fluxo na nuvem, parte 4, 26/09/2026).
export async function dispararReconferencia(vooId: string, historicoId: number) {
  return dispararWorkflow("reconferir.yml", {
    voo_id: vooId,
    historico_id: String(historicoId),
  });
}

// "Aplicar na Volly" numa proposta: grava a correcao no trecho da Volly
// (aplicar-volly.yml / src/aplicar_volly_cloud.py). Enquanto a variavel
// APLICAR_VOLLY do repositorio nao for "real", o robo so simula.
export async function dispararAplicacaoVolly(propostaId: number) {
  return dispararWorkflow("aplicar-volly.yml", { proposta_id: String(propostaId) });
}
