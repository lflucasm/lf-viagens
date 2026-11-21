"""Leitura da pagina "Minhas Viagens" da LATAM e comparacao com o CRM.

O acesso e pelo deep link do PDF (?orderId=...&lastname=...), que entra direto
sem formulario. A busca manual da LATAM e barrada por deteccao de bot; o deep
link nao e.

Esta camada e pura: recebe o TEXTO da pagina e devolve dados. Quem busca a
pagina e o navegador.py - assim da para testar o parser sem abrir browser.
"""

import re
import unicodedata

# funcoes genericas vivem em comparacao.py: GOL usa as mesmas
from comparacao import (_normaliza_voo, comparar, identificar,  # noqa: F401
                        observacoes_da_leitura, tem_trecho_futuro)

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

RE_COMPRA = re.compile(r"N[uú]mero de compra:\s*([A-Z0-9]{8,20})", re.I)
RE_DATA = re.compile(
    r"(?:segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)[-\w]*,\s*"
    r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.I)
RE_HORA = re.compile(r"^(\d{1,2}):(\d{2})$")
RE_AEROPORTO = re.compile(r"\(([A-Z]{3})\)\s*$")
RE_VOO = re.compile(r"^([A-Z]{2})\s?(\d{2,4})$")

# Sinais de que a reserva nao existe mais ou nao foi encontrada
RE_NAO_ENCONTRADA = re.compile(
    r"n[aã]o (?:foi )?(?:encontr|localiz)|"
    r"nenhuma reserva|reserva inexistente|"
    r"verifique os dados|dados incorretos", re.I)
RE_CANCELADA = re.compile(r"\bcancelad[ao]\b", re.I)


# Endpoint que a propria pagina consome. Ler daqui em vez da tela elimina a
# dependencia do acordeao (a LATAM entrega os trechos recolhidos, e a expansao
# nao e confiavel) e ainda entrega o status IATA de cada trecho.
API_PEDIDO = "/bff/mytrips/v1/order/id/"

# Codigos de status de trecho (IATA)
STATUS_OK = {"HK", "KK", "RR"}                    # confirmado
STATUS_ALTERADO = {"TK", "WK", "SC", "WL"}        # a companhia mexeu no voo
STATUS_CANCELADO = {"UN", "HX", "UC", "NO", "WN"}  # trecho caiu


def ler_api(resposta):
    """Le a resposta JSON de /bff/mytrips/v1/order/id/...

    Devolve o mesmo formato de ler_pagina(), porem sempre completo: a API traz
    todos os trechos, entao segmentos_nao_expandidos e sempre 0.
    """
    vazio = {"encontrada": False, "numero_compra": None, "cancelada": False,
             "segmentos": [], "segmentos_nao_expandidos": 0, "status_pedido": None}
    if not isinstance(resposta, dict):
        return vazio

    pedido = (resposta.get("data") or {}).get("order") or {}
    if not pedido:
        return vazio

    viagem = pedido.get("travel") or {}
    itens = viagem.get("items") or []

    segmentos = []
    for item in itens:
        for seg in item.get("segments") or []:
            chave = seg.get("key") or {}
            voo = seg.get("flight") or {}
            numero = voo.get("flightNumber")
            cia = voo.get("airlineCode") or ""
            partida = chave.get("departureDate") or ""
            chegada = chave.get("arrivalDate") or ""
            status = (seg.get("status") or "").upper()

            segmentos.append({
                "data": partida[:10],
                "origem": chave.get("origin"),
                "destino": chave.get("destination"),
                "numero_voo": "%s%s" % (cia, numero) if numero else None,
                "partida": partida[11:16],
                "chegada": chegada[11:16],
                "status": status,
                "operado_por": voo.get("operatingAirlineCode"),
                "classe": seg.get("cabinClass"),
                "contingencia": bool(seg.get("inContingency")),
                "incidente": seg.get("incidentType"),
                "partida_estimada": seg.get("estimatedDepartureTime"),
            })

    return {
        "encontrada": True,
        "numero_compra": pedido.get("id") or pedido.get("orderId"),
        "status_pedido": pedido.get("status"),
        "reembolsado": pedido.get("refunded"),
        "no_show": bool(pedido.get("isNoShow")),
        "atualizado_em": pedido.get("updateDateTime"),
        "cancelada": (pedido.get("status") or "").upper() in ("CANCELLED", "CANCELED"),
        "segmentos": segmentos,
        "segmentos_nao_expandidos": 0,
    }


def achados_de_status(leitura, voos_por_chave):
    """Alertas que vem do proprio status do trecho, sem comparar com o CRM."""
    achados = []
    for seg in leitura.get("segmentos", []):
        chave = (_normaliza_voo(seg.get("numero_voo")), seg.get("data"))
        crm = voos_por_chave.get(chave)
        status = seg.get("status") or ""

        if status in STATUS_CANCELADO:
            achados.append({"tipo": "trecho_cancelado", "voo_crm": crm,
                            "detalhe": "%s em %s com status %s" % (
                                seg.get("numero_voo"), seg.get("data"), status)})
        elif status in STATUS_ALTERADO:
            achados.append({"tipo": "alterado_pela_companhia", "voo_crm": crm,
                            "detalhe": "%s status %s" % (seg.get("numero_voo"), status)})
        elif status and status not in STATUS_OK:
            achados.append({"tipo": "status_desconhecido", "voo_crm": crm,
                            "detalhe": "%s status %s" % (seg.get("numero_voo"), status)})

        if seg.get("contingencia") or seg.get("incidente"):
            achados.append({"tipo": "em_contingencia", "voo_crm": crm,
                            "detalhe": "%s: %s" % (seg.get("numero_voo"),
                                                   seg.get("incidente") or "contingencia")})
    return achados


def _sem_acento(texto):
    normal = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normal if unicodedata.category(c) != "Mn")


def _data(dia, mes_texto, ano):
    mes = MESES.get(_sem_acento(mes_texto).lower())
    return "%04d-%02d-%02d" % (int(ano), mes, int(dia)) if mes else None


def ler_pagina(texto):
    """Extrai a reserva do texto da pagina.

    Devolve dict com: encontrada, numero_compra, cancelada, segmentos[].
    Cada segmento: data, origem, destino, numero_voo, partida, chegada.
    """
    resultado = {
        "encontrada": False,
        "numero_compra": None,
        "cancelada": False,
        "segmentos": [],
        "segmentos_nao_expandidos": 0,
    }
    if not texto:
        return resultado

    compra = RE_COMPRA.search(texto)
    if compra:
        resultado["numero_compra"] = compra.group(1).upper()
        resultado["encontrada"] = True
    elif RE_NAO_ENCONTRADA.search(texto):
        return resultado

    resultado["cancelada"] = bool(RE_CANCELADA.search(texto))

    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    data_atual = None
    bloco = None

    for linha in linhas:
        cabecalho = RE_DATA.search(linha)
        if cabecalho:
            if bloco and bloco.get("numero_voo"):
                resultado["segmentos"].append(bloco)
            elif bloco:
                resultado["segmentos_nao_expandidos"] += 1
            data_atual = _data(*cabecalho.groups())
            bloco = {"data": data_atual, "origem": None, "destino": None,
                     "numero_voo": None, "partida": None, "chegada": None}
            continue

        if bloco is None:
            continue

        hora = RE_HORA.match(linha)
        if hora:
            marca = "%02d:%02d" % (int(hora.group(1)), int(hora.group(2)))
            if bloco["partida"] is None:
                bloco["partida"] = marca
            else:
                bloco["chegada"] = marca
            continue

        aeroporto = RE_AEROPORTO.search(linha)
        if aeroporto:
            codigo = aeroporto.group(1)
            if bloco["origem"] is None:
                bloco["origem"] = codigo
            elif bloco["destino"] is None:
                bloco["destino"] = codigo
            continue

        voo = RE_VOO.match(linha)
        if voo and bloco["numero_voo"] is None:
            bloco["numero_voo"] = voo.group(1) + voo.group(2)

    if bloco and bloco.get("numero_voo"):
        resultado["segmentos"].append(bloco)
    elif bloco:
        resultado["segmentos_nao_expandidos"] += 1

    return resultado


