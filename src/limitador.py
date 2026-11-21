"""Controle de ritmo das consultas aos sites das companhias.

Existe porque em 29/07/2026 a Azul limitou o IP da agencia: varios acessos
automatizados seguidos ao site deles, feitos por scripts avulsos que nao
passavam pelo espacamento do navegador.

Por isso o estado fica em ARQUIVO, nao em memoria: assim o limite vale entre
processos diferentes. Dois scripts rodando ao mesmo tempo, ou um script rodado
logo depois do outro, continuam respeitando o mesmo intervalo.
"""

import json
import os
import random
import time
import urllib.parse

ARQUIVO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".ritmo.json")

# intervalo minimo entre duas consultas ao MESMO dominio, em segundos
INTERVALO = {
    "latamairlines.com": (8, 18),
    "voeazul.com.br": (25, 45),      # foi quem bloqueou: folga maior
    "voegol.com.br": (12, 25),
    "smiles.com.br": (12, 25),
}
PADRAO = (10, 20)

# teto de consultas por dominio numa mesma hora
TETO_POR_HORA = {"voeazul.com.br": 40}
TETO_PADRAO = 120


class LimiteExcedido(Exception):
    pass


def dominio(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    for conhecido in INTERVALO:
        if host.endswith(conhecido):
            return conhecido
    return host


def _ler():
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def _gravar(estado):
    try:
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(estado, f)
    except IOError:
        pass


def aguardar(url):
    """Segura a execucao ate ser seguro consultar de novo esse dominio.

    Levanta LimiteExcedido se o teto por hora ja foi atingido - nesse caso o
    certo e parar a rodada, nao esperar: insistir e o que vira bloqueio longo.
    """
    dom = dominio(url)
    agora = time.time()
    estado = _ler()
    registro = estado.get(dom, {"ultima": 0, "marcas": []})

    marcas = [t for t in registro.get("marcas", []) if agora - t < 3600]
    if len(marcas) >= TETO_POR_HORA.get(dom, TETO_PADRAO):
        raise LimiteExcedido(
            "%s: teto de %d consultas/hora atingido. Pare e volte mais tarde."
            % (dom, TETO_POR_HORA.get(dom, TETO_PADRAO)))

    minimo = random.uniform(*INTERVALO.get(dom, PADRAO))
    passou = agora - registro.get("ultima", 0)
    if registro.get("ultima") and passou < minimo:
        time.sleep(minimo - passou)

    agora = time.time()
    marcas.append(agora)
    estado[dom] = {"ultima": agora, "marcas": marcas}
    _gravar(estado)


def registrar_bloqueio(url, minutos=120):
    """Marca o dominio como bloqueado; consultas ficam barradas por um tempo."""
    estado = _ler()
    dom = dominio(url)
    estado.setdefault(dom, {})["bloqueado_ate"] = time.time() + minutos * 60
    _gravar(estado)


def esta_bloqueado(url):
    registro = _ler().get(dominio(url), {})
    ate = registro.get("bloqueado_ate", 0)
    return ate > time.time(), max(0, int((ate - time.time()) / 60))
