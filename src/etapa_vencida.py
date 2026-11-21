"""Diz se uma etapa ja passou do intervalo desde a ultima rodada (batimento).

Usado pelo ciclo de hora em hora (.github/workflows/ciclo.yml) pra rodar
etapas de cadencia mais lenta - a malha, 2x por dia - dentro do mesmo job,
sem depender da hora exata em que o GitHub resolve executar o cron (o
agendador pula e atrasa rodadas: em 1-15/10/2026 o supervisor "de hora em
hora" rodou 63 vezes, com buraco de ate 10,5h).

Imprime 1 (rodar) ou 0 (ainda nao). Na duvida - erro lendo o painel, etapa
sem batimento nenhum - imprime 1: melhor uma rodada a mais que uma a menos.

Uso:  python3 src/etapa_vencida.py malha 10
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import supabase_rest


def vencida(ultimo_inicio, horas, agora):
    """`ultimo_inicio` (ISO ou None) mais velho que `horas`?"""
    if not ultimo_inicio:
        return True
    visto = datetime.fromisoformat(ultimo_inicio.replace("Z", "+00:00"))
    return (agora - visto).total_seconds() >= horas * 3600


def main():
    etapa, horas = sys.argv[1], float(sys.argv[2])
    try:
        linhas = supabase_rest.select(
            os.environ["SUPABASE_WEB_URL"], os.environ["SUPABASE_WEB_SERVICE_KEY"],
            "batimentos", {"select": "inicio", "etapa": "eq." + etapa,
                           "order": "inicio.desc", "limit": "1"})
        ultimo = linhas[0]["inicio"] if linhas else None
    except Exception as erro:
        print("AVISO: nao li o batimento de %s (%s) - rodando" % (etapa, erro),
              file=sys.stderr)
        ultimo = None
    print("1" if vencida(ultimo, horas, datetime.now(timezone.utc)) else "0")


if __name__ == "__main__":
    main()
