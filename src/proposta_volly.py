"""Proposta de atualizacao do cadastro na Volly - logica PURA (sem rede).

Depois que a equipe marca um alerta como "Verificado - passageiro avisado",
a reconferencia (reconferir_cloud.py) le a companhia de novo e este modulo
compara o trecho cadastrado na Volly (`reminders`) com o que a companhia diz
agora, e diz o que MUDARIA na Volly. Nao escreve nada: o botao "Aplicar na
Volly" e fase seguinte, so depois que o proprietário validar as propostas (spec do
fluxo na nuvem, parte 4, 26/09/2026).

Tudo e comparado em UTC DE VERDADE. A Volly grava a hora local de qualquer
aeroporto com offset -03:00 (achado de 27/09/2026, ver fusos.volly_para_utc),
entao o reminder passa por volly_para_utc antes de comparar, e o valor
"para" da proposta volta pro formato dela com fusos.utc_para_volly - e o
que a Volly gravaria se alguem digitasse o horario novo na tela.

A leitura da companhia chega aqui ja normalizada (formato `leitura` abaixo),
venha de onde vier - AeroDataBox (monitor Volly / malha) ou portal da cia:

    {"numero_voo": "LA3588", "origem": "GRU", "destino": "DOU",
     "partida_utc": "2026-10-28T12:25:00+00:00",   # None = nao se sabe
     "chegada_utc": "2026-10-28T14:10:00+00:00",   # None = nao se sabe
     "cancelado": False,
     "reacomodado_para": None | <outra leitura>,   # voo novo, se houver
     "motivo_sem_proposta": None | "texto"}        # sem_proposta explicado
"""

import re
from datetime import datetime, timedelta, timezone

import fusos

# Diferenca minima de horario pra propor mudanca - a mesma dos alertas de
# "venda x companhia" (checar_volly_cloud.MINUTOS_DIVERGENCIA_VENDA): abaixo
# disso e arredondamento de quem digitou a venda.
MINUTOS_TOLERANCIA = 5

# Status da AeroDataBox que contam como cancelado. "CanceledUncertain" entra
# de proposito: na duvida, a proposta manda conferir no portal em vez de
# comparar horario de um voo que talvez nem saia.
STATUS_CANCELADO_ADB = {"Canceled", "CanceledUncertain"}

# Status de trecho que o portal marca como cancelado (IATA, mesmos de
# latam.STATUS_CANCELADO) - GOL/Azul trazem o status da reserva inteira, que
# cai no teste por "cancel" no texto.
STATUS_CANCELADO_PORTAL = {"UN", "HX", "UC", "NO", "WN"}

# Quantos dias de distancia um voo novo do portal pode estar da data vendida
# pra ser considerado a reacomodacao (mesma rota, outro numero).
DIAS_REACOMODACAO = 3

MSG_IGUAL = "✅ Volly já está igual à companhia."
MSG_CANCELADO = ("⚠️ Sem proposta: voo cancelado e sem voo novo visível. "
                 "Conferir no portal da cia.")
MSG_SEM_LEITURA = ("⚠️ Sem proposta: nenhuma fonte conseguiu ler o voo agora. "
                   "Conferir no portal da cia.")

RE_INSTANTE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?$")


# ------------------------------------------------------------------ tempo

def instante_utc(texto):
    """Texto de horario com fuso -> datetime UTC, ou None.

    Aceita o ISO da Volly ("2026-10-28T12:00:00+00:00") e o da AeroDataBox
    ("2026-09-27 03:05Z"). Sem fuso explicito devolve None: horario sem
    fuso aqui seria chute, e chute vira proposta errada.
    """
    if not texto:
        return None
    achado = RE_INSTANTE.match(str(texto).strip())
    if not achado:
        return None
    data, hora, minuto, segundo, fuso = achado.groups()
    if not fuso:
        return None
    if fuso == "Z":
        deslocamento = timedelta(0)
    else:
        sinal = -1 if fuso[0] == "-" else 1
        digitos = fuso[1:].replace(":", "")
        deslocamento = sinal * timedelta(hours=int(digitos[:2]), minutes=int(digitos[2:]))
    momento = datetime.strptime("%s %s:%s:%s" % (data, hora, minuto, segundo or "00"),
                                "%Y-%m-%d %H:%M:%S")
    return (momento - deslocamento).replace(tzinfo=timezone.utc)


def _iso(momento):
    return momento.astimezone(timezone.utc).isoformat() if momento else None


def local_para_utc(data, hhmm, aeroporto):
    """("2026-10-28", "09:25", "GRU") -> ISO UTC, ou None sem fuso conhecido.

    Portal e observacao da malha falam hora LOCAL do aeroporto; sem o fuso
    nao da pra comparar (nunca assumir UTC - regra de 26/09/2026).
    """
    fuso = fusos.fuso_de(aeroporto)
    if not (data and hhmm and fuso and fusos.ZoneInfo):
        return None
    try:
        parede = datetime.strptime("%s %s" % (data, hhmm[:5]), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return _iso(parede.replace(tzinfo=fusos.ZoneInfo(fuso)))


def _texto_local(iso_utc, aeroporto):
    """"dd/mm HH:MM" na hora local do aeroporto (o que a equipe le)."""
    momento, _ = fusos.para_local(iso_utc, aeroporto)
    return momento.strftime("%d/%m %H:%M") if momento else "?"


# ------------------------------------------------------------ adaptadores

def _normaliza_numero(numero):
    return re.sub(r"[^A-Z0-9]", "", (numero or "").upper())


def de_contrato_aerodatabox(contrato):
    """Um FlightContract da AeroDataBox (snapshot da Volly ou malha) -> leitura.

    Usa o `scheduledTime`, nao o `revisedTime`: a Volly guarda a GRADE do
    voo, e o revisado e estimativa operacional do dia (atraso), que muda de
    hora em hora - propor gravar atraso na Volly seria errado e reagendaria
    lembrete de cliente a toa.
    """
    if not isinstance(contrato, dict):
        return None
    partida = contrato.get("departure") or {}
    chegada = contrato.get("arrival") or {}

    def iata(movimento):
        return (((movimento.get("airport") or {}).get("iata")) or "").strip().upper() or None

    def utc(movimento):
        return _iso(instante_utc(((movimento.get("scheduledTime") or {}).get("utc"))))

    return {
        "numero_voo": _normaliza_numero(contrato.get("number")) or None,
        "origem": iata(partida),
        "destino": iata(chegada),
        "partida_utc": utc(partida),
        "chegada_utc": utc(chegada),
        "cancelado": contrato.get("status") in STATUS_CANCELADO_ADB,
        "reacomodado_para": None,
    }


def _cancelado_no_portal(status):
    status = (status or "").upper()
    return status in STATUS_CANCELADO_PORTAL or "CANCEL" in status


def de_segmento_portal(seg):
    """Um segmento de latam.ler_api / gol.ler_pagina / azul.ler_api -> leitura.

    Os tres portais entregam data + hora LOCAL (partida e chegada, sem a data
    da chegada). Chegada "antes" da partida e voo que vira a noite: chegada no
    dia seguinte (nenhum trecho unico da carteira passa de 24h).
    """
    if not isinstance(seg, dict):
        return None
    origem = (seg.get("origem") or "").upper() or None
    destino = (seg.get("destino") or "").upper() or None
    data = seg.get("data")
    partida_utc = local_para_utc(data, seg.get("partida"), origem)
    chegada_utc = None
    if data and seg.get("chegada"):
        data_chegada = data
        if seg.get("partida") and seg["chegada"][:5] < seg["partida"][:5]:
            data_chegada = (datetime.strptime(data, "%Y-%m-%d")
                            + timedelta(days=1)).strftime("%Y-%m-%d")
        chegada_utc = local_para_utc(data_chegada, seg["chegada"], destino)
    return {
        "numero_voo": _normaliza_numero(seg.get("numero_voo")) or None,
        "origem": origem,
        "destino": destino,
        "partida_utc": partida_utc,
        "chegada_utc": chegada_utc,
        "cancelado": _cancelado_no_portal(seg.get("status")),
        "reacomodado_para": None,
    }


def de_observacao(obs, numero_voo, origem, destino):
    """Ultima `observacoes` de uma fonte (ex.: malha-cloud) -> leitura.

    A observacao so guarda partida local ("AAAA-MM-DD HH:MM"), rota e
    situacao - chegada fica None e nao entra na comparacao. Rota ausente
    (a malha nem sempre grava) vale como a do reminder.
    """
    if not isinstance(obs, dict) or not obs.get("partida"):
        return None
    rota = (obs.get("rota") or "").upper()
    if "-" in rota:
        origem, destino = rota.split("-", 1)
    partida = obs["partida"]
    return {
        "numero_voo": _normaliza_numero(numero_voo) or None,
        "origem": origem,
        "destino": destino,
        "partida_utc": local_para_utc(partida[:10], partida[11:16], origem),
        "chegada_utc": None,
        "cancelado": (obs.get("situacao") or "") in STATUS_CANCELADO_ADB
                     or _cancelado_no_portal(obs.get("situacao")),
        "reacomodado_para": None,
    }


def de_leitura_portal(leitura, numero_voo, data_local, origem, destino):
    """Reserva lida no portal -> leitura do trecho vendido, ou None.

    - reserva cancelada: cancelado, sem voo novo;
    - GOL em "reacomodacao-de-voo" (sem itinerario visivel): sem proposta,
      com o motivo;
    - o numero vendido aparece: esse trecho (o do dia vendido, ou o mais
      perto dele - data mudada vira proposta);
    - o numero vendido sumiu (ou esta cancelado) mas ha outro voo na MESMA
      rota ate DIAS_REACOMODACAO dias do vendido: reacomodacao pra ele;
    - nada disso: None (o portal nao mostra este trecho - quem responde e a
      proxima fonte, Volly ou malha).

    Conexao nova (GRU-CGB-DOU no lugar de GRU-DOU) nao casa rota e cai em
    None de proposito: montar proposta de dois trechos a partir de um e
    trabalho pra fase de escrita, nao pra adivinhar aqui.
    """
    if not isinstance(leitura, dict):
        return None
    if leitura.get("reacomodada") and not leitura.get("segmentos"):
        return {"numero_voo": _normaliza_numero(numero_voo), "origem": origem,
                "destino": destino, "partida_utc": None, "chegada_utc": None,
                "cancelado": True, "reacomodado_para": None,
                "motivo_sem_proposta": "a companhia reacomodou a reserva e o voo "
                                       "novo não está visível"}
    if leitura.get("cancelada"):
        return {"numero_voo": _normaliza_numero(numero_voo), "origem": origem,
                "destino": destino, "partida_utc": None, "chegada_utc": None,
                "cancelado": True, "reacomodado_para": None}

    segmentos = [s for s in (leitura.get("segmentos") or []) if isinstance(s, dict)]
    alvo = _normaliza_numero(numero_voo)

    def distancia(seg):
        try:
            return abs((datetime.strptime(seg.get("data") or "", "%Y-%m-%d")
                        - datetime.strptime(data_local, "%Y-%m-%d")).days)
        except ValueError:
            return 999

    mesmo_numero = [s for s in segmentos
                    if _normaliza_numero(s.get("numero_voo")) == alvo
                    and (s.get("origem") or "").upper() in ((origem or "").upper(), "")]
    vendido = min(mesmo_numero, key=distancia) if mesmo_numero else None
    lido = de_segmento_portal(vendido) if vendido else None
    if lido and not lido["cancelado"]:
        return lido

    substitutos = [s for s in segmentos
                   if _normaliza_numero(s.get("numero_voo")) != alvo
                   and (s.get("origem") or "").upper() == (origem or "").upper()
                   and (s.get("destino") or "").upper() == (destino or "").upper()
                   and distancia(s) <= DIAS_REACOMODACAO
                   and not _cancelado_no_portal(s.get("status"))]
    if substitutos:
        novo = de_segmento_portal(min(substitutos, key=distancia))
        base = lido or {"numero_voo": alvo, "origem": origem, "destino": destino,
                        "partida_utc": None, "chegada_utc": None}
        return dict(base, cancelado=True, reacomodado_para=novo)
    return lido


# --------------------------------------------------------------- proposta

def _minutos_entre(a, b):
    ia, ib = instante_utc(a), instante_utc(b)
    if ia is None or ib is None:
        return None
    return abs((ia - ib).total_seconds()) / 60.0


def montar(reminder, leitura, fonte):
    """Reminder da Volly x leitura da companhia -> proposta.

    Devolve {"status", "campos", "mensagem"} (mais "fonte", pra gravar):
      - "proposta": algo difere (horario >= 5 min, numero ou aeroporto);
        `campos` = {campo_da_volly: {"de": valor atual, "para": valor novo}}
        no formato da Volly;
      - "sem_proposta": cancelado sem voo novo (ou nenhuma leitura);
      - "nada_a_mudar": a Volly ja esta igual a companhia.
    """
    resultado = {"status": "sem_proposta", "campos": {}, "mensagem": MSG_SEM_LEITURA,
                 "fonte": fonte}
    if not reminder or not leitura:
        return resultado

    alvo = leitura
    if leitura.get("cancelado"):
        if not leitura.get("reacomodado_para"):
            motivo = leitura.get("motivo_sem_proposta")
            resultado["mensagem"] = (
                "⚠️ Sem proposta: %s. Conferir no portal da cia." % motivo
                if motivo else MSG_CANCELADO)
            return resultado
        alvo = leitura["reacomodado_para"]

    orig_volly = (reminder.get("departure_airport") or "").upper()
    dest_volly = (reminder.get("arrival_airport") or "").upper()
    orig_cia = (alvo.get("origem") or orig_volly).upper()
    dest_cia = (alvo.get("destino") or dest_volly).upper()

    campos = {}
    partes = []

    num_volly = reminder.get("flight_number") or ""
    num_cia = alvo.get("numero_voo")
    # _numero_iata dos dois lados: a Volly cadastra "TP0007" e a AeroDataBox
    # devolve "TP 7" - sem tirar o zero a esquerda viraria troca de voo falsa
    if num_cia and _numero_iata(num_volly, reminder.get("airline")) != _numero_iata(num_cia):
        campos["flight_number"] = {"de": num_volly, "para": num_cia}
        partes.append("voo %s → %s" % (num_volly, num_cia))

    if orig_cia != orig_volly:
        campos["departure_airport"] = {"de": reminder.get("departure_airport"), "para": orig_cia}
        partes.append("origem %s → %s" % (orig_volly, orig_cia))
    if dest_cia != dest_volly:
        campos["arrival_airport"] = {"de": reminder.get("arrival_airport"), "para": dest_cia}
        partes.append("destino %s → %s" % (dest_volly, dest_cia))

    for campo, aero_volly, aero_cia, chave, rotulo in (
            ("departure_datetime", orig_volly, orig_cia, "partida_utc", "partida"),
            ("arrival_datetime", dest_volly, dest_cia, "chegada_utc", "chegada")):
        valor_volly = reminder.get(campo)
        utc_cia = alvo.get(chave)
        if not utc_cia:
            continue
        utc_volly = fusos.volly_para_utc(valor_volly, aero_volly) if valor_volly else None
        diferenca = _minutos_entre(utc_volly, utc_cia)
        # aeroporto trocado muda o fuso da conversao: mesmo com a hora igual,
        # o valor gravado na Volly precisa ser refeito
        if diferenca is not None and diferenca < MINUTOS_TOLERANCIA and aero_cia == aero_volly:
            continue
        para = fusos.utc_para_volly(utc_cia, aero_cia)
        if valor_volly and _minutos_entre(valor_volly, para) == 0:
            continue
        campos[campo] = {"de": valor_volly, "para": para}
        partes.append("%s %s → %s" % (
            rotulo,
            _texto_local(utc_volly, aero_volly) if utc_volly else "?",
            _texto_local(utc_cia, aero_cia)))

    if not campos:
        resultado.update(status="nada_a_mudar", mensagem=MSG_IGUAL)
        return resultado

    # Rota (aeroporto) ou numero diferente so vira proposta quando vem do
    # PORTAL da cia - a unica fonte que ve a reserva do passageiro. Pela
    # grade (monitor Volly/malha) isso e ambiguo: TSTABX G3 1541 MCZ-CGH em
    # 19/11 apareceu so como GYN-CGH (27/09/2026) e a proposta mudaria a
    # origem pra GYN - pode ser reacomodacao, voo com escala, grade nova.
    # Nesses casos a equipe confere no portal e ajusta a mao.
    muda_rota = any(c in campos for c in ("departure_airport", "arrival_airport", "flight_number"))
    if muda_rota and not str(fonte or "").startswith("portal-"):
        resultado.update(
            status="sem_proposta", campos={},
            mensagem="⚠️ Sem proposta automática: a companhia mostra outra rota/voo (%s). "
                     "Pode ser reacomodação ou escala — conferir no portal da cia e ajustar "
                     "na Volly à mão." % "; ".join(partes))
        return resultado

    resultado.update(
        status="proposta", campos=campos,
        mensagem="✏️ Na Volly mudaria — %s %s: %s" % (
            reminder.get("locator") or "?", num_volly or "?", "; ".join(partes)))
    return resultado


# Mesma normalizacao do monitor (checar_volly_cloud.numero_iata), repetida
# aqui pra este modulo continuar puro e sem importar o monitor inteiro.
_ICAO_PARA_IATA = {"GLO": "G3", "TAM": "LA", "LAN": "LA", "AZU": "AD", "TAP": "TP"}
_CIA_PARA_IATA = {"GOL": "G3", "LATAM": "LA", "AZUL": "AD", "TAP": "TP"}


def _numero_iata(numero, cia=None):
    n = _normaliza_numero(numero)
    if n[:3] in _ICAO_PARA_IATA and n[3:].isdigit():
        n = _ICAO_PARA_IATA[n[:3]] + n[3:]
    elif n.isdigit() and (cia or "").upper() in _CIA_PARA_IATA:
        n = _CIA_PARA_IATA[cia.upper()] + n
    # zero a esquerda do numero sai (TP0007 = TP7), igual
    # comparacao._normaliza_voo desde 27/09/2026
    m = re.match(r"^([A-Z0-9]{2})(\d+)$", n)
    if m and not n.isdigit():
        n = m.group(1) + str(int(m.group(2)))
    return n
