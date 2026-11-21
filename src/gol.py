"""Leitura da pagina "Gerencie sua viagem" da GOL.

O deep link ja leva os tres campos e **se envia sozinho** - nao clicar em nada.
Clicar atrapalha: quando a pagina termina de carregar o botao ja sumiu, e a
tentativa de clique derruba o fluxo. Basta abrir e esperar a URL virar
/minhas-viagens/detalhes-da-viagem.

Diferente da LATAM, a GOL nao depende de PDF: localizador, origem e sobrenome
ja estao no CRM.

Camada pura: recebe o TEXTO da pagina e devolve dados.
"""

import re

URL_CONSULTA = ("https://b2c.voegol.com.br/minhas-viagens/encontrar-viagem"
                "?codigoReserva=%s&origem=%s&sobrenome=%s")
URL_DETALHE = "detalhes-da-viagem"

# Quando a GOL ja reacomodou o voo sozinha (mudou horario/voo), o deep link
# redireciona pra ca em vez de detalhes-da-viagem - a pagina pede "voce
# concorda com essa alteracao?" em vez de mostrar o itinerario normal. E o
# sinal mais explicito que existe: nao depende de regex em texto, e nao
# precisa de leitura confiavel pra valer.
URL_REACOMODACAO = "reacomodacao-de-voo"

# API que a pagina chama para validar localizador+origem+sobrenome. E dela que
# sai o motivo real de uma consulta que nao abre: a tela so mostra "Houve um
# erro. Tente novamente mais tarde." e volta o formulario vazio.
API_CONSULTA = "pnr-bnpl-validation"

BLOQUEIO_RECAPTCHA = "reCAPTCHA da GOL barrou a consulta automatizada"

RE_ERRO_RECAPTCHA = re.compile(r"recaptcha", re.I)

# Codigo de companhia pode ter digito: G3 (Gol), 4M, AD. [A-Z]{2} nao serve.
RE_VOO = re.compile(r"^([A-Z][A-Z0-9])\s?(\d{2,4})\b")
RE_IATA = re.compile(r"^([A-Z]{3})$")
RE_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_HORA = re.compile(r"^(\d{1,2}):(\d{2})$")

RE_CONFIRMADA = re.compile(r"Reserva:\s*Confirmada", re.I)
RE_NAO_ENCONTRADA = re.compile(
    r"n[aã]o (?:foi )?(?:poss[ií]vel )?(?:encontr|localiz)|"
    r"reserva n[aã]o|dados n[aã]o conferem|verifique os dados", re.I)

# Avisos que a GOL exibe quando mexeu no voo. Sao o sinal que interessa.
AVISOS = (
    ("cancelado", r"voo\s+cancelad|reserva\s+cancelad|\bcancelad[ao]\b"),
    ("alteracao", r"altera[cç][aã]o|alterad[oa]|remarcad[oa]|"
                  r"mudan[cç]a\s+de\s+hor[aá]rio|novo\s+hor[aá]rio"),
    ("atraso", r"\batras[oa]\b"),
    ("irregularidade", r"irregularidade|contingencia|imprevisto"),
    ("acao_necessaria", r"a[cç][aã]o necess[aá]ria|pend[eê]ncia|"
                        r"regularize|entre em contato"),
)


def montar_url(localizador, origem, sobrenome):
    from urllib.parse import quote
    return URL_CONSULTA % (quote(localizador), quote(origem), quote(sobrenome))


def motivo_da_falha(capturado):
    """Por que a consulta nao abriu? Le a resposta da API, nao a tela.

    Devolve o motivo em texto, ou None se a API nao recusou (ai o problema e
    outro: pagina lenta, rede, etc).

    Existe porque a GOL exige score de reCAPTCHA nesse endpoint (confirmado em
    29/07/2026: 500 com "Error recaptcha: score recaptcha is fail"). Navegador
    automatizado tira score baixo e o score varia por sessao, entao parte das
    consultas passa e parte e recusada. Sem ler isso, a rodada gastava 66s por
    reserva esperando uma URL que nunca ia mudar e culpava a pagina.

    Nao se tenta contornar o reCAPTCHA: derrubar o IP da agencia custa mais
    que conferir a mao. Reserva barrada vai para o painel (src/painel.py).
    """
    for registro in (capturado or {}).values():
        if API_CONSULTA not in registro.get("url", ""):
            continue
        corpo = registro.get("json")
        corpo = corpo if isinstance(corpo, dict) else {}
        erro = corpo.get("error")
        erro = erro if isinstance(erro, dict) else {}
        mensagem = str(erro.get("message") or "")

        if RE_ERRO_RECAPTCHA.search(mensagem):
            return BLOQUEIO_RECAPTCHA
        if registro.get("status", 0) >= 400:
            return "a API da GOL respondeu %d (%s)" % (
                registro["status"], mensagem[:70] or "sem detalhe")
        if corpo.get("success") is False:
            return "a GOL recusou a consulta (%s)" % (
                mensagem[:70] or "sem detalhe")
    return None


def ler_pagina(texto):
    """Extrai a reserva do texto da pagina de detalhes.

    Devolve o mesmo formato do latam.ler_api(), para a comparacao ser a mesma.
    """
    resultado = {"encontrada": False, "confirmada": False, "cancelada": False,
                 "avisos": [], "segmentos": [], "segmentos_nao_expandidos": 0,
                 "status_pedido": None, "confiavel": False, "motivo": None}
    if not texto:
        return resultado

    if RE_NAO_ENCONTRADA.search(texto):
        return resultado
    if not RE_CONFIRMADA.search(texto) and "Voo da ida" not in texto \
            and "Voo da volta" not in texto:
        return resultado

    resultado["encontrada"] = True
    resultado["confirmada"] = bool(RE_CONFIRMADA.search(texto))
    resultado["status_pedido"] = "Confirmada" if resultado["confirmada"] else "?"

    # Avisos so valem no miolo da reserva: o rodape institucional fala de
    # "cancelamento" em texto de politica e viraria alarme falso.
    inicio = texto.find("Sua viagem")
    fim = texto.find("Gerenciar a sua viagem")
    miolo = texto[inicio:fim] if 0 <= inicio < fim else texto[:4000]
    for rotulo, padrao in AVISOS:
        achado = re.search(padrao, miolo, re.I)
        if achado:
            resultado["avisos"].append((rotulo, achado.group(0)))
    resultado["cancelada"] = any(r == "cancelado" for r, _ in resultado["avisos"])

    resultado["segmentos"] = _segmentos(texto)
    resultado["confiavel"], resultado["motivo"] = _confiavel(miolo, resultado["segmentos"])
    return resultado


# Marcas de trecho com conexao/escala. A pagina lista mais aeroportos do que
# um par origem-destino, e o leitor funde os trechos: em 29/07/2026 isso gerou
# 4 alertas falsos de "rota alterada" numa reserva NAT-GIG-CWB intacta.
RE_CONEXAO = re.compile(r"conex[aã]o|escala|\bparada\b|1 parada|2 paradas", re.I)


def _confiavel(miolo, segmentos):
    """A leitura pode ser usada para afirmar que algo mudou?

    Só devolve True quando o itinerario e simples o bastante para ter certeza.
    Na duvida o sistema cala a boca: alerta errado custa uma ligacao a um
    cliente avisando de mudanca que nao existe.

    Recebe o MIOLO da reserva, nao a pagina inteira: o rodape institucional
    fala de conexao e faria todo voo direto virar "nao confiavel".
    """
    if RE_CONEXAO.search(miolo):
        return False, "itinerario com conexao"
    for seg in segmentos:
        if not (seg.get("origem") and seg.get("destino")
                and seg.get("data") and seg.get("partida")):
            return False, "trecho incompleto na leitura"
    return True, None


def _segmentos(texto):
    """Le os trechos. Cada um vem como:

        G3 1681 OPERADO POR / TARIFA / ... / NAT / 03/08/2026 / 03:35 / Natal
        / Voo direto / GRU / 03/08/2026 / 07:10 / Sao Paulo
    """
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    segmentos = []
    bloco = None

    for linha in linhas:
        voo = RE_VOO.match(linha)
        if voo and ("OPERADO" in linha.upper() or len(linha) < 12):
            if bloco and bloco["origem"] and bloco["destino"]:
                segmentos.append(bloco)
            bloco = {"numero_voo": voo.group(1) + voo.group(2), "data": None,
                     "origem": None, "destino": None,
                     "partida": None, "chegada": None, "status": None}
            continue

        if bloco is None:
            continue

        iata = RE_IATA.match(linha)
        if iata:
            if bloco["origem"] is None:
                bloco["origem"] = iata.group(1)
            elif bloco["destino"] is None:
                bloco["destino"] = iata.group(1)
            continue

        data = RE_DATA.match(linha)
        if data:
            dia, mes, ano = data.groups()
            iso = "%s-%s-%s" % (ano, mes, dia)
            if bloco["data"] is None:
                bloco["data"] = iso
            continue

        hora = RE_HORA.match(linha)
        if hora:
            marca = "%02d:%02d" % (int(hora.group(1)), int(hora.group(2)))
            if bloco["partida"] is None:
                bloco["partida"] = marca
            elif bloco["chegada"] is None:
                bloco["chegada"] = marca

    if bloco and bloco["origem"] and bloco["destino"]:
        segmentos.append(bloco)
    return segmentos


def achados_de_aviso(leitura, voos_da_reserva):
    """Transforma os avisos da pagina em alertas."""
    achados = []
    referencia = voos_da_reserva[0] if voos_da_reserva else None
    for rotulo, trecho in leitura.get("avisos", []):
        achados.append({
            "tipo": {"cancelado": "trecho_cancelado",
                     "alteracao": "alterado_pela_companhia",
                     "atraso": "atraso",
                     "irregularidade": "em_contingencia",
                     "acao_necessaria": "acao_necessaria"}.get(rotulo, rotulo),
            "voo_crm": referencia,
            "detalhe": 'a GOL exibiu "%s" na pagina da reserva' % trecho,
        })
    if leitura.get("encontrada") and not leitura.get("confirmada"):
        achados.append({
            "tipo": "sem_confirmacao",
            "voo_crm": referencia,
            "detalhe": "a pagina nao mostrou 'Reserva: Confirmada'",
        })
    return achados
