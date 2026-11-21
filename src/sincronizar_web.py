"""Espelha voos/historico/observacoes do banco local (voos.db) pro banco do
painel web (Supabase). Chamado automaticamente no fim de rodada.py e
checar_malha.py - tambem da pra rodar isolado (ver
scripts/sincronizar_supabase.py).

O bot continua sendo o UNICO lugar que fala com a malha e os portais e
gasta cota - este modulo so copia o resultado, depois que a checagem ja
aconteceu. Idempotente (chave = origem_local_id no historico, voo_id+origem
em observacoes) e nunca toca `resolvido`/`atendente_id`, que sao decisao do
operador no site, nao do bot.

Falha de sincronizacao NUNCA aborta a rodada - o monitoramento em si nao
depende do site. `sincronizar()` so devolve (ok, mensagem), nunca levanta.
"""

import urllib.error
from datetime import datetime

import painel
import qualidade
import supabase_rest


def com_fuso_brasil(iso_naive):
    """datetime.now().isoformat() do bot e hora local do Mac (America/Sao_Paulo,
    sem DST desde 2019), sem fuso anotado. Sem isso o Postgres (timestamptz)
    interpretaria como UTC e o horario apareceria 3h adiantado no site.
    """
    if not iso_naive:
        return iso_naive
    if iso_naive.endswith("Z") or "+" in iso_naive[10:]:
        return iso_naive
    return iso_naive + "-03:00"


def ler_voos(con):
    colunas = [
        "id", "emissao_id", "localizador", "cia", "numero_voo", "origem", "destino",
        "embarque", "chegada", "classe", "sentido", "status", "cliente", "passageiros",
        "tags", "balcao", "valor_venda", "ativo", "visto_em", "criado_em",
    ]
    linhas = []
    for row in con.execute("SELECT %s FROM voos" % ",".join(colunas)):
        d = dict(zip(colunas, row))
        d["ativo"] = bool(d["ativo"])
        d["balcao"] = int(d["balcao"] or 0)
        d["visto_em"] = com_fuso_brasil(d["visto_em"])
        d["criado_em"] = com_fuso_brasil(d["criado_em"])
        linhas.append(d)
    return linhas


def ler_historico(con):
    colunas = [
        "id", "voo_id", "evento", "campo", "valor_antigo", "valor_novo", "origem",
        "detectado_em", "notificado",
    ]
    linhas = []
    for row in con.execute("SELECT %s FROM historico" % ",".join(colunas)):
        d = dict(zip(colunas, row))
        d["origem_local_id"] = d.pop("id")
        d["notificado"] = bool(d["notificado"])
        d["detectado_em"] = com_fuso_brasil(d["detectado_em"])
        linhas.append(d)
    return linhas


def ler_observacoes(con):
    colunas = ["voo_id", "origem", "partida", "rota", "situacao", "visto_em"]
    linhas = []
    for row in con.execute("SELECT %s FROM observacoes" % ",".join(colunas)):
        d = dict(zip(colunas, row))
        d["visto_em"] = com_fuso_brasil(d["visto_em"])
        linhas.append(d)
    return linhas


def links_pdf_para_sincronizar(voos):
    """Uma linha por localizador ATIVO com o link de consulta ja pronto: PDF
    (LATAM so quando o numero de compra ja foi descoberto - ver
    painel.vinculos_latam; GOL/Azul quando o PDF tem) e senao o montado so com
    o CRM (sempre disponivel para GOL/Azul).

    Alimenta a tabela `links_pdf` do Supabase. E dali que o site e a checagem
    de malha na nuvem (checar_malha_cloud.py, que roda no GitHub Actions sem
    acesso a pasta de PDFs do Mac) pegam o MESMO link que ja vai no alerta
    local do Telegram - sem duplicar a logica de montagem em TypeScript.

    `voos`: lista de dicts no formato de ler_voos() (precisa de localizador,
    cia, origem, embarque, passageiros, ativo).
    """
    do_pdf = painel.links_dos_pdfs()
    por_localizador = {}
    for v in voos:
        if not v.get("ativo"):
            continue
        loc = (v.get("localizador") or "").upper()
        if not loc:
            continue
        atual = por_localizador.get(loc)
        # primeiro trecho AINDA NAO VOADO - mesma regra de painel.carregar()
        if atual is None or (v.get("embarque") or "") < (atual.get("embarque") or ""):
            por_localizador[loc] = v

    agora = com_fuso_brasil(datetime.now().isoformat(timespec="seconds"))
    linhas = []
    for loc, v in por_localizador.items():
        sobrenome = qualidade.sobrenome(v.get("passageiros"))
        voo = {"cia": v.get("cia"), "localizador": loc, "origem": v.get("origem"),
              "numero_voo": v.get("numero_voo"), "sobrenome": sobrenome,
              "sobrenome_completo": qualidade.sobrenome_completo(v.get("passageiros"))}
        url, _origem_link = painel.link_para(voo, do_pdf)
        if not url:
            continue
        linhas.append({
            "localizador": loc, "companhia": v.get("cia"), "origem": v.get("origem"),
            "sobrenome": sobrenome, "url": url, "util": True, "atualizado_em": agora,
        })
    return linhas


def sincronizar(con, supabase_url, service_key):
    """Le do banco local (SQLite ja conectado) e espelha pro Supabase.

    Devolve (ok: bool, mensagem: str). Nunca levanta - quem chama decide o
    que fazer com uma falha, mas ela nunca pode derrubar a rodada.
    """
    try:
        voos = ler_voos(con)
        historico = ler_historico(con)
        observacoes = ler_observacoes(con)
        links_pdf = links_pdf_para_sincronizar(voos)

        # ordem importa: historico/observacoes referenciam voos (FK)
        supabase_rest.upsert(supabase_url, service_key, "voos", voos, "id")
        supabase_rest.upsert(supabase_url, service_key, "historico", historico, "origem_local_id")
        supabase_rest.upsert(supabase_url, service_key, "observacoes", observacoes, "voo_id,origem")
        if links_pdf:
            supabase_rest.upsert(supabase_url, service_key, "links_pdf", links_pdf, "localizador")

        return True, "%d voos, %d historico, %d observacoes, %d links de consulta" % (
            len(voos), len(historico), len(observacoes), len(links_pdf))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
    except Exception as e:
        return False, str(e)


def sincronizar_se_configurado(con, config):
    """Chama sincronizar() so se SUPABASE_WEB_URL/SUPABASE_WEB_SERVICE_KEY
    estiverem preenchidos no .env - sem eles, sincronizacao fica desligada
    em silencio (nao e erro: nem todo ambiente tem o site configurado).
    """
    if not (config.supabase_web_url and config.supabase_web_service_key):
        return None
    return sincronizar(con, config.supabase_web_url, config.supabase_web_service_key)
