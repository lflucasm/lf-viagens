"""Ritmo de pessoa pras consultas ao "Monitorar voo" da Volly.

Pedido do proprietário em 28/09/2026: a checagem nao pode ter cara de robo - nada
de rajada de consultas no comeco de cada hora com 1s entre uma e outra (o
padrao ate aqui). O monitor agora abre uma "sessao" como alguem da equipe
faria: consulta um voo, olha, espera um tempo irregular, consulta o proximo;
de vez em quando se distrai; de madrugada quase nao aparece.

Desde 15/10/2026 a rodada agendada do monitor e em rajada (sem --humano):
as sessoes dormindo no runner esgotaram a cota de minutos do GitHub
Actions. Isto continua valendo pro disparo manual com --humano e pela
validade da leitura por faixa (VENCIMENTO_POR_FAIXA), que segue em uso.

Tudo aqui e puro (recebe `rng` e `agora`) pra dar pra testar sem esperar.
O checar_volly_cloud.py e quem dorme de verdade entre as consultas.
"""

import math
from datetime import timedelta, timezone

BRT = timezone(timedelta(hours=-3))

# Horario de gente (Brasilia). Fora dele so voo que embarca em menos de
# HORAS_URGENTE, e nem sempre.
HORA_INICIO = 7
HORA_FIM = 23
HORAS_URGENTE = 24
CHANCE_MADRUGADA = 0.35       # rodada da madrugada que olha algum urgente
MAX_MADRUGADA = 1

# Sessao: dura entre 20 e 45 min e nunca passa do teto (o token da Volly e
# renovado antes de cada sessao e vale 1h - ver checar-volly-cloud.yml).
SESSAO_MIN_S = 20 * 60
SESSAO_MAX_S = 45 * 60
CHANCE_SEM_SESSAO = 0.10      # hora em que "ninguem olhou"

# Entre uma consulta e outra: log-normal com mediana de ~90s, entre 35s e
# 6 min, e de vez em quando uma pausa longa (atendeu cliente, cafe...).
PAUSA_MEDIANA_S = 90
PAUSA_SIGMA = 0.55
PAUSA_MIN_S = 35
PAUSA_MAX_S = 6 * 60
CHANCE_PAUSA_LONGA = 0.08
PAUSA_LONGA_S = (5 * 60, 10 * 60)

# Inicio da sessao nao cai certinho no minuto do cron
ATRASO_INICIAL_S = (0, 6 * 60)

# Quanto tempo cada leitura vale, por proximidade do embarque. Recalibrado
# pro ritmo de pessoa (bem menos consultas por hora que a rajada): voo
# distante nao precisa ser olhado duas vezes por dia.
VENCIMENTO_POR_FAIXA = (    # (embarque em ate X horas, leitura vale Y horas)
    (24, 4),
    (7 * 24, 10),
    (30 * 24, 16),
    (None, 30),
)


def agora_brt(agora):
    return agora.astimezone(BRT)


def horario_ativo(agora):
    """Das 7h as 23h de Brasilia."""
    return HORA_INICIO <= agora_brt(agora).hour < HORA_FIM


def horas_de_validade(horas_ate_embarque):
    """Quantas horas uma leitura da Volly vale pra este voo."""
    for limite, horas in VENCIMENTO_POR_FAIXA:
        if limite is None or (horas_ate_embarque is not None and horas_ate_embarque <= limite):
            return horas
    return VENCIMENTO_POR_FAIXA[-1][1]


def vencido(idade, horas_ate_embarque):
    """A leitura precisa ser renovada? `idade` None = nunca leu."""
    if idade is None:
        return True
    return idade >= horas_de_validade(horas_ate_embarque)


def plano_da_sessao(rng, agora):
    """{"ativa", "duracao_s", "maximo", "so_urgentes", "atraso_inicial_s"}.

    `maximo` None = sem teto proprio (so o tempo da sessao e o orcamento da
    Volly limitam)."""
    if horario_ativo(agora):
        if rng.random() < CHANCE_SEM_SESSAO:
            return {"ativa": False, "motivo": "hora sem consulta (natural)"}
        return {"ativa": True, "so_urgentes": False, "maximo": None,
                "duracao_s": rng.uniform(SESSAO_MIN_S, SESSAO_MAX_S),
                "atraso_inicial_s": rng.uniform(*ATRASO_INICIAL_S)}
    if rng.random() >= CHANCE_MADRUGADA:
        return {"ativa": False, "motivo": "madrugada"}
    return {"ativa": True, "so_urgentes": True, "maximo": MAX_MADRUGADA,
            "duracao_s": SESSAO_MIN_S, "atraso_inicial_s": rng.uniform(*ATRASO_INICIAL_S)}


def pausa(rng):
    """Segundos ate a proxima consulta."""
    if rng.random() < CHANCE_PAUSA_LONGA:
        return rng.uniform(*PAUSA_LONGA_S)
    valor = rng.lognormvariate(math.log(PAUSA_MEDIANA_S), PAUSA_SIGMA)
    return max(PAUSA_MIN_S, min(PAUSA_MAX_S, valor))


def faixa(horas_ate_embarque):
    """0 = embarca em <24h, 1 = <7d, 2 = <30d, 3 = mais longe/desconhecido."""
    for i, (limite, _) in enumerate(VENCIMENTO_POR_FAIXA):
        if limite is None or (horas_ate_embarque is not None and horas_ate_embarque <= limite):
            return i
    return len(VENCIMENTO_POR_FAIXA) - 1


def ordem_humana(itens, rng, horas_de):
    """Urgentes primeiro, mas dentro de cada faixa a ordem e embaralhada -
    ninguem percorre a lista na mesma ordem exata toda vez.
    `horas_de(item)` -> horas ate o embarque."""
    grupos = {}
    for item in itens:
        grupos.setdefault(faixa(horas_de(item)), []).append(item)
    ordem = []
    for f in sorted(grupos):
        lista = list(grupos[f])
        rng.shuffle(lista)
        ordem += lista
    return ordem
