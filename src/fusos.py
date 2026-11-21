"""Conversao de horario: o MilhasFlow grava UTC, os portais mostram hora local.

Sem isso a comparacao com o site da companhia acusaria "horario alterado" em
todo voo - o Brasil esta 3h atras de UTC. Cada aeroporto usa o proprio fuso,
entao a conversao e por aeroporto, nao global.
"""

import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

IATA = re.compile(r"^[A-Z]{3}$")

# Aeroportos presentes na base da agencia. Ampliar conforme surgirem novos.
FUSOS = {
    # Brasil
    "BSB": "America/Sao_Paulo", "CGH": "America/Sao_Paulo",
    "CNF": "America/Sao_Paulo", "CWB": "America/Sao_Paulo",
    "GIG": "America/Sao_Paulo", "GRU": "America/Sao_Paulo",
    "MGF": "America/Sao_Paulo", "POA": "America/Sao_Paulo",
    "RAO": "America/Sao_Paulo", "SDU": "America/Sao_Paulo",
    "VCP": "America/Sao_Paulo",
    # faltavam em 26/09/2026 - sem eles o horario saia em UTC e o monitor
    # Volly acusava "venda 20:25 x companhia 17:25" em voo que nao mudou
    # (fusos confirmados pelo timeZone da AeroDataBox)
    "BHZ": "America/Sao_Paulo", "FLN": "America/Sao_Paulo",
    "IGU": "America/Sao_Paulo", "IZA": "America/Sao_Paulo",
    "SJP": "America/Sao_Paulo", "UDI": "America/Sao_Paulo",
    "DOU": "America/Campo_Grande",
    "AJU": "America/Maceio", "VDC": "America/Bahia",
    "FOR": "America/Fortaleza", "JPA": "America/Fortaleza",
    "NAT": "America/Fortaleza", "THE": "America/Fortaleza",
    "MCZ": "America/Maceio", "REC": "America/Recife",
    "SSA": "America/Bahia",
    # Exterior
    "ATL": "America/New_York", "PTY": "America/Panama",
    "BLL": "Europe/Copenhagen", "CDG": "Europe/Paris",
    "FCO": "Europe/Rome", "FLR": "Europe/Rome",
    "LHR": "Europe/London", "LIS": "Europe/Lisbon",
    "XPG": "Europe/Paris",          # Gare du Nord (trecho de trem)
    "QQS": "Europe/London",         # St Pancras (trecho de trem)
    "BKK": "Asia/Bangkok", "DOH": "Asia/Qatar",
    "AEP": "America/Argentina/Buenos_Aires", "BLQ": "Europe/Rome",
    "BOS": "America/New_York", "JFK": "America/New_York",
    "MAD": "Europe/Madrid",
    # sem snapshot na Volly pra aprender (27/09/2026)
    "DUS": "Europe/Berlin", "ROS": "America/Argentina/Cordoba",
}

# Segundo mapa, aprendido: fuso que a AeroDataBox informou (campo `timeZone`
# dos snapshots da Volly) para aeroporto fora de FUSOS, guardado na tabela
# `fusos_aeroporto` do painel pela ingestao (sincronizar_voos_cloud). Comeca
# vazio; script de nuvem que converte horario chama carregar_aprendidos() no
# inicio. Decisao de 26/09/2026: aeroporto novo nao pode esperar alguem
# editar este arquivo, e tambem nao pode cair em UTC calado.
FUSOS_APRENDIDOS = {}


def fuso_valido(nome):
    """O nome existe na base de fusos do Python? (evita gravar lixo da API)"""
    if not nome or ZoneInfo is None:
        return False
    try:
        ZoneInfo(nome)
        return True
    except Exception:
        return False


def carregar_aprendidos(supabase_url, service_key):
    """Le `fusos_aeroporto` do painel para FUSOS_APRENDIDOS.

    Devolve quantos aeroportos entraram. Nunca levanta: sem a tabela o
    sistema segue so com o mapa fixo (e o aeroporto desconhecido continua
    marcado como incompleto, nunca convertido como se fosse UTC).
    """
    import supabase_rest  # aqui dentro: fusos.py tambem roda no Mac, sem painel
    try:
        linhas = supabase_rest.select(supabase_url, service_key, "fusos_aeroporto",
                                      {"select": "iata,fuso"})
    except Exception as erro:
        print("AVISO: fusos aprendidos nao carregaram (%s)" % erro)
        return 0
    return aprender({l["iata"]: l["fuso"] for l in linhas})


def aprender(mapa):
    """Junta {iata: fuso} ao mapa aprendido (so fuso valido). Devolve quantos."""
    novos = 0
    for iata, fuso in (mapa or {}).items():
        codigo = (iata or "").strip().upper()
        if e_aeroporto(codigo) and fuso_valido(fuso):
            FUSOS_APRENDIDOS[codigo] = fuso
            novos += 1
    return novos


def fuso_de(codigo):
    """Fuso do aeroporto: mapa fixo primeiro, depois o aprendido. None se nenhum."""
    codigo = (codigo or "").strip().upper()
    return FUSOS.get(codigo) or FUSOS_APRENDIDOS.get(codigo)


def e_aeroporto(codigo):
    """Distingue aeroporto de rodoviaria: a base mistura os dois.

    'GRU' e aeroporto; 'Belo Horizonte (Rodoviaria)' e trecho terrestre e nao
    tem o que checar em site de companhia aerea.
    """
    return bool(codigo and IATA.match(codigo.strip()))


def tem_fuso(codigo):
    """Aeroporto com fuso conhecido (fixo ou aprendido)? Fora deles o horario
    sairia errado."""
    return fuso_de(codigo) is not None


def para_local(iso, codigo_aeroporto):
    """Converte o horario UTC do banco para a hora local do aeroporto.

    Devolve (datetime_local, fuso_conhecido: bool). Sem fuso mapeado, devolve
    o horario em UTC e sinaliza - melhor entregar o dado cru do que um errado.
    """
    if not iso:
        return None, True
    try:
        momento = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None, True

    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)

    fuso = fuso_de(codigo_aeroporto)
    if not fuso or ZoneInfo is None:
        return momento, False
    return momento.astimezone(ZoneInfo(fuso)), True


# A Volly grava o horario LOCAL do aeroporto como se fosse de Brasilia
# (sempre com offset -03:00 -> UTC), qualquer que seja o aeroporto.
# Confirmado em 27/09/2026 com 120 trechos contra a AeroDataBox: LIS, CDG,
# LHR, DOH e BLQ batem 100% nessa leitura. Nos aeroportos em -03:00 isso
# coincide com o UTC real, por isso passou despercebido; no exterior (e em
# Manaus/Cuiaba/Rio Branco/Noronha) a conversao por fuso errava 3-6h e gerava
# "horario da venda nao bate" falso.
OFFSET_VOLLY = timezone(timedelta(hours=-3))


def volly_para_utc(iso, codigo_aeroporto):
    """Horario como a Volly grava -> UTC de verdade (ISO).

    Le a parede do relogio em -03:00 e reinterpreta no fuso do aeroporto.
    Sem fuso conhecido devolve o valor original (o trecho ja vira
    `incompleto` na ingestao, nunca e comparado).
    """
    if not iso:
        return iso
    try:
        momento = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return iso
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    fuso = fuso_de(codigo_aeroporto)
    if not fuso or ZoneInfo is None:
        return iso
    parede = momento.astimezone(OFFSET_VOLLY).replace(tzinfo=None)
    return parede.replace(tzinfo=ZoneInfo(fuso)).astimezone(timezone.utc).isoformat()


def utc_para_volly(iso_utc, codigo_aeroporto):
    """Inverso de volly_para_utc: como a Volly gravaria esse instante (pra
    montar/comparar proposta de atualizacao no formato dela)."""
    if not iso_utc:
        return iso_utc
    fuso = fuso_de(codigo_aeroporto)
    if not fuso or ZoneInfo is None:
        return iso_utc
    momento = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    parede = momento.astimezone(ZoneInfo(fuso)).replace(tzinfo=None)
    return parede.replace(tzinfo=OFFSET_VOLLY).astimezone(timezone.utc).isoformat()


def texto_local(iso, codigo_aeroporto):
    """Horario local formatado para o CSV: 'AAAA-MM-DD HH:MM'."""
    momento, _ = para_local(iso, codigo_aeroporto)
    return momento.strftime("%Y-%m-%d %H:%M") if momento else ""


def horas_ate(iso):
    """Horas entre agora e o embarque, respeitando fuso (nao depende do mapa)."""
    if not iso:
        return None
    try:
        momento = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return (momento - datetime.now(timezone.utc)).total_seconds() / 3600.0
