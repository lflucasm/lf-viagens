"""Comparacao entre o que a companhia mostra e o que o CRM tem.

Generico de proposito: LATAM e GOL entregam os dados de formas completamente
diferentes (JSON de API x texto de pagina), mas depois de lidos viram a mesma
estrutura de segmentos - e a comparacao vale para as duas.

A chave de casamento e numero do voo + data. Sobrenome nao serve: SILVA e MELO
se repetem entre clientes.
"""

import re
from datetime import datetime


# Prefixo ICAO que aparece no CRM no lugar do IATA (GLO1618 = G3 1618).
# "GOL" nao e ICAO de ninguem: e o nome da marca digitado no lugar do codigo
# (GOL1549, 17/10/2026) - a Volly resolve pelo nome da cia, aqui vale igual.
_ICAO_PARA_IATA = {"GLO": "G3", "GOL": "G3", "TAM": "LA", "LAN": "LA", "AZU": "AD", "TAP": "TP"}

# Campo `cia` do CRM -> prefixo IATA, pra numero que veio so com digitos.
CIA_PARA_IATA = {"GOL": "G3", "LATAM": "LA", "AZUL": "AD", "TAP": "TP"}


def _normaliza_voo(numero):
    """Forma unica de um numero de voo pra comparar fontes diferentes.

    Alem de tirar espaco/pontuacao: prefixo ICAO vira IATA e zero a esquerda
    do numero sai (TP0007 = TP7). Sem isso, trecho escrito "GLO1618" no CRM
    contra "G3 1618" na malha virava "ausente na companhia" falso (27/09/2026).

    Conexao digitada num trecho so ("TP1930 + TP1928", NAT-OPO) fica com o
    PRIMEIRO voo: e o que parte do aeroporto do trecho. O segundo voo nao e
    checado (a hora e o aeroporto da conexao nao estao no cadastro).
    """
    numero = (numero or "").split("+")[0]
    n = re.sub(r"[^A-Z0-9]", "", numero.upper())
    if n[:3] in _ICAO_PARA_IATA and n[3:].isdigit():
        n = _ICAO_PARA_IATA[n[:3]] + n[3:]
    m = re.match(r"^([A-Z0-9]{2})(\d+)$", n)
    if m and not n.isdigit():
        n = m.group(1) + str(int(m.group(2)))
    return n


def numero_iata(numero, cia=None):
    """Numero de voo no padrao IATA que a AeroDataBox e a Volly entendem.

    Alem de _normaliza_voo: numero so com digitos ("1885") ganha o prefixo da
    companhia do CRM (GOL -> G3). Sem isso a malha mandava "1885" cru pra
    API e nunca achava o voo (TSTACX, 17/10/2026).
    """
    n = _normaliza_voo(numero)
    if n.isdigit() and (cia or "").strip().upper() in CIA_PARA_IATA:
        return CIA_PARA_IATA[cia.strip().upper()] + n
    return n


def tem_trecho_futuro(leitura, hoje=None):
    """A reserva ainda tem voo por acontecer?

    A pasta guarda PDF de viagem antiga tambem. Como a companhia reaproveita o
    mesmo numero de voo todo dia, uma viagem de julho casaria com uma reserva
    de outubro pelo numero - e viraria alerta falso. Viagem passada sai fora.
    """
    limite = hoje or datetime.now().strftime("%Y-%m-%d")
    return any((s.get("data") or "") >= limite for s in leitura.get("segmentos", []))


def identificar(leitura, voos_crm):
    """Descobre a qual localizador do CRM esta reserva corresponde.

    Necessario porque o PDF da LATAM nao guarda o PNR - so o numero de compra.
    Sem este passo a comparacao rodaria contra a base inteira e acusaria como
    "sumido" todo voo que simplesmente pertence a outra reserva.

    Pontuacao: voo+data vale mais que voo+rota, que vale mais que so o voo.
    Assim uma remarcacao de data ainda identifica a reserva certa.
    """
    pontos = {}
    for seg in leitura.get("segmentos", []):
        numero = _normaliza_voo(seg.get("numero_voo"))
        if not numero:
            continue
        for v in voos_crm:
            if _normaliza_voo(v.get("numero_voo")) != numero:
                continue
            loc = v.get("localizador")
            ganho = 1
            if (v.get("embarque_local") or "")[:10] == seg.get("data"):
                ganho = 4
            elif v.get("origem") == seg.get("origem") and v.get("destino") == seg.get("destino"):
                ganho = 2
            pontos[loc] = pontos.get(loc, 0) + ganho

    if not pontos:
        return None, 0
    melhor = max(pontos.items(), key=lambda i: i[1])
    return melhor[0], melhor[1]


def observacoes_da_leitura(leitura, voos_crm):
    """O que esta leitura viu, por voo do CRM: [(voo_id, partida, rota, situacao)].

    Fica aqui, e nao em db.py, para continuar sendo funcao PURA - os quatro
    conectores usam o mesmo casamento (numero do voo + data) e quem grava e o
    chamador. Assim da para testar sem banco.

    `partida` sai como "AAAA-MM-DD HH:MM" na hora LOCAL do aeroporto, que e o
    que todos os leitores ja entregam.
    """
    por_chave = {}
    for v in voos_crm:
        chave = (_normaliza_voo(v.get("numero_voo")), (v.get("embarque_local") or "")[:10])
        por_chave.setdefault(chave, []).append(v)

    vistas = []
    for seg in leitura.get("segmentos", []):
        crms = por_chave.get((_normaliza_voo(seg.get("numero_voo")), seg.get("data"))) or []
        for crm in crms:
            if not crm.get("id"):
                continue
            partida = None
            if seg.get("data") and seg.get("partida"):
                partida = "%s %s" % (seg["data"], seg["partida"])
            rota = None
            if seg.get("origem") and seg.get("destino"):
                rota = "%s-%s" % (seg["origem"], seg["destino"])
            vistas.append((crm["id"], partida, rota, seg.get("status")))
    return vistas


def comparar(leitura, voos_crm, observado_antes=None):
    """Cruza o que a companhia mostra agora com o que ELA MESMA mostrou antes.

    O casamento e por numero do voo + data - unico e sem ambiguidade. Sobrenome
    nao serve como chave: SILVA e MELO se repetem em varios clientes.

    `observado_antes`: {voo_id: {"partida", "rota"}} com a ULTIMA leitura
    confiavel desta mesma fonte (portal-latam, portal-gol, portal-azul ou
    malha - ver db.observacoes_por_fonte). E contra isso que horario_alterado
    e rota_alterada comparam, NAO contra o CRM: o CRM so serve para achar o
    voo (numero+data), montar o link de consulta e saber se ele existe.

    Motivo: o CRM nao e fonte confiavel de horario/rota. Em 10/08/2026 a
    reserva TSTAKX tinha LA3491 com origem=CGH no CRM (dado corrompido numa
    resincronizacao) contra origem=FOR tanto no portal quanto na malha - duas
    fontes independentes concordando contra o CRM. Comparar contra o CRM gerou
    8 alertas falsos em 6 dias porque o mesmo erro nunca mudava. Comparar
    contra a leitura anterior DESTA fonte so acusa quando algo realmente muda
    entre uma checagem e a proxima - e sem baseline (primeira vez que esta
    fonte ve o voo) a leitura de hoje so estabelece o ponto de partida, sem
    alertar.

    `leitura` e o dict devolvido por ler_pagina(). Importa o campo
    segmentos_nao_expandidos: a LATAM entrega a volta recolhida no acordeao, e
    sem expandir o trecho parece "sumido". Alertar ali seria falso positivo em
    toda reserva de ida e volta.

    Devolve lista de achados: {tipo, voo_crm, detalhe}.
    """
    if isinstance(leitura, list):          # compatibilidade com chamada antiga
        leitura = {"segmentos": leitura, "segmentos_nao_expandidos": 0}
    segmentos = leitura.get("segmentos", [])
    incompleta = leitura.get("segmentos_nao_expandidos", 0) > 0
    observado_antes = observado_antes or {}

    achados = []
    por_chave = {}
    for v in voos_crm:
        chave = (_normaliza_voo(v.get("numero_voo")), (v.get("embarque_local") or "")[:10])
        por_chave.setdefault(chave, []).append(v)

    vistos = set()
    for seg in segmentos:
        chave = (_normaliza_voo(seg.get("numero_voo")), seg.get("data"))
        crms = por_chave.get(chave)

        if not crms:
            # mesmo voo em outra data = remarcacao pela companhia. Duas
            # reservas podem estar no mesmo voo (ver voos_para_checar em
            # checar_malha.py) - cada uma precisa do seu proprio achado,
            # senao so a ultima da lista recebe o alerta.
            mesmo_voo = [v for (n, _), lista in por_chave.items()
                         if n == chave[0] for v in lista]
            if mesmo_voo:
                for crm_antigo in mesmo_voo:
                    achados.append({
                        "tipo": "data_alterada",
                        "voo_crm": crm_antigo,
                        "detalhe": "CRM %s -> companhia %s" % (
                            (crm_antigo.get("embarque_local") or "")[:10], seg.get("data")),
                    })
            elif (seg.get("data") or "") >= datetime.now().strftime("%Y-%m-%d"):
                # trecho passado nao entra: a lista do CRM so tem voo futuro,
                # entao a ida ja voada apareceria como "novo" em toda rodada
                achados.append({
                    "tipo": "voo_novo_na_companhia",
                    "voo_crm": None,
                    "detalhe": "%s em %s nao existe no CRM" % (
                        seg.get("numero_voo"), seg.get("data")),
                })
            continue

        vistos.add(chave)

        for crm in crms:
            anterior = observado_antes.get(crm.get("id")) or {}

            hora_anterior = (anterior.get("partida") or "")[11:16]
            if seg.get("partida") and hora_anterior and seg["partida"] != hora_anterior:
                achados.append({
                    "tipo": "horario_alterado",
                    "voo_crm": crm,
                    "detalhe": "visto antes %s -> agora %s" % (hora_anterior, seg["partida"]),
                })

            rota_anterior = anterior.get("rota")
            if seg.get("origem") and seg.get("destino") and rota_anterior:
                rota_atual = "%s-%s" % (seg["origem"], seg["destino"])
                if rota_atual != rota_anterior:
                    achados.append({
                        "tipo": "rota_alterada",
                        "voo_crm": crm,
                        "detalhe": "visto antes %s -> agora %s" % (rota_anterior, rota_atual),
                    })

    faltantes = [(chave, v) for chave, lista in por_chave.items()
                 if chave not in vistos for v in lista]
    for chave, crm in faltantes:
        achados.append({
            # com trecho recolhido na pagina nao da para afirmar que sumiu
            "tipo": "verificacao_incompleta" if incompleta else "ausente_na_companhia",
            "voo_crm": crm,
            "detalhe": "%s de %s %s" % (
                crm.get("numero_voo"), chave[1],
                "nao pode ser conferido (trecho recolhido na pagina)"
                if incompleta else "nao apareceu na reserva"),
        })

    return achados


def trecho_diferente_da_venda(segmento, voos_crm):
    """Achados "passageiro_remanejado": a companhia voa este numero de voo
    numa rota diferente da vendida.

    E o "Conferir voo" da tela da Volly. Diferente de rota_alterada (que so
    compara com a leitura anterior da MESMA fonte), aqui a referencia e a
    venda - vale ja na primeira leitura. Caso que motivou (23/10/2026): G3
    1541 vendido MCZ-CGH 07:10, a GOL passou o numero pra GYN-CGH 08:40 e a
    passageira (TSTABX) foi remanejada. A primeira leitura ja veio GYN-CGH,
    virou baseline, e o unico alerta foi "horario da venda nao bate" - a
    equipe leu como ajuste de horario e resolveu.

    Conexao digitada num trecho so (`composto`, ex. "TP1930 + TP1928") fica
    de fora: o primeiro voo nunca chega ao destino do trecho.
    """
    origem_cia = (segmento.get("origem") or "").upper()
    destino_cia = (segmento.get("destino") or "").upper()
    if not origem_cia or not destino_cia:
        return []
    hora_cia = segmento.get("prevista") or segmento.get("partida") or ""
    achados = []
    for voo in voos_crm:
        origem = (voo.get("origem") or "").upper()
        destino = (voo.get("destino") or "").upper()
        if voo.get("composto") or not origem or not destino:
            continue
        if (origem, destino) == (origem_cia, destino_cia):
            continue
        venda = voo.get("embarque_local") or ""
        achados.append({
            "tipo": "passageiro_remanejado",
            "voo_crm": voo,
            "detalhe": ("em %s: vendido %s-%s %s -> companhia %s-%s %s" % (
                venda[:10], origem, destino, venda[11:16],
                origem_cia, destino_cia, hora_cia)).strip(),
        })
    return achados
