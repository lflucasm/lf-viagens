"""Atende a fila de checagens sob demanda pedidas pelo botao "Checar agora"
do painel web (tabela solicitacoes_checagem no Supabase).

So cobre LATAM/GOL/Azul - dependem do Chrome/PDFs deste Mac, por isso o
pedido fica numa fila em vez de rodar na hora (ver painel.link_para e o
README, secao "malha" x "portal", pro motivo dessa separacao). A malha
(AeroDataBox) nao passa por aqui: o botao dispara o GitHub Actions direto,
sem precisar do Mac.

Cada solicitacao pendente vira uma chamada de `checar_<cia>.py --loc
<localizador>` - a MESMA checagem individual que ja existe pra diagnostico,
so que disparada pela fila em vez da linha de comando. O resultado (saida
das ultimas linhas do comando) fica em `resultado`, pro colaborador ver o
que aconteceu sem abrir o Telegram.

Uso:  .venv/bin/python src/atender_solicitacoes.py
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import supabase_rest
from config import config

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(RAIZ, ".venv/bin/python")

# Um checador por cia - mesmo --loc que cada um ja aceita para diagnostico.
SCRIPT_POR_CIA = {
    "LATAM": "src/checar_latam.py",
    "GOL": "src/checar_gol.py",
    "AZUL": "src/checar_azul.py",
}

# A Azul e cautelosa com rajada (ver checar_azul.py) - nao ha por que isso
# afetar o atendimento sob demanda, mas o teto de tempo evita que uma
# checagem trave o poller pra sempre.
TIMEOUT_SEGUNDOS = 5 * 60


def pendentes(supabase_url, service_key):
    return supabase_rest.select(supabase_url, service_key, "solicitacoes_checagem", {
        "status": "eq.pendente",
        "select": "id,voo_id,localizador,cia,solicitado_em",
        "order": "solicitado_em.asc",
    })


def marcar(supabase_url, service_key, id_, status, resultado):
    supabase_rest.atualizar(
        supabase_url, service_key, "solicitacoes_checagem",
        {"id": "eq.%d" % id_},
        {"status": status, "resultado": resultado[:500],
         "concluido_em": "now()"},
    )


def atender_uma(solicitacao):
    cia = (solicitacao.get("cia") or "").upper()
    loc = solicitacao["localizador"]
    script = SCRIPT_POR_CIA.get(cia)
    if not script:
        return "erro", "companhia '%s' nao tem checagem individual (so malha, via GitHub Actions)" % cia

    comando = [PYTHON, script, "--loc", loc]
    print("  -> %s" % " ".join(comando))
    try:
        r = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True,
                           timeout=TIMEOUT_SEGUNDOS)
    except subprocess.TimeoutExpired:
        return "erro", "checagem travou (mais de %d min)" % (TIMEOUT_SEGUNDOS // 60)

    saida = (r.stdout or "") + (r.stderr or "")
    ultimas = "\n".join(saida.strip().splitlines()[-6:])
    # sys.exit(2) e a Azul se protegendo (quarentena), nao falha real - ver
    # SAIDA_NAO_E_FALHA em rodada.py
    if r.returncode not in (0, 2):
        return "erro", ultimas or "saiu com codigo %d, sem saida" % r.returncode
    return "concluida", ultimas or "checagem rodou sem saida"


def main():
    supabase_url = config.supabase_web_url
    service_key = config.supabase_web_service_key
    if not supabase_url or not service_key:
        print("SUPABASE_WEB_URL/SUPABASE_WEB_SERVICE_KEY nao configurados - nada a fazer.")
        return

    fila = pendentes(supabase_url, service_key)
    if not fila:
        print("fila vazia")
        return

    print("%d solicitacao(oes) pendente(s)" % len(fila))
    for s in fila:
        print("[%s] %s (%s)" % (s["id"], s["localizador"], s.get("cia") or "?"))
        status, resultado = atender_uma(s)
        marcar(supabase_url, service_key, s["id"], status, resultado)
        print("  %s: %s" % (status, resultado.splitlines()[-1] if resultado else ""))


if __name__ == "__main__":
    main()
