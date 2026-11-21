"""Quarentena de dominio pra checadores de nuvem (GitHub Actions).

limitador.py (Mac) guarda estado em arquivo local - funciona porque o Mac
e a mesma maquina toda hora. Runner de nuvem e descartavel: cada execucao
comeca do zero, entao arquivo local nao lembra bloqueio de ontem. Aqui o
estado mora no Supabase (tabela limitador_estado), unico jeito de um
bloqueio de uma rodada valer pra proxima.

Existe por causa da Azul: ja limitou o IP da agencia uma vez (29/07/2026).
Rodar de nuvem sem isso arriscaria martelar o dominio sem trava nenhuma.
"""

import random
import time
import urllib.parse

import supabase_rest

INTERVALO = {
    "voeazul.com.br": (25, 45),
    "voegol.com.br": (12, 25),
}
PADRAO = (10, 20)
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


def _linha(supabase_url, service_key, dom):
    linhas = supabase_rest.select(
        supabase_url, service_key, "limitador_estado",
        {"select": "*", "dominio": "eq.%s" % dom})
    return linhas[0] if linhas else None


def aguardar(supabase_url, service_key, url):
    """Mesma logica de limitador.aguardar, com estado no Supabase."""
    dom = dominio(url)
    agora = time.time()
    linha = _linha(supabase_url, service_key, dom) or {}

    marcas = [t for t in (linha.get("marcas") or []) if agora - t < 3600]
    if len(marcas) >= TETO_POR_HORA.get(dom, TETO_PADRAO):
        raise LimiteExcedido(
            "%s: teto de %d consultas/hora atingido. Pare e volte mais tarde."
            % (dom, TETO_POR_HORA.get(dom, TETO_PADRAO)))

    minimo = random.uniform(*INTERVALO.get(dom, PADRAO))
    ultima = linha.get("ultima_epoch") or 0
    passou = agora - ultima
    if ultima and passou < minimo:
        time.sleep(minimo - passou)

    agora = time.time()
    marcas.append(agora)
    supabase_rest.upsert(
        supabase_url, service_key, "limitador_estado",
        [{"dominio": dom, "ultima_epoch": agora, "marcas": marcas}], "dominio")


def registrar_bloqueio(supabase_url, service_key, url, minutos=120):
    dom = dominio(url)
    ate = time.time() + minutos * 60
    supabase_rest.upsert(
        supabase_url, service_key, "limitador_estado",
        [{"dominio": dom, "bloqueado_ate_epoch": ate}], "dominio")


def esta_bloqueado(supabase_url, service_key, url):
    linha = _linha(supabase_url, service_key, dominio(url)) or {}
    ate = linha.get("bloqueado_ate_epoch") or 0
    return ate > time.time(), max(0, int((ate - time.time()) / 60))
