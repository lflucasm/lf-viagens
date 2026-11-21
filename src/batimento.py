"""Batimento: uma linha por rodada de cada etapa na tabela `batimentos` do
painel. E o que o supervisor (supervisor.py) le para saber se cada etapa
rodou, quando e com que resultado - sem isso uma etapa parada so seria
notada quando alguem estranhasse a falta de alerta (foi o que aconteceu
com a rodada do Mac, parada de 15 a 26/09/2026 sem ninguem ver).

Nunca levanta: falha ao gravar batimento nao pode derrubar a etapa que
esta sendo registrada.

Uso:
    with batimento.rodada(url, key, "monitor-volly") as b:
        ...
        b.lidos = 104
        b.detalhe["chamadas"] = 8
"""

import sys
from contextlib import contextmanager

import supabase_rest
from nuvem_comum import agora_utc


def iniciar(supabase_url, service_key, etapa):
    """Grava o inicio da rodada. Devolve o id, ou None se nao gravou."""
    try:
        linha = supabase_rest.inserir(supabase_url, service_key, "batimentos", {
            "etapa": etapa, "inicio": agora_utc()})
        return linha["id"] if linha else None
    except Exception as erro:
        print("AVISO: batimento de %s nao iniciou (%s)" % (etapa, erro), file=sys.stderr)
        return None


def concluir(supabase_url, service_key, batimento_id, ok, lidos=0, alertas=0,
             falhas=0, detalhe=None):
    if batimento_id is None:
        return
    try:
        supabase_rest.atualizar(
            supabase_url, service_key, "batimentos", {"id": "eq.%s" % batimento_id},
            {"fim": agora_utc(), "ok": bool(ok), "lidos": lidos, "alertas": alertas,
             "falhas": falhas, "detalhe": detalhe or {}})
    except Exception as erro:
        print("AVISO: batimento %s nao concluiu (%s)" % (batimento_id, erro), file=sys.stderr)


class Rodada(object):
    """Contadores que a etapa preenche durante a rodada."""

    def __init__(self):
        self.lidos = 0
        self.alertas = 0
        self.falhas = 0
        self.detalhe = {}


@contextmanager
def rodada(supabase_url, service_key, etapa):
    """Registra inicio e fim. Excecao da etapa vira `ok = false` (com o erro
    no detalhe) e e relancada - quem trata a quebra continua sendo o
    wrapper `__main__` de cada script (nuvem_comum.avisar_quebra)."""
    batimento_id = iniciar(supabase_url, service_key, etapa)
    contadores = Rodada()
    try:
        yield contadores
    except BaseException as erro:
        if not isinstance(erro, SystemExit) or erro.code not in (0, None):
            contadores.detalhe["erro"] = str(erro)[:500]
            concluir(supabase_url, service_key, batimento_id, False, contadores.lidos,
                     contadores.alertas, contadores.falhas, contadores.detalhe)
        else:
            concluir(supabase_url, service_key, batimento_id, True, contadores.lidos,
                     contadores.alertas, contadores.falhas, contadores.detalhe)
        raise
    concluir(supabase_url, service_key, batimento_id, True, contadores.lidos,
             contadores.alertas, contadores.falhas, contadores.detalhe)
