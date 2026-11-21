"""Leitura da reserva da Azul pela API canonica que a propria pagina consome.

A Azul e a unica das tres que NAO pede sobrenome: o link leva so o PNR e o
aeroporto de origem (ver qualidade.REQUISITOS).

    /br/pt/home/minhas-viagens/confirmacao?pnr=IJ56KL&origin=BSB

Abrindo esse link, a pagina autentica e chama:

    b2c-api.voeazul.com.br/canonical/api/booking/v5/bookings/<PNR>

E dela que lemos - nao da tela. Medido em 30/07/2026 com AB12CD: a resposta
traz o itinerario inteiro estruturado, e o texto da pagina e 90% oferta de
hotel, cupom e assento. Raspar aquilo seria trabalhoso e fragil a toa.

Vantagem sobre o leitor da GOL: como cada trecho vem separado no JSON, conexao
NAO atrapalha. O problema la era o parser de texto fundir trechos; aqui nao ha
o que fundir, entao itinerario com escala continua conferivel.

HORARIOS SAO LOCAIS. `std` veio 2026-08-20T20:35:00 para o voo que o CRM tem
como 20:35 em REC. Diferente do banco do MilhasFlow, que grava UTC, aqui nao se
converte nada - converter geraria "horario alterado" em todos os voos.

Camada pura: recebe o JSON e devolve dados, no mesmo formato de
latam.ler_api() e gol.ler_pagina(), para a comparacao ser a mesma.
"""

import re
from urllib.parse import quote

URL_CONSULTA = ("https://www.voeazul.com.br/br/pt/home/minhas-viagens/"
                "confirmacao?pnr=%s&origin=%s")

# Capturamos TUDO do backend (inclusive o /authentication/, que e onde uma
# recusa aparece primeiro) e so depois filtramos a resposta da reserva. Guardar
# so o que deu certo deixaria a falha invisivel - foi o que fez a GOL passar
# dias parecendo "pagina que nao carrega".
API_CAPTURA = "b2c-api.voeazul.com.br"
API_BOOKING = "/api/booking/"
API_AUTENTICACAO = "/api/authentication/"

# Endpoints cujo erro realmente impede a checagem. A pagina chama vario outro
# servico acessorio (/forecast, previsao do tempo do destino, e companhia) que
# responde 404 sem que a reserva tenha problema nenhum.
API_ESSENCIAIS = (API_BOOKING, API_AUTENTICACAO)

# Validado contra resposta real da API em 30/07/2026 (AB12CD, ida e volta).
# Caso de teste em testes/paginas/azul_pm99tj.json.
CALIBRADO = True

# Status da reserva inteira, em data.info.status
STATUS_OK = {"CONFIRMED"}
RE_STATUS_CANCELADO = re.compile(r"cancel", re.I)


def montar_url(localizador, origem):
    return URL_CONSULTA % (quote(localizador), quote(origem))


# Sinais de que a companhia limitou o acesso. Com a Azul nao se insiste: foi
# ela que bloqueou o IP da agencia em 29/07/2026, e o limitador ja reserva a
# ela o intervalo mais largo (25-45s) e o unico teto por hora do sistema.
SINAIS_DE_BLOQUEIO = (
    "acesso foi limitado",
    "comportamento incomum",
    "muitas tentativas",
    "bloqueado temporariamente",
    "access denied",
    "unusual traffic",
    "too many requests",
)


def sinal_de_bloqueio(texto):
    """Devolve o sinal de bloqueio encontrado no inicio da pagina, ou None.

    So o comeco do texto: o rodape institucional fala de "acesso" em contexto
    de politica de privacidade e nao e bloqueio nenhum.
    """
    if not texto:
        return None
    baixo = texto[:1500].lower()
    for sinal in SINAIS_DE_BLOQUEIO:
        if sinal in baixo:
            return sinal
    return None


def resposta_do_booking(capturado):
    """Acha, entre as respostas capturadas, a da reserva. None se nao veio."""
    for registro in (capturado or {}).values():
        if API_BOOKING in registro.get("url", ""):
            return registro
    return None


def motivo_da_falha(capturado):
    """Por que a consulta nao trouxe a reserva? Le a API, nao a tela.

    Devolve (motivo, e_bloqueio). motivo None significa que nada recusou.

    e_bloqueio separa "a Azul esta barrando o acesso" de "deu erro": o primeiro
    poe o dominio de quarentena e interrompe a rodada, o segundo so manda a
    reserva para o painel manual.
    """
    registros = list((capturado or {}).values())

    # 403/429 em QUALQUER endpoint do backend e sinal de IP barrado - a Azul
    # nao recusa so uma rota quando decide fechar.
    for registro in registros:
        if registro.get("status", 0) in (403, 429):
            return ("a Azul recusou o acesso (HTTP %d)"
                    % registro["status"]), True

    # Fora disso, so erro em endpoint ESSENCIAL conta. Em 30/07/2026 tratar
    # qualquer 404 como recusa mandou 2 reservas intactas para o painel e parou
    # a rodada por "2 recusas seguidas" - o 404 era de /forecast.
    for registro in registros:
        url = registro.get("url", "")
        if not any(rota in url for rota in API_ESSENCIAIS):
            continue
        status = registro.get("status", 0)
        if status < 400:
            continue
        corpo = registro.get("json")
        corpo = corpo if isinstance(corpo, dict) else {}
        erro = corpo.get("error")
        erro = erro if isinstance(erro, dict) else {}
        mensagem = str(corpo.get("message") or erro.get("message") or "")
        return ("a API da Azul respondeu %d em %s (%s)"
                % (status, _trecho_final(url),
                   mensagem[:60] or "sem detalhe")), False
    return None, False


def _trecho_final(url):
    return url.rsplit("/", 2)[-2] if url.count("/") > 2 else url


def ler_api(resposta):
    """Le a resposta de /canonical/api/booking/v5/bookings/<PNR>.

    Devolve o mesmo formato de gol.ler_pagina(): encontrada, confirmada,
    cancelada, avisos, segmentos[], confiavel, motivo.
    """
    vazio = {"encontrada": False, "confirmada": False, "cancelada": False,
             "avisos": [], "segmentos": [], "segmentos_nao_expandidos": 0,
             "status_pedido": None, "confiavel": False, "motivo": None,
             "localizador": None}
    if not isinstance(resposta, dict):
        return vazio

    dados = resposta.get("data")
    if not isinstance(dados, dict) or not dados.get("journeys"):
        return vazio

    status = str(((dados.get("info") or {}).get("status")) or "")
    resultado = dict(vazio)
    resultado["encontrada"] = True
    resultado["localizador"] = dados.get("recordLocator")
    resultado["status_pedido"] = status or "?"
    resultado["confirmada"] = status.upper() in STATUS_OK
    resultado["cancelada"] = bool(RE_STATUS_CANCELADO.search(status))

    segmentos, remanejados, com_parada = [], [], []
    for jornada in dados.get("journeys") or []:
        for trecho in jornada.get("segments") or []:
            ident = trecho.get("identifier") or {}
            numero = ident.get("flightNumber")
            cia = ident.get("carrierCode") or ""
            partida = ident.get("std") or ""
            chegada = ident.get("sta") or ""

            # std/sta ja vem na hora local do aeroporto - nao converter
            segmento = {
                "data": partida[:10] or None,
                "origem": ident.get("departureStation"),
                "destino": ident.get("arrivalStation"),
                "numero_voo": ("%s%s" % (cia, numero)) if numero else None,
                "partida": partida[11:16] or None,
                "chegada": chegada[11:16] or None,
                "status": status,
                "remanejado": bool(trecho.get("isReaccommodation")),
                "paradas": len(trecho.get("stops") or []),
                "equipamento": (trecho.get("equipment") or {}).get("name"),
            }
            segmentos.append(segmento)
            if segmento["remanejado"]:
                remanejados.append(segmento)
            if segmento["paradas"]:
                com_parada.append(segmento)

    resultado["segmentos"] = segmentos
    if resultado["cancelada"]:
        resultado["avisos"].append(("cancelado", "status %s" % status))
    for seg in remanejados:
        resultado["avisos"].append(
            ("alteracao", "%s remanejado pela companhia" % seg["numero_voo"]))

    resultado["confiavel"], resultado["motivo"] = _confiavel(resultado)
    return resultado


def _confiavel(leitura):
    """A leitura pode sustentar uma afirmacao de mudanca?

    Ao contrario da GOL, conexao nao derruba a confianca: o JSON entrega cada
    trecho separado, entao nao ha risco de o leitor fundir dois trechos e
    inventar "rota alterada". O que derruba e trecho incompleto ou status que
    nao reconhecemos - ai o sistema cala a boca.
    """
    if not leitura["segmentos"]:
        return False, "nenhum trecho na resposta"
    for seg in leitura["segmentos"]:
        if not (seg.get("origem") and seg.get("destino")
                and seg.get("data") and seg.get("partida")
                and seg.get("numero_voo")):
            return False, "trecho incompleto na resposta"
    status = (leitura.get("status_pedido") or "").upper()
    if status not in STATUS_OK and not leitura["cancelada"]:
        return False, "status desconhecido: %s" % leitura["status_pedido"]
    return True, None


def achados_de_aviso(leitura, voos_da_reserva):
    """Transforma os avisos da reserva em alertas.

    Passa mesmo com leitura nao confiavel: cancelamento anunciado pela propria
    companhia nao depende de o resto ter sido lido direito, e silenciar isso
    por cautela e pior que o alarme falso que a cautela evita.
    """
    achados = []
    referencia = voos_da_reserva[0] if voos_da_reserva else None
    por_voo = {}
    for v in voos_da_reserva:
        por_voo[re.sub(r"[^A-Z0-9]", "", (v.get("numero_voo") or "").upper())] = v

    for rotulo, trecho in leitura.get("avisos", []):
        alvo = referencia
        achado = re.match(r"^([A-Z0-9]+) ", trecho)
        if achado:
            alvo = por_voo.get(achado.group(1), referencia)
        achados.append({
            "tipo": {"cancelado": "trecho_cancelado",
                     "alteracao": "alterado_pela_companhia",
                     "atraso": "atraso",
                     "irregularidade": "em_contingencia"}.get(rotulo, rotulo),
            "voo_crm": alvo,
            "detalhe": "a Azul informou: %s" % trecho,
        })

    if leitura.get("encontrada") and not leitura.get("confirmada") \
            and not leitura.get("cancelada"):
        achados.append({
            "tipo": "sem_confirmacao",
            "voo_crm": referencia,
            "detalhe": "reserva com status '%s', nao 'Confirmed'"
                       % leitura.get("status_pedido"),
        })
    return achados
