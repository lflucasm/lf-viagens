#!/usr/bin/env python3
"""Mede o teto por hora da flight-status da Volly ("Monitorar voo").

O monitor Volly (src/checar_volly_cloud.py) roda de hora em hora com
orcamento = LIMITE_VOLLY_HORA x 0,8 menos o que a organizacao ja consultou
na ultima hora. O LIMITE_VOLLY_HORA de la e provisorio (150, chute a partir
dos testes de 25/09/2026, quando o "Limite de consultas por hora atingido"
veio depois de ~180 consultas em ~25min). Este script mede o numero de
verdade: aperta o botao em sequencia num unico trecho futuro, com force,
ate a Volly recusar.

CUIDADO: o teto e da organizacao inteira - enquanto ele estiver batido, o
botao "Monitorar voo" da equipe tambem para. Rodar so fora do horario
comercial e com o aval do proprietário. Depois de medir, repetir apos 1h (janela
deslizante ou hora cheia?) e no fim do dia (existe teto diario?), e anotar o
resultado em LIMITE_VOLLY_HORA com a data.

So LE da Volly: consultar_status_voo e o mesmo botao de consulta da tela,
nao altera reminder nenhum.

Uso (na raiz do projeto, com o .env preenchido):
    python3 scripts/medir_limite_volly.py              # mede (ate 400 chamadas)
    python3 scripts/medir_limite_volly.py --so-contar  # so conta os lookups da
                                                       # ultima hora, sem chamar
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from config import Config  # noqa: E402
from milhasflow import MilhasFlow  # noqa: E402

SINAL_DE_LIMITE = "Limite de consultas"
PAUSA_S = 0.5
# teto de seguranca: se a Volly nao recusar ate aqui, para e avisa - nao da
# pra ficar batendo sem fim num recurso compartilhado com outras agencias
TETO_DE_CHAMADAS = 400


def lookups_ultima_hora(mf):
    desde = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    linhas = mf._buscar_tabela("flight_status_lookups", {
        "select": "created_at,cache_hit",
        "organization_id": "eq." + mf.cfg.organization_id,
        "created_at": "gte." + desde,
    })
    return sorted(linhas, key=lambda l: l.get("created_at") or "")


def imprimir_lookups(mf):
    linhas = lookups_ultima_hora(mf)
    cache = sum(1 for l in linhas if l.get("cache_hit"))
    print("Lookups da organizacao na ultima hora: %d  (cache_hit: %d, sem cache: %d)"
          % (len(linhas), cache, len(linhas) - cache))
    if linhas:
        print("  primeiro da janela: %s" % linhas[0]["created_at"])
        print("  ultimo da janela .: %s" % linhas[-1]["created_at"])
    return linhas


def reminder_futuro(mf):
    """Um trecho futuro com numero de voo - o mais proximo, que a
    AeroDataBox com certeza conhece (voo distante as vezes nem tem malha)."""
    agora = datetime.now(timezone.utc).isoformat()
    candidatos = [r for r in mf.buscar_voos(so_com_emissao=False)
                  if r.get("flight_number") and (r.get("departure_datetime") or "") > agora]
    candidatos.sort(key=lambda r: r["departure_datetime"])
    for r in candidatos:
        # confirma que a Volly acha esse voo antes de comecar a contar
        _, erro = mf.consultar_status_voo(r["id"], forcar=False)
        if not erro:
            return r, 1
        if SINAL_DE_LIMITE in erro:
            print("A Volly ja esta no limite agora (%s). Tente mais tarde." % erro)
            sys.exit(2)
        print("  %s %s nao serve (%s), tentando o proximo"
              % (r["flight_number"], r["departure_datetime"][:10], erro))
    print("Nenhum trecho futuro que a Volly encontre.")
    sys.exit(1)


def main():
    config = Config()
    mf = MilhasFlow(config)

    if "--so-contar" in sys.argv:
        imprimir_lookups(mf)
        return

    print("Antes de comecar:")
    imprimir_lookups(mf)

    reminder, chamadas = reminder_futuro(mf)
    print("\nTrecho escolhido: %s %s (%s-%s), reminder %s\n" % (
        reminder["flight_number"], reminder["departure_datetime"][:16],
        reminder.get("departure_airport"), reminder.get("arrival_airport"), reminder["id"]))

    inicio = datetime.now(timezone.utc)
    erro = None
    while chamadas < TETO_DE_CHAMADAS:
        _, erro = mf.consultar_status_voo(reminder["id"], forcar=True)
        chamadas += 1
        if erro and SINAL_DE_LIMITE in erro:
            break
        if erro:
            print("  chamada %d: erro sem ser limite (%s)" % (chamadas, erro))
        elif chamadas % 20 == 0:
            print("  %d chamadas ok..." % chamadas)
        time.sleep(PAUSA_S)
    fim = datetime.now(timezone.utc)

    print("\n" + "=" * 62)
    if erro and SINAL_DE_LIMITE in erro:
        print("  LIMITE atingido na chamada %d: %s" % (chamadas, erro))
        print("  chamadas que passaram ........ %d" % (chamadas - 1))
    else:
        print("  teto de seguranca de %d chamadas sem recusa da Volly" % TETO_DE_CHAMADAS)
    print("  duracao ...................... %.0fs (%s -> %s UTC)" % (
        (fim - inicio).total_seconds(), inicio.strftime("%H:%M:%S"), fim.strftime("%H:%M:%S")))
    print("=" * 62 + "\n")
    imprimir_lookups(mf)


if __name__ == "__main__":
    main()
