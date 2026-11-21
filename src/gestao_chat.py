"""KPIs do VollyChat - calculo puro em Python sobre o que volly_chat.py
devolve. Mesmo espirito de gestao.py: sem rede, sem estado.

Substitui os `chat_*` do MCP pago mais uteis pro dia a dia: quem esta
esperando resposta agora, tempo medio de 1a resposta, violacao de SLA,
volume por dia, protocolo parado.
"""

import datetime as _dt
from collections import defaultdict


def _dt_parse(s):
    if not s:
        return None
    s = str(s).replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def _contato(conversa):
    c = conversa.get("contacts") or {}
    return c.get("custom_name") or c.get("name") or c.get("phone") or "—"


# --- quem esta esperando agora --------------------------------------

def nao_respondidas(conversas, minutos=30, agora=None):
    """`conversas` = volly_chat.conversas(so_abertas=True) - usa so a
    ULTIMA mensagem embutida: se ela e 'in' (cliente falou), ninguem
    respondeu ainda."""
    agora = agora or _dt.datetime.now(_dt.timezone.utc)
    out = []
    for c in conversas:
        msgs = c.get("messages") or []
        if not msgs or msgs[0].get("direction") != "in":
            continue
        quando = _dt_parse(msgs[0].get("created_at"))
        if not quando:
            continue
        espera = (agora - quando).total_seconds()
        if espera >= minutos * 60:
            out.append({
                "conversation_id": c["id"],
                "contato": _contato(c),
                "telefone": (c.get("contacts") or {}).get("phone"),
                "responsavel": c.get("assigned_to"),
                "esperando_segundos": int(espera),
                "esperando_desde": quando.isoformat(),
            })
    return sorted(out, key=lambda x: -x["esperando_segundos"])


# --- volume ----------------------------------------------------------

def volume_por_dia(mensagens, fuso_horas=-3):
    """`mensagens` = volly_chat.mensagens_das_conversas(...) ou
    mensagens_recentes(...)[1]. Agrupa por dia local (default America/
    Sao_Paulo, UTC-3 - nao muda com horario de verao no Brasil desde 2019)."""
    b = defaultdict(lambda: {"entrada": 0, "saida": 0})
    for m in mensagens:
        d = _dt_parse(m.get("created_at"))
        if not d:
            continue
        dia = (d + _dt.timedelta(hours=fuso_horas)).date().isoformat()
        chave = "entrada" if m.get("direction") == "in" else "saida"
        b[dia][chave] += 1
    return dict(sorted(b.items()))


# --- tempo de resposta / SLA ------------------------------------------

def tempo_resposta(mensagens, limite_sla_minutos=30):
    """Pareia a 1a mensagem 'in' de cada sequencia com a proxima 'out' -
    isso e o tempo de resposta. Uma sequencia de varias 'in' seguidas conta
    so a primeira (o cliente mandando 3 mensagens seguidas nao e 3 esperas)."""
    por_conversa = defaultdict(list)
    for m in mensagens:
        por_conversa[m["conversation_id"]].append(m)

    esperas = []
    violacoes = []
    for cid, msgs in por_conversa.items():
        msgs = sorted(msgs, key=lambda m: m["created_at"])
        aguardando_desde = None
        for m in msgs:
            direcao = m.get("direction")
            if direcao == "in":
                if aguardando_desde is None:
                    aguardando_desde = _dt_parse(m["created_at"])
            elif direcao == "out" and aguardando_desde:
                resposta_em = _dt_parse(m["created_at"])
                if resposta_em:
                    seg = (resposta_em - aguardando_desde).total_seconds()
                    esperas.append(seg)
                    if seg > limite_sla_minutos * 60:
                        violacoes.append({
                            "conversation_id": cid,
                            "espera_segundos": int(seg),
                            "respondido_em": resposta_em.isoformat(),
                        })
                aguardando_desde = None

    media = sum(esperas) / len(esperas) if esperas else 0.0
    return {
        "qtd_respostas": len(esperas),
        "media_segundos": media,
        "violacoes_sla": sorted(violacoes, key=lambda x: -x["espera_segundos"]),
    }


# --- protocolos --------------------------------------------------------

def protocolos_abertos(protocolos, dias_min=3, hoje=None):
    hoje = hoje or _dt.datetime.now(_dt.timezone.utc)
    out = []
    for p in protocolos:
        if (p.get("status") or "").lower() == "closed":
            continue
        aberto = _dt_parse(p.get("opened_at"))
        if not aberto:
            continue
        dias = (hoje - aberto).days
        if dias >= dias_min:
            out.append({
                "numero": p.get("number"), "assunto": p.get("subject"),
                "aberto_em": aberto.isoformat(), "dias_aberto": dias,
            })
    return sorted(out, key=lambda x: -x["dias_aberto"])
