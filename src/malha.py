"""Leitura da malha publicada pela companhia, por numero de voo + data.

Terceira fonte do sistema, e a unica que cobre 100% dos voos: nao pede
localizador, nem sobrenome, nem PDF, nem sessao. Pergunta "o voo G3 1681 do dia
03/08/2026 saiu do horario que o CRM diz?" - e para isso o CRM ja tem tudo
(numero do voo, trecho e data estao preenchidos em 48 de 48 voos futuros).

O QUE ESTA FONTE VE:  horario alterado, rota alterada, voo cancelado, atraso,
                      voo que deixou de operar naquela data.
O QUE ELA NAO VE:     evento no nivel da RESERVA - PNR cancelado, passageiro
                      remarcado para outro voo, bilhete cancelado. O voo antigo
                      continua na malha; so o passageiro saiu dele. Isso e
                      trabalho dos conectores de portal e do e-mail.

Por isso ela nao substitui LATAM/GOL/AZUL: cobre o ponto cego deles (cobertura)
e tem um ponto cego proprio (nivel da reserva). As duas coisas juntas e que
fecham o monitoramento.

FONTE DOS CAMPOS: contrato oficial da AeroDataBox (FlightContract,
FlightAirportMovementContract, DateTimeContract, FlightStatus). Os nomes aqui
nao foram adivinhados - saem do OpenAPI publicado.

    GET /flights/number/{numero}/{AAAA-MM-DD}?dateLocalRole=Departure
    -> 200 [FlightContract, ...]   |   204 sem conteudo

Camada pura: recebe o JSON e devolve dados. Nao acessa rede.
"""

import re
from datetime import datetime

# ------------------------------------------------------------- prioridade
# A cota (600 unidades/mes, 2 por consulta = 300 consultas) nao paga conferir
# todo voo todo dia. Entao a fonte trabalha por ROTACAO: cada voo tem um
# intervalo alvo, e a rodada gasta o orcamento do dia nos mais atrasados.
#
# A ordem de prioridade vem da operacao da agencia, nao de palpite:
#
#   - voo com menos de 8 dias a equipe JA acompanha pelo CRM, que abre o voo
#     para check-in e manipulacao. Robo ali e redundante.
#   - alteracao e cancelamento chegam quase sempre em voo DISTANTE.
#   - voo distante que muda tambem da tempo de reagir, entao vale conferir com
#     intervalo maior: o alerta nao se perde, so chega alguns dias depois.
#
# A deteccao NAO depende do intervalo: a comparacao e sempre contra o CRM, e
# nao contra a checagem anterior. Intervalo maior atrasa a noticia, nao a perde.
DIAS_MIN = 8

# (ate quantos dias de antecedencia, de quantos em quantos dias conferir)
# Esta e a PROPORCAO de referencia, escolhida pela agencia: 3 : 7 : 14. Ela nao
# e usada crua - `ajustar_faixas()` a escala para caber no credito disponivel,
# preservando a proporcao. A carteira muda toda semana (voo novo entra, voo
# antigo embarca), entao intervalo fixo ou sobraria credito parado ou estouraria
# a cota no dia 20.
FAIXAS_BASE = ((30, 3), (90, 7), (None, 14))

# Limites do ajuste. Sem eles um mes magro faria o sistema consultar o mesmo voo
# todo dia (desperdicio, a malha nao muda tanto), e um mes cheio faria o
# intervalo virar dois meses sem ninguem perceber.
FATOR_MIN = 0.6      # no maximo ~40% mais rapido que a proporcao base
FATOR_MAX = 5.0      # alem disso a carteira nao cabe no plano: avisar, nao mentir

UNIDADES_POR_CONSULTA = 2      # o endpoint de voo e TIER 2, medido na pratica
DIAS_DO_CICLO = 30             # a cota do RapidAPI renova a cada ~31 dias

# ---------------------------------------------------------------- status
# Enum FlightStatus do contrato oficial. ATENCAO: "Canceled" com UM L - e assim
# que a API escreve. "Cancelled" (dois L) nunca chega e o teste cobre isso.
CANCELADO = "Canceled"
CANCELAMENTO_INCERTO = "CanceledUncertain"
DESVIADO = "Diverted"
ATRASADO = "Delayed"

# Marcadores de qualidade (FlightAirportMovementQualityEnum). Sem Basic ou Live
# o horario e estimativa, e estimativa nao sustenta alerta de "mudou o
# horario": alarme falso custa uma ligacao a um cliente avisando de mudanca que
# nao existe.
QUALIDADE_FIRME = ("Basic", "Live")

# "AAAA-MM-DD HH:MM+03:00", "AAAA-MM-DDTHH:MM:SS", com ou sem fuso no fim.
# O contrato garante que DateTimeContract.local existe e e date-time, mas nao
# fixa o separador nem o offset - entao a leitura e tolerante e, se nao casar,
# devolve None em vez de chutar.
RE_INSTANTE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})")


def intervalo_alvo(dias, faixas=None):
    """De quantos em quantos dias conferir um voo que embarca em `dias`."""
    faixas = faixas or FAIXAS_BASE
    for limite, intervalo in faixas:
        if limite is None or dias <= limite:
            return intervalo
    return faixas[-1][1]


def demanda_diaria(candidatos, faixas=None, dias_min=None):
    """Quantas consultas por dia a carteira pede para manter o ritmo das faixas.

    Um voo conferido a cada 3 dias consome 1/3 de consulta por dia. Somando
    todos, sai o ritmo necessario - que e o que se compara com o orcamento.
    """
    dias_min = DIAS_MIN if dias_min is None else dias_min
    por_dia = 0.0
    for c in candidatos:
        dias = c.get("dias")
        if dias is None or dias < dias_min:
            continue
        por_dia += 1.0 / intervalo_alvo(dias, faixas)
    return por_dia


def escalar_faixas(fator, faixas=None):
    """Multiplica os intervalos pelo fator, preservando a proporcao."""
    faixas = faixas or FAIXAS_BASE
    return tuple((limite, max(1, int(round(intervalo * fator))))
                 for limite, intervalo in faixas)


def ajustar_faixas(candidatos, orcamento_diario_unidades, faixas=None,
                   dias_min=None):
    """Escala a proporcao de referencia para caber no credito disponivel.

    Devolve (faixas_ajustadas, diagnostico).

    fator > 1  carteira grande demais para o ritmo base: espaca as conferencias
    fator < 1  sobra credito: aproxima as conferencias, sem passar de FATOR_MIN

    O ajuste e proporcional de proposito: a agencia escolheu a relacao 3:7:14
    entre as faixas, e essa relacao e preservada. O que muda e a escala.
    """
    faixas = faixas or FAIXAS_BASE
    consultas = demanda_diaria(candidatos, faixas, dias_min)
    orcamento_consultas = (orcamento_diario_unidades or 0) / float(UNIDADES_POR_CONSULTA)

    diagnostico = {
        "consultas_base": consultas,
        "orcamento_consultas": orcamento_consultas,
        "fator": 1.0,
        "estourou": False,
    }

    if consultas <= 0 or orcamento_consultas <= 0:
        diagnostico["estourou"] = orcamento_consultas <= 0 and consultas > 0
        return faixas, diagnostico

    fator = consultas / orcamento_consultas
    if fator > FATOR_MAX:
        # nem espacando ao maximo a carteira cabe: nao adianta esticar mais,
        # o certo e dizer que faltam creditos
        diagnostico["estourou"] = True
        fator = FATOR_MAX
    fator = max(FATOR_MIN, fator)

    diagnostico["fator"] = fator
    ajustadas = escalar_faixas(fator, faixas)
    diagnostico["consultas_ajustadas"] = demanda_diaria(candidatos, ajustadas, dias_min)
    return ajustadas, diagnostico


def _dias_desde(data_texto, hoje):
    if not data_texto:
        return None
    try:
        anterior = datetime.strptime(data_texto[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (hoje - anterior).days


def priorizar(candidatos, hoje=None, orcamento_unidades=None, dias_min=None,
              faixas=None):
    """Escolhe o que conferir hoje dentro do orcamento.

    `candidatos`: lista de dicts com
        chave  - (numero_voo, data) — identifica a consulta
        dias   - dias de antecedencia do embarque
        ultima - data da ultima checagem ("AAAA-MM-DD") ou None

    Devolve (escolhidos, relatorio). `escolhidos` sao as chaves, na ordem de
    prioridade. `relatorio` conta por que cada um dos outros ficou fora, para
    a rodada poder dizer isso em voz alta em vez de simplesmente omitir voo.

    Nunca conferido vem primeiro: sem linha de base, esse voo e o unico sobre o
    qual o sistema nao sabe nada. Entre eles, o que embarca mais cedo antes.
    """
    hoje = hoje or datetime.now().date()
    dias_min = DIAS_MIN if dias_min is None else dias_min

    fila = []
    relatorio = {"acompanhado_no_crm": 0, "ainda_no_prazo": 0, "sem_orcamento": 0}

    for c in candidatos:
        dias = c.get("dias")
        if dias is None:
            continue
        if dias < dias_min:
            # a equipe ja olha esse voo no CRM; gastar cota aqui tira dos
            # distantes, que e onde a mudanca aparece
            relatorio["acompanhado_no_crm"] += 1
            continue

        alvo = intervalo_alvo(dias, faixas)
        desde = _dias_desde(c.get("ultima"), hoje)
        if desde is None:
            atraso = float("inf")      # nunca conferido
        else:
            atraso = desde / float(alvo)
            if atraso < 1.0:
                relatorio["ainda_no_prazo"] += 1
                continue
        fila.append((atraso, dias, c["chave"]))

    # mais atrasado primeiro (-atraso); empatados, embarque mais proximo antes.
    # Nunca conferido tem atraso infinito, entao -inf o poe na frente de tudo.
    fila.sort(key=lambda i: (-i[0], i[1]))

    escolhidos = []
    gasto = 0
    for _, _, chave in fila:
        if orcamento_unidades is not None and \
                gasto + UNIDADES_POR_CONSULTA > orcamento_unidades:
            relatorio["sem_orcamento"] += 1
            continue
        escolhidos.append(chave)
        gasto += UNIDADES_POR_CONSULTA

    relatorio["unidades"] = gasto
    return escolhidos, relatorio


def _instante(contrato):
    """DateTimeContract -> ("AAAA-MM-DD", "HH:MM"). (None, None) se nao der.

    Usa SEMPRE o campo `local`, nunca o `utc`. Tratar UTC como local foi o bug
    que gerou alerta de "horario alterado" em 100% dos voos (ver fusos.py) - e
    aqui a API ja entrega a hora local do aeroporto, entao nao existe motivo
    para converter nada.
    """
    if not isinstance(contrato, dict):
        return None, None
    achado = RE_INSTANTE.match(str(contrato.get("local") or ""))
    if not achado:
        return None, None
    return achado.group(1), "%s:%s" % (achado.group(2), achado.group(3))


def _iata(movimento):
    if not isinstance(movimento, dict):
        return None
    aeroporto = movimento.get("airport")
    if not isinstance(aeroporto, dict):
        return None
    # iata e nullable no contrato. Sem ele nao se compara rota - o CRM fala
    # IATA, e comparar contra ICAO acusaria rota alterada em todo voo.
    return (aeroporto.get("iata") or "").strip().upper() or None


def _horario_firme(movimento):
    if not isinstance(movimento, dict):
        return False
    marcas = movimento.get("quality") or []
    return any(m in QUALIDADE_FIRME for m in marcas)


def ler_voo(contrato):
    """Um FlightContract -> segmento no mesmo formato dos outros leitores.

    Devolve tambem `revisada`: quando a companhia mexeu no horario, ela publica
    revisedTime e o scheduledTime continua o original. E o revisedTime que
    interessa comparar contra o CRM.
    """
    if not isinstance(contrato, dict):
        return None

    partida = contrato.get("departure") or {}
    chegada = contrato.get("arrival") or {}

    data_prev, hora_prev = _instante(partida.get("scheduledTime"))
    data_rev, hora_rev = _instante(partida.get("revisedTime"))
    _, hora_chegada = _instante(chegada.get("revisedTime")) if data_rev \
        else _instante(chegada.get("scheduledTime"))

    return {
        "numero_voo": (contrato.get("number") or "").strip(),
        "origem": _iata(partida),
        "destino": _iata(chegada),
        # o horario que vale hoje: revisado se existir, senao o previsto
        "data": data_rev or data_prev,
        "partida": hora_rev or hora_prev,
        "chegada": hora_chegada,
        "status": contrato.get("status") or None,
        "revisada": bool(hora_rev and hora_rev != hora_prev),
        "prevista": hora_prev,
        "horario_firme": _horario_firme(partida),
    }


def ler_resposta(resposta):
    """Resposta da API (array de FlightContract) -> leitura padrao do sistema.

    O endpoint devolve LISTA: um mesmo numero de voo numa data pode trazer mais
    de uma perna, e codeshare aparece repetido.
    """
    leitura = {"encontrada": False, "segmentos": [], "segmentos_nao_expandidos": 0,
               "confiavel": False, "motivo": None, "status_pedido": None}
    if not isinstance(resposta, list) or not resposta:
        # 204 / lista vazia NAO e voo cancelado. Pode ser data fora da
        # cobertura do plano. Confundir os dois transformaria voo de outubro em
        # alarme de cancelamento.
        leitura["motivo"] = "a malha nao tem esse voo nessa data"
        return leitura

    segmentos = [s for s in (ler_voo(c) for c in resposta) if s]
    if not segmentos:
        leitura["motivo"] = "resposta em formato inesperado"
        return leitura

    leitura["encontrada"] = True
    leitura["segmentos"] = segmentos
    leitura["status_pedido"] = segmentos[0].get("status")
    return leitura


def escolher(leitura, voo_crm):
    """Qual dos voos devolvidos e o do CRM? Devolve (segmento, motivo).

    Necessario porque a resposta e lista. Casa por rota quando os dois lados
    tem IATA; com um unico voo na resposta, aceita sem exigir rota - senao voo
    sem IATA publicado nunca seria conferido.
    """
    segmentos = leitura.get("segmentos") or []
    if not segmentos:
        return None, "a malha nao tem esse voo nessa data"

    origem = (voo_crm.get("origem") or "").upper()
    destino = (voo_crm.get("destino") or "").upper()

    exatos = [s for s in segmentos
              if s.get("origem") == origem and s.get("destino") == destino]
    if len(exatos) == 1:
        return exatos[0], None
    if exatos:
        return exatos[0], None

    # nenhuma perna casa a rota do CRM
    if len(segmentos) == 1:
        return segmentos[0], None
    return None, "a malha devolveu %d pernas e nenhuma casa a rota do CRM" % len(segmentos)


def confiavel(segmento):
    """A leitura pode sustentar alerta de horario? (pode, motivo)

    Regra da casa: na duvida o sistema cala a boca.
    """
    if not segmento.get("data") or not segmento.get("partida"):
        return False, "a malha nao publicou horario de partida"
    if not segmento.get("horario_firme"):
        return False, "horario apenas estimado pela malha"
    return True, None


def achados_de_status(segmento, voo_crm):
    """Status da malha -> alertas. Independe de o horario ter sido lido.

    Cancelamento e um valor de enum, nao texto solto: nao depende de o parser
    ter acertado a estrutura, entao passa mesmo com leitura nao confiavel.
    Silenciar cancelamento por cautela e pior que o alarme falso que a cautela
    evita.
    """
    achados = []
    status = segmento.get("status")

    if status == CANCELADO:
        achados.append({
            "tipo": "trecho_cancelado",
            "voo_crm": voo_crm,
            "detalhe": "a malha da companhia marca %s de %s como cancelado" % (
                segmento.get("numero_voo") or "?", segmento.get("data") or "?"),
        })
    elif status == CANCELAMENTO_INCERTO:
        achados.append({
            "tipo": "possivel_cancelamento",
            "voo_crm": voo_crm,
            "detalhe": "a malha marca %s como possivelmente cancelado "
                       "(confirmar com a companhia)" % (
                           segmento.get("numero_voo") or "?"),
        })
    elif status == DESVIADO:
        achados.append({
            "tipo": "voo_desviado",
            "voo_crm": voo_crm,
            "detalhe": "a malha marca %s como desviado para outro destino" % (
                segmento.get("numero_voo") or "?"),
        })
    elif status == ATRASADO:
        achados.append({
            "tipo": "atraso",
            "voo_crm": voo_crm,
            "detalhe": "a malha marca %s como atrasado" % (
                segmento.get("numero_voo") or "?"),
        })

    # So sustenta o alerta com horario FIRME (Basic/Live). A malha publica
    # revisedTime tambem quando o horario ainda e estimativa (quality
    # Approximate por exemplo) - sem este filtro, todo voo com previsao
    # oscilando um pouco viraria "alterado pela companhia" sem a companhia
    # ter mexido em nada. Mesma regra que malha.confiavel() ja aplica para
    # horario_alterado/data_alterada; faltava aqui.
    if segmento.get("revisada") and segmento.get("horario_firme"):
        achados.append({
            "tipo": "alterado_pela_companhia",
            "voo_crm": voo_crm,
            "detalhe": "a companhia revisou o horario publicado: %s -> %s" % (
                segmento.get("prevista") or "?", segmento.get("partida") or "?"),
        })
    return achados
