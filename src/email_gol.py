"""Le o e-mail "Aviso GOL: seu voo foi alterado" (comunicacaovoegol@
acomodacao.voegol.com.br) que chega no hub hub@seudominio.com.br.

Existe porque o portal da GOL bloqueia o robo com reCAPTCHA (lidos=0 desde
23/10/2026) e o e-mail traz o que o portal mostraria: localizador, voo
antigo, voo novo e passageiros. Funcoes puras - quem busca o e-mail e quem
grava o alerta esta em checar_email_cias_cloud.py (via email_cias.py).

O corpo (texto puro) tem tabelas markdown:
    | Voo antigo |  ...  | Data | Voo | Origem |  | 04/11/26 | G3 1618 | ... (CGH) |
                          | Partida | Chegada | Destino |  | 17:50 | 21:05 | ... (REC) |
    | Voo novo |    ...  (mesmo formato)
    | Clientes |    | NOME |  (uma linha por passageiro)
"""

import re

import comparacao
import fusos

_LOCALIZADOR = re.compile(r"C[óo]digo de Reserva:\s*([A-Z0-9]{6})")
_DATA_VOO = re.compile(r"^\|\s*(\d\d)/(\d\d)/(\d\d)\s*\|\s*([A-Z0-9]{2}\s?\d{1,4})\s*\|\s*([^|]+?)\s*\|\s*$")
_HORAS = re.compile(r"^\|\s*(\d\d:\d\d)\s*\|\s*(\d\d:\d\d)\s*\|\s*([^|]+?)\s*\|\s*$")
_NOME = re.compile(r"^\|\s*([^|\d.,:!?]{3,70}?)\s*\|\s*$")
_AEROPORTO = re.compile(r"\((\w{3})\)")


def _iata(texto):
    m = _AEROPORTO.search(texto)
    return m.group(1) if m else None


def interpretar(corpo):
    """Texto do e-mail -> {"localizador", "antigos", "novos", "passageiros"},
    ou None se nao parece um aviso de alteracao com trechos (quem chama manda
    o e-mail inteiro pro Telegram em vez de calar)."""
    achou = _LOCALIZADOR.search(corpo or "")
    secao = None
    trechos = {"antigo": [], "novo": []}
    passageiros = []
    aberto = None
    for linha in (corpo or "").splitlines():
        linha = linha.strip()
        if "Voo antigo" in linha:
            secao, aberto = "antigo", None
        elif "Voo novo" in linha:
            secao, aberto = "novo", None
        elif re.search(r"\|\s*Clientes\s*\|", linha):
            secao, aberto = "clientes", None
        elif secao in trechos:
            m = _DATA_VOO.match(linha)
            if m:
                aberto = {"data": "20%s-%s-%s" % (m.group(3), m.group(2), m.group(1)),
                          "voo": m.group(4), "origem": _iata(m.group(5))}
                continue
            m = _HORAS.match(linha)
            if m and aberto:
                aberto.update(partida=m.group(1), chegada=m.group(2), destino=_iata(m.group(3)))
                trechos[secao].append(aberto)
                aberto = None
        elif secao == "clientes":
            m = _NOME.match(linha)
            if m:
                passageiros.append(m.group(1))
            elif passageiros and linha.strip("| "):
                secao = None   # primeira linha com texto que nao e nome (o paragrafo do botao)
    if not achou or not trechos["antigo"] or not trechos["novo"]:
        return None
    return {"localizador": achou.group(1), "antigos": trechos["antigo"],
            "novos": trechos["novo"], "passageiros": passageiros}


def _txt(t):
    return "%s %s/%s %s %s→%s %s" % (
        t["voo"], t["data"][8:], t["data"][5:7], t["origem"], t["partida"],
        t["destino"], t["chegada"])


def descrever(info):
    """Frase estavel (e o que o dedupe compara): so os trechos que mudaram."""
    antigos, novos = info["antigos"], info["novos"]
    pares = list(zip(antigos, novos)) if len(antigos) == len(novos) else [(None, None)]
    if pares == [(None, None)]:
        return "GOL avisou por e-mail: era %s; agora %s" % (
            " + ".join(_txt(t) for t in antigos), " + ".join(_txt(t) for t in novos))
    partes = ["%s virou %s" % (_txt(a), _txt(n)) for a, n in pares if a != n]
    return "GOL avisou por e-mail: " + "; ".join(partes or ["trechos iguais (confira o e-mail)"])


def escolher_voo(info, voos):
    """O voo do painel (da mesma reserva) ao qual o alerta se prende.

    Devolve (voo, no_painel): `no_painel` e False quando nenhum trecho antigo
    do e-mail esta no painel (ex.: TSTAMX, 21/10/2026 - so a ida estava la) e
    o alerta se prende ao primeiro voo da reserva.
    """
    do_loc = [v for v in voos if (v.get("localizador") or "").upper() == info["localizador"]]
    if not do_loc:
        return None, False
    for t in info["antigos"]:
        for v in do_loc:
            if (comparacao.numero_iata(v.get("numero_voo"), v.get("cia")) ==
                    comparacao.numero_iata(t["voo"], v.get("cia"))
                    and (v.get("embarque_local") or "")[:10] == t["data"]):
                return v, True
    return min(do_loc, key=lambda v: v.get("embarque_local") or ""), False


def com_embarque_local(voo):
    return dict(voo, embarque_local=fusos.texto_local(voo["embarque"], voo["origem"]))
