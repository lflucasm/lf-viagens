"""Acesso HTTP direto ao PostgREST do Supabase (sem biblioteca cliente,
so urllib - mesma escolha do resto do projeto). Usado por quem precisa ler
ou escrever no banco do painel web sem passar pelo voos.db local, como
sincronizar_web.py (espelha o SQLite) e checar_malha_cloud.py (roda inteiro
fora do Mac, sem SQLite nenhum).
"""

import json
import urllib.error
import urllib.parse
import urllib.request

LOTE = 500


def select(supabase_url, service_key, tabela, params=None):
    """GET .../rest/v1/<tabela>?<params>. Devolve lista de dicts."""
    query = "?" + urllib.parse.urlencode(params) if params else ""
    req = urllib.request.Request(
        supabase_url.rstrip("/") + "/rest/v1/%s%s" % (tabela, query),
        headers={
            "apikey": service_key,
            "Authorization": "Bearer " + service_key,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def upsert(supabase_url, service_key, tabela, linhas, on_conflict):
    """POST em lotes de LOTE, merge por on_conflict (nomes de coluna, "a,b")."""
    if not linhas:
        return
    for i in range(0, len(linhas), LOTE):
        lote = linhas[i : i + LOTE]
        corpo = json.dumps(lote).encode("utf-8")
        req = urllib.request.Request(
            supabase_url.rstrip("/") + "/rest/v1/%s?on_conflict=%s" % (tabela, on_conflict),
            data=corpo,
            method="POST",
            headers={
                "apikey": service_key,
                "Authorization": "Bearer " + service_key,
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=60).read()


def atualizar(supabase_url, service_key, tabela, filtro, campos):
    """PATCH .../rest/v1/<tabela>?<filtro> - update de verdade, nao upsert.

    Necessario para tabelas com id GERADO (ex: historico.id e "generated
    always as identity"): um upsert por POST tenta inserir esse id de volta e
    o Postgres recusa, mesmo quando o conflito resolveria em UPDATE - o
    parser valida a clausula INSERT antes de saber que vai colidir.
    """
    query = "?" + urllib.parse.urlencode(filtro)
    corpo = json.dumps(campos).encode("utf-8")
    req = urllib.request.Request(
        supabase_url.rstrip("/") + "/rest/v1/%s%s" % (tabela, query),
        data=corpo,
        method="PATCH",
        headers={
            "apikey": service_key,
            "Authorization": "Bearer " + service_key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    urllib.request.urlopen(req, timeout=30).read()


def inserir(supabase_url, service_key, tabela, linha):
    """POST simples (sem upsert) - para tabelas append-only como historico.

    Devolve a linha gravada (com o id gerado), para quem precisa dele depois
    (ex: marcar notificado=true so apos confirmar o envio do alerta).
    """
    corpo = json.dumps(linha).encode("utf-8")
    req = urllib.request.Request(
        supabase_url.rstrip("/") + "/rest/v1/%s" % tabela,
        data=corpo,
        method="POST",
        headers={
            "apikey": service_key,
            "Authorization": "Bearer " + service_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        linhas = json.loads(r.read().decode())
    return linhas[0] if linhas else None
