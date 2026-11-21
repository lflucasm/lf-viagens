"""Roda a agenda do dia que ficou pra tras, se o Mac esteve desligado.

O launchd recupera sozinho um StartCalendarInterval perdido quando o Mac
estava so dormindo, mas nao quando estava DESLIGADO de verdade - nesse caso
o horario passa e nada dispara, porque o proprio launchd nao estava rodando
para notar. Este script cobre esse caso: dispara no login/boot (RunAtLoad) e
de novo a cada 30 min, e so executa o que ja passou do horario e ainda nao
rodou hoje (ver src/agenda.py). Repetir em dia nao faz nada - e barato chamar
com frequencia.

Uso:  .venv/bin/python src/vigia.py
"""

import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agenda

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(RAIZ, ".venv/bin/python")

# Checagem consolidada numa rodada só por dia (decisão do proprietário, economiza
# consulta de API): rodada.py já chama a malha internamente, então não tem
# mais horário separado pra ela nem rodada da noite. Ver com.lfviagens.rodada-manha.
AGENDA_DO_DIA = (
    (agenda.RESUMO, 7, 0, [PYTHON, "src/rodada.py", "--resumo"]),
)


def main():
    agora = datetime.datetime.now()
    for chave, hora, minuto, comando in AGENDA_DO_DIA:
        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if agora < alvo:
            print("%-8s ainda nao chegou (previsto %02d:%02d)" % (chave, hora, minuto))
            continue
        if agenda.ja_rodou_hoje(chave):
            print("%-8s ja rodou hoje" % chave)
            continue
        print("%-8s atrasado (previsto %02d:%02d) - rodando agora" % (chave, hora, minuto))
        subprocess.run(comando, cwd=RAIZ)


if __name__ == "__main__":
    main()
