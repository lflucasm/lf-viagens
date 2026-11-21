"""Avisos de voo de TODAS as companhias que chegam no hub (hub@seudominio.com.br).

Cada e-mail vira {"cia", "tipo", "localizador", "compra", "nome", "antigos",
"novos"} - funcoes puras; quem busca e grava esta em checar_email_cias_cloud.py.

- GOL: parser proprio (email_gol.py, tabelas com localizador).
- LATAM (info@info.latam.com): blocos "Novo horário / Horario anterior /
  Voo cancelado / Novo voo LA1234" + data por extenso + horas. Nao traz o
  localizador, so o "Número de compra" (orderId) e o primeiro nome.
- Demais (Azul, TAP, Copa, Qatar...): ate 07/11/2026 nenhum aviso de voo
  delas chegou no hub, entao nao ha modelo real - leitura generica de
  localizador, numero de voo e data. O que nao der pra ligar a um voo do
  painel vai pro Telegram inteiro (nada passa calado).
"""

import re
import unicodedata

import comparacao
import email_gol

# (nome no painel, pedacos do dominio do remetente)
CIAS = [
    ("GOL", ("voegol.com.br",)),
    ("LATAM", ("latam.com", "lan.com")),
    ("AZUL", ("voeazul.com.br", "voeazul-news.com.br")),
    ("TAP", ("flytap.com", "tapforbiz.com")),
    ("COPA", ("copaair.com",)),
    ("QATAR", ("qatarairways.com",)),
    ("IBERIA", ("iberia.com",)),
    ("AMERICAN", ("aa.com", "americanairlines.com")),
    ("UNITED", ("united.com",)),
    ("DELTA", ("delta.com",)),
    ("AVIANCA", ("avianca.com",)),
    ("AEROLINEAS", ("aerolineas.com.ar",)),
    ("EMIRATES", ("emirates.com",)),
    ("AIR FRANCE", ("airfrance.",)),
    ("KLM", ("klm.com",)),
]
MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
         "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}

_VOO = r"([A-Z0-9]{2}\s?\d{2,4})"
_BLOCO_LATAM = re.compile(r"(Novo hor[áa]rio|Hor[áa]rio anterior|Voo cancelado|Novo voo|Voo anterior)\s+" + _VOO)
_FIM_LATAM = re.compile(r"Sobre a sua bagagem|Prefere outra op")
_DATA_EXTENSO = re.compile(r"(\d{1,2}) de ([a-zç]+) de (\d{4})", re.I)
_HORA = re.compile(r"\b(\d\d:\d\d)\b")
_COMPRA = re.compile(r"N[úu]mero de compra\s+(LA\w{8,})")
_NOME = re.compile(r"Ol[áa],?\s+([A-ZÀ-Ú][A-ZÀ-Ú ]{1,60}?)\s*,")
_LOCALIZADOR = re.compile(
    r"(?:c[óo]digo (?:da|de) reserva|localizador|reserva|booking (?:reference|code)|"
    r"record locator|pnr|c[óo]digo de confirma[çc][ãa]o)\s*[:#nº°.]*\s*([A-Z0-9]{6})\b", re.I)
_VOO_SOLTO = re.compile(r"\b(AD|G3|LA|JJ|TP|CM|QR|IB|AA|UA|DL|AV|AR|EK|AF|KL)\s?(\d{2,4})\b")
_DATA_BARRA = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def cia_do_remetente(de):
    de = (de or "").lower()
    for nome, dominios in CIAS:
        if any(d in de for d in dominios):
            return nome
    return None


def tipo_do_aviso(assunto, corpo=""):
    """Tipo do alerta (nuvem_comum.GRUPO_ALERTA) pelo assunto; corpo so desempata."""
    a = _sem_acento((assunto or "").lower())
    if "pagamento pendente" in a:
        return "pagamento_pendente"
    if "cancelad" in a or "cancelled" in a or "canceled" in a:
        return "cancelamento"
    if re.search(r"\bvoo cancelado\b", _sem_acento((corpo or "").lower())) and "novo voo" not in a:
        return "cancelamento"
    return "alteracao_voo"


def _trecho_latam(voo, texto):
    texto = re.sub(r"Informa[çc][ãa]o atualizada em [\d/]+ \d\d:\d\d", " ", texto)
    datas = _DATA_EXTENSO.findall(texto)
    horas = _HORA.findall(texto)
    if not datas or not horas:
        return None
    d, mes, ano = datas[0]
    mes = MESES.get(_sem_acento(mes.lower()))
    if not mes:
        return None
    return {"voo": voo.replace(" ", ""), "data": "%s-%02d-%02d" % (ano, mes, int(d)),
            "partida": horas[0], "chegada": horas[1] if len(horas) > 1 else None}


def ler_latam(corpo):
    """Corpo (texto puro do Gmail ou como a tela mostra - tanto faz, a quebra de
    linha nao importa) -> antigos/novos/compra/nome. None se nao achou trecho."""
    plano = " ".join((corpo or "").split())
    fim = _FIM_LATAM.search(plano)
    plano_util = plano[:fim.start()] if fim else plano
    blocos = list(_BLOCO_LATAM.finditer(plano_util))
    antigos, novos = [], []
    for i, b in enumerate(blocos):
        ate = blocos[i + 1].start() if i + 1 < len(blocos) else len(plano_util)
        trecho = _trecho_latam(b.group(2), plano_util[b.end():ate])
        if trecho is None:
            continue
        rotulo = _sem_acento(b.group(1).lower())
        (novos if rotulo.startswith("novo") else antigos).append(trecho)
    if not antigos and not novos:
        return None
    compra, nome = _COMPRA.search(plano), _NOME.search(plano)
    return {"compra": compra.group(1) if compra else None,
            "nome": nome.group(1).strip() if nome else None,
            "localizador": None, "antigos": antigos, "novos": novos, "passageiros": []}


def ler_generico(corpo):
    """Qualquer cia sem modelo: localizador + voos citados (com a 1a data do texto)."""
    plano = " ".join((corpo or "").split())
    loc = _LOCALIZADOR.search(plano)
    data = _DATA_BARRA.search(plano)
    iso = None
    if data:
        ano = data.group(3) if len(data.group(3)) == 4 else "20" + data.group(3)
        iso = "%s-%s-%s" % (ano, data.group(2), data.group(1))
    voos = []
    for m in _VOO_SOLTO.finditer(plano):
        v = m.group(1) + m.group(2)
        if v not in [t["voo"] for t in voos]:
            voos.append({"voo": v, "data": iso, "partida": None, "chegada": None})
    if not loc and not voos:
        return None
    return {"compra": None, "nome": None, "localizador": loc.group(1).upper() if loc else None,
            "antigos": voos, "novos": [], "passageiros": []}


def interpretar(email):
    """{"de", "assunto", "corpo"} -> info do aviso, ou None (vai pro Telegram inteiro)."""
    cia = cia_do_remetente(email.get("de"))
    if cia is None:
        return None
    corpo = email.get("corpo") or ""
    if cia == "GOL":
        info = email_gol.interpretar(corpo)
        if info:
            info = dict(info, compra=None, nome=None)
    elif cia == "LATAM":
        info = ler_latam(corpo)
    else:
        info = ler_generico(corpo)
    if info is None:
        return None
    return dict(info, cia=cia, tipo=tipo_do_aviso(email.get("assunto"), corpo))


def _txt(t):
    horas = "%s→%s" % (t["partida"], t["chegada"]) if t.get("chegada") else (t.get("partida") or "")
    data = "%s/%s" % (t["data"][8:], t["data"][5:7]) if t.get("data") else ""
    return " ".join(p for p in (t["voo"], data, horas) if p)


def descrever(info, assunto=""):
    """Frase estavel (o dedupe compara o texto): o que mudou, sem enfeite."""
    if info["cia"] == "GOL" and info.get("localizador") and info["novos"]:
        return email_gol.descrever(info)
    cab = "%s avisou por e-mail: " % info["cia"]
    antigos, novos = info["antigos"], info["novos"]
    if info["tipo"] == "cancelamento" and antigos and not novos:
        return cab + "voo cancelado " + " + ".join(_txt(t) for t in antigos)
    if antigos and novos and len(antigos) == len(novos):
        partes = ["%s virou %s" % (_txt(a), _txt(n)) for a, n in zip(antigos, novos) if a != n]
        return cab + "; ".join(partes or ["trechos iguais (confira o e-mail)"])
    if novos and not antigos:
        return cab + "novo voo " + " + ".join(_txt(t) for t in novos)
    voos = " + ".join(_txt(t) for t in antigos + novos)
    return cab + (assunto or "aviso") + (" (%s)" % voos if voos else "")


def _mesmo_voo(v, t):
    return (comparacao.numero_iata(v.get("numero_voo"), v.get("cia")) ==
            comparacao.numero_iata(t["voo"], v.get("cia"))
            and (not t.get("data") or (v.get("embarque_local") or "")[:10] == t["data"]))


def _com_nome(voos, nome):
    if not nome:
        return voos
    primeiro = _sem_acento(nome.split()[0].upper())
    filtrados = [v for v in voos if primeiro in _sem_acento(str(v.get("passageiros") or "").upper())]
    return filtrados or voos


def escolher_voos(info, voos, loc_da_compra=None):
    """Voos do painel aos quais o alerta se prende.

    Ordem: localizador do e-mail > localizador do numero de compra LATAM
    (links_pdf) > mesmo numero de voo e data (a cia mexe no voo, entao vale
    pra todo cliente nele; o primeiro nome do e-mail so estreita). Devolve
    lista vazia quando nada casa.
    """
    loc = info.get("localizador") or (loc_da_compra or {}).get(info.get("compra") or "")
    if loc:
        do_loc = [v for v in voos if (v.get("localizador") or "").upper() == loc]
        if do_loc:
            if info["cia"] == "GOL":
                voo, _ = email_gol.escolher_voo(dict(info, localizador=loc), do_loc)
                return [voo]
            casados = [v for v in do_loc if any(_mesmo_voo(v, t) for t in info["antigos"])]
            return casados or [min(do_loc, key=lambda v: v.get("embarque_local") or "")]
    casados = [v for v in voos if (v.get("cia") or "").upper().startswith(info["cia"][:3])
               and any(_mesmo_voo(v, t) for t in info["antigos"] if t.get("data"))]
    return _com_nome(casados, info.get("nome"))


_ORDER_ID = re.compile(r"orderId=([A-Za-z0-9]+)")


def localizador_por_compra(links_pdf):
    """{localizador: url} (tabela links_pdf) -> {numero de compra: localizador}."""
    saida = {}
    for loc, url in (links_pdf or {}).items():
        m = _ORDER_ID.search(url or "")
        if m:
            saida[m.group(1).upper()] = loc
    return saida
