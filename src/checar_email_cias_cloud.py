"""Avisos de voo das companhias por e-mail -> alerta (etapa `email-cias` do ciclo).

Os e-mails das cias chegam no hub (hub@seudominio.com.br), onde um Google Apps
Script (scripts/apps-script/email-gol.gs) os entrega por POST autenticado.
Comecou so com a GOL (portal bloqueado por reCAPTCHA); desde 07/11/2026 le
todas as cias: e mais uma fonte cruzando com Volly, portais e malha
(nuvem_comum.decidir_achado junta o mesmo fato visto por fontes diferentes).

Aqui: interpreta (email_cias.py), prende o alerta ao voo do painel
(localizador > numero de compra LATAM > numero do voo + data) e segue o fluxo
comum (dedupe, site, Telegram, supervisor). Origem do alerta = `email-<cia>`.

O script devolve os ultimos dias inteiros a cada rodada; nao precisa marcar
e-mail como lido porque gravar_achado nao repete (voo, tipo, detalhe).

Reserva que nao esta no painel, ou e-mail que nao deu pra interpretar, vai
direto pro Telegram (uma vez - dedupe em supervisor_estado `emailgol:<id>`,
prefixo mantido da versao so-GOL pra nao repetir aviso antigo): nada de cia
pode morrer calado.

Env: EMAIL_GOL_URL (URL /exec do Apps Script) e EMAIL_GOL_TOKEN - nomes da
versao so-GOL, mantidos pra nao recriar secret.
Uso: python3 src/checar_email_cias_cloud.py [--dias N]   (padrao 7)
"""

import html
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import batimento
import email_cias
import email_gol
import nuvem_comum
import supabase_rest

ETAPA = "email-cias"


def origem_da_cia(cia):
    return "email-" + cia.lower().replace(" ", "")


def buscar_emails(url, token, dias):
    """POST {token, dias} -> lista de {id, data, de, assunto, corpo}. O Apps
    Script responde com 302 pro conteudo; o urllib segue sozinho."""
    pedido = urllib.request.Request(
        url, data=json.dumps({"token": token, "dias": dias}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        resposta = json.loads(r.read().decode())
    if not resposta.get("ok"):
        raise RuntimeError("Apps Script recusou: %s" % resposta.get("erro"))
    return resposta["emails"]


def voos_ativos(supabase_url, service_key):
    linhas = supabase_rest.select(supabase_url, service_key, "voos", {
        "select": "id,localizador,cia,numero_voo,origem,destino,embarque,passageiros",
        "ativo": "eq.true", "embarque": "gte." + (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()})
    return [email_gol.com_embarque_local(v) for v in linhas]


def _ja_avisado(estado, chave):
    return any(e["chave"] == chave for e in estado)


def avisar_solto(supabase_url, service_key, token, chat, estado, email, texto):
    """Telegram direto, uma vez por e-mail. True se enviou agora."""
    chave = "emailgol:%s" % email["id"]
    if _ja_avisado(estado, chave):
        return False
    ok, erro = alertas.enviar_telegram(token, chat, texto)
    if not ok:
        print("       Telegram falhou: %s" % erro)
        return False
    supabase_rest.upsert(supabase_url, service_key, "supervisor_estado", [{
        "chave": chave, "aberto_em": nuvem_comum.agora_utc(),
        "avisado_em": nuvem_comum.agora_utc(), "detalhe": {"assunto": email["assunto"]}}],
        "chave")
    return True


def texto_solto(email, info):
    """Mensagem do Telegram pra aviso que nao virou alerta de voo do painel.
    O Telegram vai em parse_mode HTML: texto do e-mail (ex.: "<https://...>")
    precisa ser escapado, senao a API recusa com 400."""
    e = html.escape
    cia = email_cias.cia_do_remetente(email.get("de")) or "Companhia"
    if info is None:
        return "⚠️ E-mail da %s que não consegui interpretar — confira no hub:\n%s\n%s" % (
            cia, e(email["assunto"] or ""), e((email.get("corpo") or "")[:600]))
    ref = info.get("localizador") or info.get("compra") or "?"
    quem = ", ".join(info.get("passageiros") or []) or info.get("nome") or "?"
    return "⚠️ Aviso da %s para reserva fora do painel: %s\n%s\nPassageiros: %s" % (
        cia, e(ref), e(email_cias.descrever(info, email["assunto"])), e(quem))


def rodar(b, dias):
    url, token = os.environ["EMAIL_GOL_URL"], os.environ["EMAIL_GOL_TOKEN"]
    supabase_url = os.environ["SUPABASE_WEB_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_WEB_SERVICE_KEY"]
    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    emails = buscar_emails(url, token, dias)
    print("E-mails das cias nos ultimos %d dias ... %d" % (dias, len(emails)))
    voos = voos_ativos(supabase_url, service_key)
    estado = supabase_rest.select(supabase_url, service_key, "supervisor_estado",
                                  {"select": "chave", "chave": "like.emailgol:*"})
    do_pdf = nuvem_comum.links_pdf_do_supabase(supabase_url, service_key)
    por_compra = email_cias.localizador_por_compra(do_pdf)

    por_origem, soltos, sem_leitura, por_cia = {}, 0, 0, {}
    for e in emails:
        info = email_cias.interpretar(e)
        cia = email_cias.cia_do_remetente(e.get("de")) or "?"
        por_cia[cia] = por_cia.get(cia, 0) + 1
        alvos = email_cias.escolher_voos(info, voos, por_compra) if info else []
        if not alvos:
            sem_leitura += info is None
            soltos += avisar_solto(supabase_url, service_key, tg_token, tg_chat, estado, e,
                                   texto_solto(e, info))
            continue
        descricao = email_cias.descrever(info, e["assunto"])
        for voo in alvos:
            por_origem.setdefault(origem_da_cia(info["cia"]), []).append(
                {"tipo": info["tipo"], "voo_crm": voo, "detalhe": descricao})

    novos = 0
    for origem, achados in por_origem.items():
        itens = [i for i in (nuvem_comum.gravar_achado(supabase_url, service_key, a, origem, do_pdf)
                             for a in achados) if i]
        enviado, motivo = nuvem_comum.enviar_alertas(
            supabase_url, service_key, tg_token, tg_chat, itens, origem,
            "Aviso da companhia por e-mail", do_pdf)
        print("%s: alertas novos %d, Telegram: %s" % (
            origem, len(itens), enviado if enviado is not None else motivo))
        novos += len(itens)
    print("avisos soltos %d (sem leitura %d)" % (soltos, sem_leitura))
    b.lidos = len(emails)
    b.alertas = novos + soltos
    b.detalhe.update({"emails": len(emails), "por_cia": por_cia, "sem_leitura": sem_leitura})


def main():
    if not os.environ.get("EMAIL_GOL_URL") or not os.environ.get("EMAIL_GOL_TOKEN"):
        # ainda nao instalado: sai calado (so o supervisor lembra, uma vez)
        print("EMAIL_GOL_URL / EMAIL_GOL_TOKEN nao configurados - nada a fazer")
        return
    dias = int(sys.argv[sys.argv.index("--dias") + 1]) if "--dias" in sys.argv else 7
    supabase_url = os.environ["SUPABASE_WEB_URL"].rstrip("/")
    with batimento.rodada(supabase_url, os.environ["SUPABASE_WEB_SERVICE_KEY"], ETAPA) as b:
        rodar(b, dias)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("O leitor de e-mails das companhias", erro)
        sys.exit(1)
