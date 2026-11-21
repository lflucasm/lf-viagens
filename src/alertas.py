"""Envio de alertas pelo Telegram - unico canal do sistema.

Regra de ouro: nunca alertar duas vezes a mesma coisa. O historico tem a coluna
`notificado` e so vira mensagem o que ainda nao foi avisado - sistema que
repete alerta e sistema que a equipe aprende a ignorar.
"""

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

import qualidade

TELEGRAM = "https://api.telegram.org/bot%s/sendMessage"

ICONE = {
    "cancelamento": "🔴", "reserva_perdida": "🔴", "trecho_cancelado": "🔴",
    "alteracao_voo": "🟠", "alterado_pela_companhia": "🟠", "pagamento_pendente": "🟠",
    "horario_alterado": "🟠", "data_alterada": "🟠", "rota_alterada": "🟠",
    "em_contingencia": "🟠", "atraso": "🟡", "reembolso": "🟡",
    "ausente_na_companhia": "🔴", "status_desconhecido": "🟡",
    # amarelo de proposito: nao e mudanca confirmada, e "as fontes discordam,
    # confira". Tratar como laranja daria a uma duvida o mesmo peso de um voo
    # que a companhia realmente mexeu.
    "fontes_divergem": "🟡",
    # a venda (CRM) diz um horario/data e a companhia outro - ou a agencia
    # digitou errado, ou a cia mexeu antes da primeira leitura. Laranja: nos
    # dois casos alguem precisa conferir e avisar o passageiro.
    "horario_venda_diverge": "🟠",
    # a Volly nao acha o voo no trecho vendido (status SemVooNoTrecho): a cia
    # mexeu no voo ou a venda esta errada - alguem precisa conferir.
    "sem_voo_no_trecho": "🟠",
    # o numero vendido hoje voa outra rota: o passageiro quase certamente
    # foi tirado desse voo (TSTABX, 23/10/2026)
    "passageiro_remanejado": "🔴",
}

# Titulo de cada tipo no Telegram (mesmo texto de web/lib/tipos.ts
# ROTULO_TIPO). Tipo fora daqui sai com o codigo, como antes.
ROTULO = {
    "passageiro_remanejado": "Passageiro remanejado?",
    "horario_venda_diverge": "Horário da companhia diferente da venda",
    "horario_alterado": "Horário alterado",
    "data_alterada": "Data do voo mudou",
    "rota_alterada": "Rota alterada",
    "sem_voo_no_trecho": "Voo não encontrado no trecho",
    "alterado_pela_companhia": "Alterado pela companhia",
    "trecho_cancelado": "Trecho cancelado",
    "cancelamento": "Cancelamento",
    "ausente_na_companhia": "Trecho não aparece na companhia",
    "atraso": "Atraso",
    "alteracao_voo": "Voo alterado",
    "pagamento_pendente": "Pagamento pendente",
}

_REMANEJADO = re.compile(r"vendido (\w{3})-(\w{3})(?: (\d{2}:\d{2}))? -> "
                         r"companhia (\w{3})-(\w{3})(?: (\d{2}:\d{2}))?")
_HORARIOS = re.compile(r"(?:na venda (?:\d{4}-\d{2}-\d{2} )?|visto antes )(\d{2}:\d{2})"
                       r" -> (?:na companhia |agora )(\d{2}:\d{2})")
_DATAS = re.compile(r"CRM (\d{4})-(\d{2})-(\d{2}) -> companhia (\d{4})-(\d{2})-(\d{2})")
# abaixo disso e ajuste fino da malha ou arredondamento de quem digitou
MINUTOS_MUDANCA_GRANDE = 30


def _minutos(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def diferenca_horario(antes, depois):
    """'1h30 mais tarde' / '25 min mais cedo' - virada da meia-noite conta
    pelo caminho mais curto (23:50 -> 00:10 = 20 min mais tarde)."""
    delta = (_minutos(depois) - _minutos(antes) + 720) % 1440 - 720
    if delta == 0:
        return "mesmo horário"
    h, m = divmod(abs(delta), 60)
    tamanho = ("%dh%02d" % (h, m) if m else "%dh" % h) if h else "%d min" % m
    return "%s %s" % (tamanho, "mais tarde" if delta > 0 else "mais cedo")


def explicar(tipo, detalhe, cia=None):
    """(titulo, o que provavelmente aconteceu) - texto curto pra quem le o
    alerta ter o panorama antes de abrir a reserva (pedido do proprietário,
    23/10/2026). Mesma regra de web/lib/tipos.ts:explicarAlerta."""
    titulo = ROTULO.get(tipo, (tipo or "").replace("_", " "))
    a_cia = "a %s" % cia if cia else "a companhia"
    A_cia = a_cia[0].upper() + a_cia[1:]
    da_cia = "da %s" % cia if cia else "da companhia"
    detalhe = detalhe or ""

    if tipo == "passageiro_remanejado":
        m = _REMANEJADO.search(detalhe)
        if not m:
            return titulo, ("Esse voo agora faz outra rota: o passageiro deve ter sido "
                            "remanejado. Confira a reserva no site da cia.")
        de, para, _, de_cia, para_cia, _ = m.groups()
        if de != de_cia:
            return titulo, ("%s tirou esse voo de %s (agora sai de %s). Provável que o "
                            "passageiro tenha sido remanejado para outro voo: confira "
                            "a reserva no site da cia." % (A_cia, de, de_cia))
        return titulo, ("O voo agora termina em %s, não em %s. Pode ser escala nova ou "
                        "remanejamento: confira a reserva no site da cia." % (para_cia, para))

    if tipo in ("horario_venda_diverge", "horario_alterado"):
        m = _HORARIOS.search(detalhe)
        if not m:
            return titulo, None
        antes, depois = m.groups()
        titulo = "Horário mudou: %s → %s (%s)" % (antes, depois, diferenca_horario(antes, depois))
        grande = abs((_minutos(depois) - _minutos(antes) + 720) % 1440 - 720) >= MINUTOS_MUDANCA_GRANDE
        if tipo == "horario_alterado":
            return titulo, ("%s mudou o horário desde a última conferência. Avise o "
                            "passageiro." % A_cia)
        if grande:
            return titulo, ("Provável: %s mudou o horário depois da venda (ou a venda "
                            "foi digitada errada). Confirme e avise o passageiro." % a_cia)
        return titulo, ("Provável: ajuste pequeno %s na malha ou arredondamento na "
                        "venda." % da_cia)

    if tipo == "data_alterada":
        m = _DATAS.search(detalhe)
        if m:
            titulo = "Data mudou: %s/%s → %s/%s" % (m.group(3), m.group(2), m.group(6), m.group(5))
        return titulo, ("Provável: %s passou o voo para outro dia (ou a venda está com "
                        "a data errada)." % a_cia)

    if tipo == "sem_voo_no_trecho":
        return titulo, ("O voo não aparece mais nesse trecho: pode ter sido cancelado ou "
                        "trocado de número. Confira a reserva.")
    if tipo == "rota_alterada":
        return titulo, ("%s mudou a rota desde a última conferência; o passageiro pode "
                        "ter sido remanejado." % A_cia)
    return titulo, None


def link_painel(painel_web_url, voo_id):
    """URL da reserva no nosso painel, ou None sem PAINEL_WEB_URL/voo_id."""
    if not painel_web_url or not voo_id:
        return None
    return "%s/reserva/%s" % (painel_web_url, voo_id)


def enviar_telegram(token, chat_id, texto):
    """Devolve (ok, erro). Nao levanta: alerta que falha nao pode parar a rodada."""
    if not token or not chat_id:
        return False, "Telegram nao configurado"
    corpo = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": texto[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(TELEGRAM % token, data=corpo)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode()).get("ok", False), None
    except urllib.error.HTTPError as e:
        return False, "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:180])
    except Exception as e:
        return False, str(e)[:180]


def formatar_alerta(item):
    """Bloco de alerta pronto para o Telegram - com link da reserva, se houver.

    Passageiro e links so aparecem quando quem montou o item (rodada.py /
    checar_malha_cloud.py) tem como monta-los: para cia sem conector (TAP,
    Copa...) ou sem PAINEL_WEB_URL configurado, fica so o texto, igual antes.
    """
    icone = ICONE.get(item.get("tipo"), "⚪")
    cia = " (%s)" % item["cia"] if item.get("cia") else ""
    titulo, hipotese = explicar(item.get("tipo"), item.get("detalhe"), item.get("cia"))
    linhas = [
        "%s <b>%s</b>%s — %s" % (icone, item.get("localizador") or "?", cia, html.escape(titulo)),
        "   %s" % (item.get("detalhe") or "").replace(" -> ", " → "),
    ]
    if hipotese:
        linhas.append("   💡 %s" % html.escape(hipotese))
    nomes = qualidade.nomes_passageiros(item.get("passageiros")) or item.get("passageiro")
    if nomes:
        linhas.append("   👤 %s" % html.escape(nomes))
    if item.get("link"):
        linhas.append('   🔗 <a href="%s">abrir reserva na companhia</a>'
                      % html.escape(item["link"], quote=True))
    if item.get("link_painel"):
        linhas.append('   🖥️ <a href="%s">ver no nosso painel</a>'
                      % html.escape(item["link_painel"], quote=True))
    return "\n".join(linhas)


def montar_mensagem(alertas, titulo="Checagem de voos"):
    if not alertas:
        return None
    por_gravidade = sorted(alertas, key=lambda a: 0 if ICONE.get(a.get("tipo")) == "🔴" else 1)
    linhas = ["<b>%s</b>" % titulo, ""]
    linhas += [formatar_alerta(a) for a in por_gravidade[:25]]
    if len(alertas) > 25:
        linhas.append("\n… e mais %d." % (len(alertas) - 25))
    return "\n".join(linhas)
