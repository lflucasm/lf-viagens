"""Estado de qual rodada diaria ja aconteceu hoje.

Existe para o vigia (src/vigia.py) saber o que ficou pra tras quando o Mac
esteve desligado no horario agendado - o launchd nao recupera isso sozinho
como recupera quando o Mac so estava dormindo.
"""

import datetime
import fcntl
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = os.path.join(RAIZ, ".agenda.json")

# As chaves moram aqui, e nao soltas como texto em rodada.py/checar_malha.py/
# vigia.py: quem marca e quem cobra tem de falar a MESMA palavra, e um erro de
# digitacao numa string espalhada por 4 arquivos nao levanta erro nenhum - so
# faz o vigia achar que a tarefa nunca rodou, todo dia.
RESUMO = "resumo"
MALHA = "malha"
RECAP = "recap"


def _hoje():
    return datetime.date.today().isoformat()


def _ler():
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def ja_rodou_hoje(chave):
    return _ler().get(chave) == _hoje()


def marcar(chave):
    estado = _ler()
    estado[chave] = _hoje()
    try:
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(estado, f)
    except IOError:
        pass


# Segura o descritor vivo pelo resto do processo: e o descritor aberto que
# mantem o flock, entao ele nao pode ser coletado.
_travas = {}


def travar(nome):
    """Trava exclusiva para esta tarefa. Devolve False se ja tem uma em pe.

    O vigia dispara a cada 30 min e a rodada da manha demora mais que isso: sem
    trava, o vigia sobe uma segunda rodada por cima da que o launchd comecou as
    7h - porque a agenda so e marcada NO FIM, e ate la a tarefa parece "nao
    rodou hoje". Dois Chromes consultando os mesmos portais dobram a chance de
    bloqueio, e os dois processos leem `notificado = 0` antes de qualquer um
    marcar, mandando o mesmo alerta duas vezes.

    Uma trava por nome, e nao uma so: a malha usa API e a rodada usa navegador,
    entao elas podem correr juntas como sempre correram.

    Nao apagamos o arquivo no fim - quem solta a trava e o fim do processo,
    quando o SO fecha o descritor. Isso vale inclusive se ele morrer no meio.
    """
    arquivo = open(os.path.join(RAIZ, ".trava-%s" % nome), "w")
    try:
        fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        arquivo.close()
        return False
    _travas[nome] = arquivo
    return True
