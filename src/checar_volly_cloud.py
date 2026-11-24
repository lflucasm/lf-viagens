"""Checagem pelo "Monitorar voo" da Volly (aba Voos), 100% na nuvem - roda
no GitHub Actions, junto com a malha, sem o Mac ligado.

O que o botao faz (descoberto em 25/09/2026 lendo o bundle do site):
chama a edge function `flight-status` com o id do trecho (reminders.id). A
Volly consulta a AeroDataBox - a MESMA API da nossa malha, so que na cota
DELA - e guarda o resultado em tres tabelas do Supabase deles:

    flight_status_snapshots .. ultima leitura por (numero, data), com a
                               resposta crua em `raw`. Cache GLOBAL: sem
                               organization_id, qualquer agencia que clicar
                               no mesmo voo atualiza a linha pra todo mundo.
    flight_status_changes .... o diff entre duas leituras (portao, terminal,
                               status...). Nao usamos: a comparacao e feita
                               aqui, contra a nossa propria baseline.
    flight_status_lookups .... quem clicou quando (por organizacao).

Nao e monitor automatico - so atualiza quando alguem clica. Por isso este
script clica por nos, de hora em hora (checar-volly-cloud.yml): para cada
voo elegivel (ativo, futuro, sem `incompleto`) cuja leitura da Volly venceu
(10h, ou 4h se embarca em menos de 24h), mais proximo primeiro, dentro do
orcamento da rodada (60% do teto DIARIO da Volly, 30 reais/dia, menos o que a
organizacao ja consultou hoje; no maximo 6 reais por rodada), chama a edge function com
force=true. A lista de voos vem da ingestao (ingestao_cloud.py). Depois
le os snapshots (inclusive os que outras agencias atualizaram) e passa o
`raw` pelo mesmo caminho da malha (checar_malha_cloud.processar_contratos),
com origem propria - baseline, historico e Telegram separados da malha.
Cada rodada grava batimento `monitor-volly` (chamadas, orcamento, voos sem
leitura e o motivo, `erro_login` se o token da Volly caiu).

Sincronia com a malha: checar_malha_cloud.py pula voo que esta origem leu ha
menos de 12h (ver HORAS_COBERTO_PELA_VOLLY la), entao a cota AeroDataBox
nossa sobra pro que a Volly nao cobre - voo noturno, que a edge function
deles nao acha (monta a data em UTC; ver milhasflow.consultar_status_voo).

Alerta (modo real, desde 26/09/2026): cancelamento/atraso/desvio, horario
ou rota mudou desde a ultima leitura, voo mudou de data, e horario da venda
diferente do da companhia - cada fato distinto alerta uma vez so.

Simulacao (--plano): faz as chamadas e le tudo de verdade, mas grava a
baseline numa origem separada (ORIGEM_PLANO, que a malha ignora), nao grava
batimento e em vez de alertas manda so um resumo no Telegram.

Uso:
    python3 src/checar_volly_cloud.py                # rodada real
    python3 src/checar_volly_cloud.py --plano        # simulacao
    python3 src/checar_volly_cloud.py --passivo      # nao clica, so le cache
    python3 src/checar_volly_cloud.py --limite 5
    python3 src/checar_volly_cloud.py --loc PNR      # so essa reserva, forcando
                                                     # (fora do orcamento do robo)
    python3 src/checar_volly_cloud.py --carga-inicial
        # rodada real, mas no Telegram vai UM resumo ("N alteracoes ja
        # existentes - ver aba Urgente") em vez da lista; rodar uma vez so,
        # ao ligar o fluxo (spec, parte 3: ~23 divergencias ja existiam)
"""

import html
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import batimento
import checar_malha_cloud
import comparacao
import fusos
import nuvem_comum
import ritmo_humano
from checar_latam_cloud import MilhasFlowConfig, autenticar_volly
from milhasflow import MilhasFlow

ORIGEM = checar_malha_cloud.ORIGEM_VOLLY
ORIGEM_PLANO = ORIGEM + "-plano"

ETAPA = "monitor-volly"

# Intervalo minimo entre leituras da Volly por voo (spec do fluxo na nuvem,
# 26/09/2026): 10h, ou 4h se o embarque e nas proximas 24h. Com a rodada de
# hora em hora, so entra quem venceu - e substituiu a cadencia por faixa
# (3/6/12/24h) de antes, que nao cabia no teto por hora da Volly.
HORAS_VENCIMENTO = 10
HORAS_VENCIMENTO_PERTO = 4
HORAS_EMBARQUE_PERTO = 24
PAUSA_ENTRE_CHAMADAS_S = 1.0

# Teto da flight-status ("Monitorar voo"): 30 consultas REAIS por DIA por
# agencia ("A agencia ja fez as 30 consultas de voo de hoje. Amanha libera de
# novo."), medido em 24/11/2026 - o robo gastava as 30 em 3 min logo apos as
# 07h, todo dia, e a equipe ficava sem o botao o resto do dia. (Em 27/09 se
# achava que eram 120 por hora.) Resposta do cache da Volly (`cache_hit` /
# `fromCache`) nao conta - nem com force. O dia vira na meia-noite de Brasilia.
LIMITE_VOLLY_DIA = 30
# O teto e o MESMO do botao da equipe: o robo (e quem ja consultou hoje, equipe
# inclusa) fica com no maximo 60% dele = 18; os outros 12 sao da equipe.
FOLGA_EQUIPE = 0.4
# Teto de consultas reais por rodada: com o ciclo de hora em hora, as 18 do dia
# se espalham em vez de acabar nas primeiras rodadas (voo que fica urgente a
# tarde ainda acha orcamento). Cache da Volly nao entra na conta.
MAX_REAIS_POR_RODADA = 6

SINAIS_DE_LIMITE = ("limite de consultas", "consultas de voo de hoje")

# Quantos voos sem leitura vao nominalmente no batimento (o resto so conta)
MAX_LISTA_SEM_LEITURA = 30


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def vencido(idade, horas_ate_embarque):
    """A leitura da Volly deste voo precisa ser renovada?

    Desde 28/09/2026 a validade da leitura depende da proximidade do embarque
    (ritmo_humano.VENCIMENTO_POR_FAIXA: 4h/10h/16h/30h) - o monitor consulta
    no ritmo de uma pessoa e voo distante nao precisa de duas leituras por dia.
    `idade`: horas desde a ultima leitura (None = nunca leu).
    """
    return ritmo_humano.vencido(idade, horas_ate_embarque)


def orcamento_da_rodada(lookups_hoje, limite_dia=LIMITE_VOLLY_DIA):
    """Consultas REAIS que esta rodada pode fazer: 60% do teto do dia menos o
    que a organizacao (robo + equipe) ja consultou hoje. Nunca negativo."""
    return max(0, int(limite_dia * (1 - FOLGA_EQUIPE)) - int(lookups_hoje or 0))


def lookups_recentes(mf, horas=HORAS_VENCIMENTO, agora=None):
    """Consultas da organizacao na flight-status nas ultimas `horas`
    (robo + equipe), com numero e data - servem pro orcamento (so a ultima
    hora) e pra saber quando cada voo foi tentado (ultimas_tentativas)."""
    agora = agora or datetime.now(timezone.utc)
    desde = (agora - timedelta(hours=horas)).isoformat(timespec="seconds")
    return mf._buscar_tabela("flight_status_lookups", {
        "select": "flight_number,flight_date,created_at,cache_hit",
        "organization_id": "eq." + mf.cfg.organization_id,
        "created_at": "gte." + desde,
    })


def contar_hoje(lookups, agora=None):
    """Quantos lookups REAIS (`cache_hit = false`, so esses contam no teto da
    Volly) caem no dia de hoje, que vira na meia-noite de Brasilia."""
    agora = agora or datetime.now(timezone.utc)
    meia_noite = agora.astimezone(ritmo_humano.BRT).replace(hour=0, minute=0, second=0, microsecond=0)
    total = 0
    for l in lookups:
        if l.get("cache_hit"):
            continue
        idade = idade_horas(l.get("created_at"), agora)
        if idade is not None and agora - timedelta(hours=idade) >= meia_noite:
            total += 1
    return total


def ultimas_tentativas(lookups):
    """{(numero IATA, flight_date): created_at mais novo}.

    So consulta de verdade (cache_hit falso): clique da equipe servido do
    cache da Volly nao renova nada, e nao pode adiar a nossa consulta."""
    resultado = {}
    for l in lookups:
        if l.get("cache_hit"):
            continue
        chave = (comparacao._normaliza_voo(l.get("flight_number") or ""), l.get("flight_date"))
        if (l.get("created_at") or "") > resultado.get(chave, ""):
            resultado[chave] = l["created_at"]
    return resultado


def idade_da_tentativa(tentativas, numero, data_local, agora=None):
    """Horas desde a ultima consulta deste voo na Volly, achando ou nao.

    Voo que a Volly nao encontra (noturno, pelo bug de data em UTC deles)
    nunca ganha snapshot - sem isto ele seria "nunca lido" e gastaria uma
    chamada do orcamento em TODA rodada de hora em hora. A Volly registra o
    flight_date que ela montou (as vezes o dia seguinte, em UTC), entao
    confere os dois.
    """
    try:
        seguinte = (datetime.strptime(data_local, "%Y-%m-%d")
                    + timedelta(days=1)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        seguinte = None
    idades = [idade_horas(tentativas.get((numero, d)), agora)
              for d in (data_local, seguinte) if d]
    idades = [i for i in idades if i is not None]
    return min(idades) if idades else None


def idade_efetiva(idade_leitura, idade_tentativa):
    """A mais recente entre a leitura (fetched_at) e a ultima tentativa."""
    validas = [i for i in (idade_leitura, idade_tentativa) if i is not None]
    return min(validas) if validas else None


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def motivo_do_erro(erro):
    """Erro da flight-status -> motivo de "sem leitura" do batimento."""
    texto = _sem_acento(erro)
    if any(sinal in texto for sinal in SINAIS_DE_LIMITE):
        return "limite"
    if "trecho" in texto and "encontrado" in texto:
        return "trecho_nao_encontrado"
    if "encontrado" in texto:
        return "nao_encontrado"
    return "erro"


# Numero IATA que a Volly entende: cia de 2 caracteres (ao menos uma letra:
# G3, LA, 2Z) + ate 4 digitos. O que sobra disso depois de numero_iata (cia
# ICAO desconhecida, so digitos sem cia) nao acha snapshot nenhum - nem
# adianta gastar chamada.
NUMERO_CHECAVEL = re.compile(r"^([A-Z][A-Z0-9]|\d[A-Z])\d{1,4}$")


def numero_checavel(numero):
    return bool(NUMERO_CHECAVEL.match(numero or ""))


def ordem_de_embarque(grupos, dias_por_chave):
    """Embarque mais proximo primeiro - o corte do orcamento sempre sobra
    pros mais distantes, que esperam a proxima rodada."""
    return sorted(grupos, key=lambda g: (
        dias_por_chave.get(g[0]) if dias_por_chave.get(g[0]) is not None else 1e9,
        g[0][1], g[0][0]))


def idade_horas(texto_iso, agora=None):
    """Horas desde `fetched_at` (timestamptz da Volly). None se ilegivel."""
    if not texto_iso:
        return None
    try:
        # Python 3.10 nao aceita fracao com 1-5 digitos nem "Z"
        texto = texto_iso.replace("Z", "+00:00")
        m = re.match(r"^(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(.*)$", texto)
        if m and m.group(2):
            texto = "%s.%s%s" % (m.group(1), m.group(2)[:6].ljust(6, "0"), m.group(3))
        instante = datetime.fromisoformat(texto)
    except ValueError:
        return None
    agora = agora or datetime.now(timezone.utc)
    return (agora - instante).total_seconds() / 3600


# A Volly guarda o numero no padrao IATA (UV12WX); o CRM as vezes tem o
# prefixo ICAO (GLO1306) ou so o numero (1306, com a cia em outro campo).
# (a normalizacao mora em comparacao.numero_iata, que a malha tambem usa)
ICAO_PARA_IATA = comparacao._ICAO_PARA_IATA
CIA_PARA_IATA = comparacao.CIA_PARA_IATA
numero_iata = comparacao.numero_iata


def chave_normal(chave, voos_crm=None):
    numero, data = chave
    cia = (voos_crm or [{}])[0].get("cia")
    return (numero_iata(numero, cia), data)


def snapshots_por_numero(mf, grupos):
    """{numero IATA: [snapshot, ...]} - todas as datas, mais novo primeiro."""
    numeros = [chave_normal(chave, voos_crm)[0] for chave, voos_crm in grupos]
    resultado = {}
    for s in mf.buscar_snapshots_voo(numeros):
        resultado.setdefault(comparacao._normaliza_voo(s["flight_number"]), []).append(s)
    for lista in resultado.values():
        lista.sort(key=lambda s: s.get("fetched_at") or "", reverse=True)
    return resultado


def _data_local_partida(contrato):
    local = ((contrato.get("departure") or {}).get("scheduledTime") or {}).get("local") or ""
    return local[:10]


def leitura_do_dia(snaps_do_numero, data_local):
    """(contratos, fetched_at) do voo que parte em `data_local`, ou (None, None).

    Nao da pra confiar em flight_date: a Volly pede a AeroDataBox numa janela
    e o `raw` de uma data traz tambem a perna da vespera a noite (LA3252 de
    27/09 veio com a de 26/09 20h40 junto, 25/09/2026) - sem este filtro a
    malha.escolher pega a perna errada e acusa "data alterada" falsa. Por
    isso junta o raw de TODOS os snapshots do numero e fica so com o que
    parte no dia local do CRM, da leitura mais nova pra mais velha.
    """
    for snap in snaps_do_numero or []:
        contratos = [c for c in (snap.get("raw") or [])
                     if isinstance(c, dict) and _data_local_partida(c) == data_local]
        if contratos:
            return contratos, snap.get("fetched_at")
    return None, None


# Diferenca minima entre o horario da venda e o da companhia pra virar
# alerta - abaixo disso e arredondamento de quem digitou a venda.
MINUTOS_DIVERGENCIA_VENDA = 5


def _minutos(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def perna_da_venda(contratos, voo_crm):
    """Entre varias pernas do mesmo dia, a da venda: mesma rota do CRM e
    horario programado mais perto do vendido.

    malha.escolher fica com a PRIMEIRA que casa a rota - com duas pernas no
    dia (G3 1220 CGH-MCZ em 23/12 trouxe 21:55 e 22:05) isso acusava
    divergencia de horario falsa.
    """
    if len(contratos) < 2:
        return contratos
    origem = (voo_crm.get("origem") or "").upper()
    destino = (voo_crm.get("destino") or "").upper()
    mesma_rota = [c for c in contratos
                  if ((c.get("departure") or {}).get("airport") or {}).get("iata") == origem
                  and ((c.get("arrival") or {}).get("airport") or {}).get("iata") == destino]
    candidatos = mesma_rota or contratos
    vendido = _minutos((voo_crm.get("embarque_local") or "")[11:16])
    if vendido is None:
        return candidatos

    def distancia(c):
        local = ((c.get("departure") or {}).get("scheduledTime") or {}).get("local") or ""
        m = _minutos(local[11:16])
        return abs(m - vendido) if m is not None else 24 * 60

    return [min(candidatos, key=distancia)]


def divergencia_venda(segmento, voos_crm):
    """Horario da venda (CRM) x horario PROGRAMADO da companhia.

    E o "Horario da venda nao bate com a companhia" da tela da Volly. O resto
    do sistema compara so contra a leitura anterior da propria fonte (ver
    comparacao.comparar - CRM nao e fonte confiavel de horario), mas o que
    a venda diz e justamente o que o passageiro tem em maos: se a companhia
    diz outra coisa, alguem precisa avisar. Repetir todo dia o mesmo erro de
    digitacao (o motivo daquela regra) quem evita e o dedupe de
    nuvem_comum.gravar_achado - cada divergencia distinta alerta uma vez so.

    So com horario firme (malha.confiavel), senao estimativa oscilando vira
    alerta.

    Rota diferente da venda vira "passageiro_remanejado" (com os dois
    horarios no detalhe) em vez de "horario nao bate": o horario diferente
    e consequencia, nao o fato (TSTABX, 23/10/2026 - ver
    comparacao.trecho_diferente_da_venda).
    """
    achados = comparacao.trecho_diferente_da_venda(segmento, voos_crm)
    remanejados = {a["voo_crm"].get("id") for a in achados}
    if not segmento.get("horario_firme") or not segmento.get("prevista"):
        return achados
    companhia = segmento["prevista"]
    for voo in voos_crm:
        if voo.get("id") in remanejados:
            continue
        venda = (voo.get("embarque_local") or "")[11:16]
        a, b = _minutos(venda), _minutos(companhia)
        if a is None or b is None or abs(a - b) < MINUTOS_DIVERGENCIA_VENDA:
            continue
        achados.append({
            "tipo": "horario_venda_diverge",
            "voo_crm": voo,
            "detalhe": "na venda %s %s -> na companhia %s" % (
                (voo.get("embarque_local") or "")[:10], venda, companhia),
        })
    return achados


def leitura_de_outro_dia(snaps_do_numero, data_local, agora=None):
    """Voo que a companhia NAO opera no dia da venda.

    Quando nenhuma perna parte em `data_local` (leitura_do_dia deu None), mas
    uma leitura RECENTE da Volly pedida pra esse mesmo dia (flight_date igual
    ou no dia seguinte - a Volly monta a data meio em UTC) so trouxe pernas de
    outro dia: a companhia moveu o voo de data, ou a venda foi digitada no
    dia errado. Devolve esses contratos pra comparacao acusar "data_alterada"
    - sem isto o voo so sumia calado em "sem leitura".

    Voo diario (CD56EF CNF-NAT) traz a perna do proprio dia junto e nunca cai
    aqui - e exatamente o falso "24h antes" que a tela da Volly mostra pra
    TSTAQX em 26/09/2026 (ela compara com a perna da vespera).
    """
    try:
        dia = datetime.strptime(data_local, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    pedidos = {data_local, (dia + timedelta(days=1)).strftime("%Y-%m-%d")}
    for snap in snaps_do_numero or []:
        if snap.get("flight_date") not in pedidos:
            continue
        idade = idade_horas(snap.get("fetched_at"), agora)
        if idade is None or idade > 24:
            continue
        contratos = [c for c in (snap.get("raw") or []) if isinstance(c, dict)]
        if contratos and not any(_data_local_partida(c) == data_local for c in contratos):
            return contratos
    return None


# Status que a Volly grava no snapshot quando a AeroDataBox nao acha o voo no
# trecho vendido (raw vem nulo). Segundo o proprietário (17/10/2026), nesse status o
# voo mudou e precisa de atencao: ate entao caia em "sem leitura" calado
# (GOL 1885 REC-GIG de 31/10, TSTACX, e outros 10 voos).
STATUS_SEM_VOO_NO_TRECHO = "SemVooNoTrecho"
# Leitura mais velha que isso pode ja ter sido refeita pela companhia; o
# monitor renova antes (validade de 4h a 30h), entao so sobra snapshot parado.
HORAS_MAX_SEM_VOO = 48


def sem_voo_no_trecho(snaps_do_numero, data_local, voos_crm, agora=None):
    """Achados "sem_voo_no_trecho" - um por trecho do CRM - quando a leitura
    da Volly pra (numero, data local) diz que nao ha voo no trecho.

    So vale snapshot pedido pra propria data e recente. Detalhe estavel
    (rota + data), pro dedupe de nuvem_comum.gravar_achado alertar uma vez.
    """
    for snap in snaps_do_numero or []:
        if snap.get("status") != STATUS_SEM_VOO_NO_TRECHO or snap.get("flight_date") != data_local:
            continue
        idade = idade_horas(snap.get("fetched_at"), agora)
        if idade is None or idade > HORAS_MAX_SEM_VOO:
            continue
        return [{
            "tipo": "sem_voo_no_trecho",
            "voo_crm": voo,
            "detalhe": "a Volly nao achou o voo no trecho %s-%s em %s" % (
                voo.get("origem") or "?", voo.get("destino") or "?", data_local),
        } for voo in voos_crm]
    return []


def reminders_por_chave(mf):
    """{(numero normalizado, data local): [reminder id, ...]} direto da Volly.

    Nao da pra usar voos.id do painel como reminderId: o painel e espelho do
    que o Mac sincronizou por ultimo, e trecho recriado na Volly muda de id -
    a edge function responde "Trecho nao encontrado" (visto com G3 2029 em
    25/09/2026). Casa pelo mesmo (numero, data local) de voos_ativos.
    """
    resultado = {}
    for r in mf.buscar_voos(so_com_emissao=False):
        if not r.get("flight_number") or not r.get("departure_datetime"):
            continue
        local = fusos.texto_local(
            fusos.volly_para_utc(r["departure_datetime"], r.get("departure_airport")),
            r.get("departure_airport"))
        chave = (numero_iata(r["flight_number"], r.get("airline")), (local or "")[:10])
        resultado.setdefault(chave, []).append(r["id"])
    return resultado


def resumo_simulacao(lidos, chamadas, sem_cobertura, achados):
    linhas = ["🧪 <b>Monitor Volly — simulação %s</b>" % datetime.now().strftime("%d/%m %H:%M"),
              "",
              "Voos lidos: %d · chamadas à Volly: %d · sem cobertura: %d"
              % (lidos, chamadas, sem_cobertura)]
    if not achados:
        linhas += ["", "Nenhum alerta seria enviado."]
    else:
        linhas += ["", "<b>Alertas que seriam enviados (%d):</b>" % len(achados)]
        for a in achados[:25]:
            voo = a["voo_crm"]
            linhas.append("• %s %s [%s] %s" % (
                html.escape(voo.get("localizador") or "?"),
                html.escape(voo.get("numero_voo") or "?"),
                html.escape(a["tipo"]), html.escape(a["detalhe"][:90])))
        if len(achados) > 25:
            linhas.append("… e mais %d" % (len(achados) - 25))
    return "\n".join(linhas)


# Folga do token antes de uma sessao humana: sessao (ate 45 min) + atraso
# inicial (ate 6 min) + leitura final. So pra --so-token (sessao manual fora
# da fila milhasflow-auth); a rodada agendada em rajada roda dentro da fila
# e renova normalmente.
FOLGA_TOKEN_SESSAO_S = 55 * 60


def main():
    if "--so-token" in sys.argv:
        _obrigatorio("SUPABASE_WEB_URL")
        mf = MilhasFlow(MilhasFlowConfig())
        expira = mf.garantir_token(FOLGA_TOKEN_SESSAO_S)
        print("token da Volly valido ate %s" % datetime.fromtimestamp(
            expira, timezone.utc).isoformat(timespec="seconds"))
        return
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    plano = "--plano" in sys.argv
    passivo = "--passivo" in sys.argv
    carga_inicial = "--carga-inicial" in sys.argv
    humano = "--humano" in sys.argv
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}

    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")

    fusos.carregar_aprendidos(supabase_url, service_key)
    mf = MilhasFlow(MilhasFlowConfig())

    if plano:
        # sem batimento: simulacao nao pode contar pro supervisor como
        # monitor que rodou (mesma regra de ingestao_cloud.py) - o detalhe
        # que seria gravado sai so no log
        b = batimento.Rodada()
        rodar(mf, supabase_url, service_key, b, limite, plano, passivo, so_esses,
              humano=humano)
        print("\nBatimento que seria gravado: lidos=%d alertas=%d falhas=%d\n%s" % (
            b.lidos, b.alertas, b.falhas, b.detalhe))
        return
    with batimento.rodada(supabase_url, service_key, ETAPA) as b:
        rodar(mf, supabase_url, service_key, b, limite, plano, passivo, so_esses,
              carga_inicial, humano=humano)


def rodar(mf, supabase_url, service_key, b, limite, plano, passivo, so_esses,
          carga_inicial=False, humano=False):
    """A rodada em si. `b` (batimento.Rodada) recebe lidos/alertas/falhas e
    o detalhe que o supervisor le (chamadas, orcamento, sem leitura...)."""
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    # 330 dias: o custo e so chamada na Volly (voo distante reclica a cada
    # 10h), e voo vendido com 6+ meses de antecedencia tambem muda
    horizonte = int(os.environ.get("VOLLY_DIAS", "330"))
    origem = ORIGEM_PLANO if plano else ORIGEM

    autenticar_volly(mf, b.detalhe)

    # A lista de voos vem pronta da ingestao (ingestao_cloud.py, a cada 2h) -
    # ate 26/09/2026 ela rodava aqui dentro.
    grupos, fora, dias_por_chave, incompletos = checar_malha_cloud.voos_ativos(
        supabase_url, service_key, horizonte)
    print("Voos elegiveis no horizonte ... %d" % len(grupos))
    if fora:
        print("Fora do horizonte (%d dias) ... %d" % (horizonte, fora))
    if incompletos:
        print("Incompletos (nao checaveis) ... %d" % incompletos)
    if so_esses:
        grupos = [(chave, voos_crm) for chave, voos_crm in grupos
                  if any((v.get("localizador") or "").upper() in so_esses for v in voos_crm)]
        if not grupos:
            print("Nenhum localizador bate com %s" % ", ".join(sorted(so_esses)))
            sys.exit(1)
    grupos = ordem_de_embarque(grupos, dias_por_chave)
    if limite is not None:
        grupos = grupos[:limite]

    # 1) clicar "Monitorar voo" onde a leitura da Volly venceu
    snaps = snapshots_por_numero(mf, grupos)
    chamadas = 0
    reais = 0             # so as consultas fora do cache gastam o teto da Volly
    limite_batido = False
    motivos = {}          # chave -> por que nao ha leitura nova (se faltar)
    orcamento = lookups = None
    if not passivo:
        recentes = lookups_recentes(mf)
        tentativas = ultimas_tentativas(recentes)
        lookups = contar_hoje(recentes)
        orcamento = min(orcamento_da_rodada(lookups), MAX_REAIS_POR_RODADA)
        print("Consultas reais da org hoje %d -> orcamento da rodada %d%s" % (
            lookups, orcamento, " (ignorado com --loc)" if so_esses else ""))
        reminders = reminders_por_chave(mf)

        # quem precisa de leitura nova, com o motivo de quem nao da pra consultar
        fila = []
        for chave, voos_crm in grupos:
            numero, data = chave_normal(chave, voos_crm)
            if not numero_checavel(numero):
                motivos[chave] = "numero_incompleto"
                continue
            # conexao digitada num trecho so ("TP1930 + TP1928"): a Volly nao
            # entende o numero composto e responderia erro toda hora. Quem
            # cobre o primeiro voo e a malha.
            if any("+" in (v.get("numero_voo") or "") for v in voos_crm):
                motivos[chave] = "composto_so_malha"
                continue
            _, visto = leitura_do_dia(snaps.get(numero), data)
            idade = idade_efetiva(idade_horas(visto),
                                  idade_da_tentativa(tentativas, numero, data))
            dias = dias_por_chave.get(chave)
            horas = dias * 24 if dias is not None else None
            if not so_esses and not vencido(idade, horas):
                continue
            ids = reminders.get((numero, data))
            if not ids:
                print("  %s %s  trecho nao encontrado na Volly" % (chave[0], chave[1]))
                motivos[chave] = "trecho_nao_encontrado"
                continue
            fila.append({"chave": chave, "reminder": ids[0], "idade": idade, "horas": horas})

        # Ritmo de pessoa (pedido do proprietário, 28/09/2026 - ver ritmo_humano.py):
        # sessao de 20-45 min, uma consulta por vez com pausa irregular,
        # quase nada de madrugada. Desde 15/10/2026 a rodada agendada e sem
        # --humano (rajada, pedido do proprietário): a sessao de 20-45 min dormindo
        # no runner estourou a cota de minutos do GitHub Actions. --humano
        # segue no disparo manual. --loc (botao da equipe) e sem --humano
        # consultam direto, sem pausa longa.
        rng = random.Random()
        sessao = None
        if humano and not so_esses:
            sessao = ritmo_humano.plano_da_sessao(rng, datetime.now(timezone.utc))
            b.detalhe["sessao"] = {k: (round(v) if isinstance(v, float) else v)
                                   for k, v in sessao.items()}
            if not sessao["ativa"]:
                print("Sem sessao de consulta agora (%s) - so leitura do que ja existe"
                      % sessao["motivo"])
                for item in fila:
                    motivos[item["chave"]] = "fora_da_sessao"
                fila = []
            else:
                if sessao["so_urgentes"]:
                    fila = [f for f in fila if f["horas"] is not None
                            and f["horas"] < ritmo_humano.HORAS_URGENTE]
                fila = ritmo_humano.ordem_humana(fila, rng, lambda f: f["horas"])
                print("Sessao humana: ate %.0f min, %d voo(s) vencido(s), inicio em %.0fs" % (
                    sessao["duracao_s"] / 60, len(fila), sessao["atraso_inicial_s"]))
                if fila and not plano:
                    time.sleep(sessao["atraso_inicial_s"])
        inicio = time.time()
        pausas = []

        for i, item in enumerate(fila, 1):
            chave = item["chave"]
            # --loc e o botao "checar agora" da equipe: usa a folga dela, entao
            # nao respeita o orcamento do robo - so a parada da propria Volly
            if limite_batido or (not so_esses and reais >= orcamento):
                motivos[chave] = "limite"
                continue
            if sessao and sessao.get("maximo") is not None and chamadas >= sessao["maximo"]:
                motivos[chave] = "fora_da_sessao"
                continue
            if sessao and chamadas:
                espera = ritmo_humano.pausa(rng)
                if time.time() - inicio + espera > sessao["duracao_s"]:
                    motivos[chave] = "fora_da_sessao"
                    continue
                pausas.append(round(espera))
                if not plano:
                    time.sleep(espera)
            print("[%d/%d] %s %s  consultando (leitura/tentativa %s)" % (
                i, len(fila), chave[0], chave[1],
                "de %.0fh" % item["idade"] if item["idade"] is not None else "inexistente"))
            # igual ao botao do site: sem "forcar". So forca quando a Volly
            # devolve cache mais velho que a validade da leitura deste voo.
            resposta, erro = mf.consultar_status_voo(item["reminder"], forcar=bool(so_esses))
            chamadas += 1
            if not erro and not (resposta or {}).get("fromCache"):
                reais += 1
            if not erro and not so_esses and (resposta or {}).get("fromCache"):
                idade_cache = idade_horas((resposta or {}).get("updatedAt"))
                if idade_cache is None or idade_cache >= ritmo_humano.horas_de_validade(item["horas"]):
                    # rajada (agendada desde 15/10/2026) nao espera: a pausa
                    # de pessoa so vale dentro de uma sessao humana
                    if not plano:
                        time.sleep(rng.uniform(15, 45) if sessao else PAUSA_ENTRE_CHAMADAS_S)
                    resposta, erro = mf.consultar_status_voo(item["reminder"], forcar=True)
                    chamadas += 1
                    if not erro and not (resposta or {}).get("fromCache"):
                        reais += 1
            if erro:
                print("       %s" % erro)
                motivos[chave] = motivo_do_erro(erro)
                if motivos[chave] == "limite":
                    limite_batido = True
                    print("       limite da Volly - o resto fica pra proxima rodada")
            elif not sessao:
                time.sleep(PAUSA_ENTRE_CHAMADAS_S)
        if sessao:
            b.detalhe["sessao"]["pausas_s"] = pausas
            b.detalhe["sessao"]["duracao_real_s"] = round(time.time() - inicio)
        if chamadas:
            snaps = snapshots_por_numero(mf, grupos)

    # 2) ler o que a Volly tem e comparar pelo mesmo caminho da malha
    baseline = checar_malha_cloud.observado_antes(supabase_url, service_key, origem)
    do_pdf = nuvem_comum.links_pdf_do_supabase(supabase_url, service_key)

    ok = falhas = 0
    sem_leitura = []
    alertas_para_enviar = []
    for chave, voos_crm in grupos:
        numero, data = chave_normal(chave, voos_crm)
        contratos, visto = leitura_do_dia(snaps.get(numero), data)
        if not contratos:
            contratos = leitura_de_outro_dia(snaps.get(numero), data)
            if not contratos:
                achados = sem_voo_no_trecho(snaps.get(numero), data, voos_crm)
                if not achados:
                    sem_leitura.append((chave, voos_crm, motivos.get(chave, "sem_snapshot")))
                    continue
                print("%s %s  (Volly: sem voo no trecho)" % chave)
                if plano:
                    alertas_para_enviar += achados
                else:
                    for a in achados:
                        item = nuvem_comum.gravar_achado(
                            supabase_url, service_key, a, origem, do_pdf)
                        if item:
                            alertas_para_enviar.append(item)
                continue
            print("%s %s  (Volly: nenhuma perna nesse dia)" % chave)
        else:
            print("%s %s  (Volly, lido ha %.0fh)" % (
                chave[0], chave[1], idade_horas(visto) or 0))
        try:
            # comparacao casa numero+data: "1306"/"GLO1306" do CRM contra
            # "G3 1306" da malha viraria "ausente" falso
            voos_iata = [dict(v, numero_voo=numero) for v in voos_crm]
            contratos = perna_da_venda(contratos, voos_crm[0])
            situacao, itens = checar_malha_cloud.processar_contratos(
                contratos, voos_iata, supabase_url, service_key, baseline, do_pdf,
                origem=origem, gravar_achados=not plano,
                achados_extras=divergencia_venda, visto_em=visto)
        except Exception as e:
            print("       erro inesperado: %s" % str(e)[:150])
            falhas += 1
            continue
        if situacao == "falha":
            falhas += 1
        elif situacao == "alerta":
            alertas_para_enviar += itens
        else:
            ok += 1

    lidos = len(grupos) - len(sem_leitura)
    b.lidos = lidos
    b.alertas = len(alertas_para_enviar)
    b.falhas = falhas
    b.detalhe.update(resumo_batimento(
        chamadas, orcamento, lookups, limite_batido, sem_leitura, incompletos))

    print("\n" + "=" * 62)
    print("  chamadas a Volly ............ %d%s" % (
        chamadas, "  (LIMITE DA VOLLY BATIDO)" if limite_batido else ""))
    print("  lidos do monitor Volly ...... %d" % lidos)
    print("  sem leitura na Volly ........ %d  (a malha cobre) %s" % (
        len(sem_leitura), b.detalhe["sem_leitura_por_motivo"] or ""))
    print("  conferidos sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d" % len(alertas_para_enviar))
    print("  falharam .................... %d" % falhas)
    print("=" * 62)

    if plano:
        ok_envio, erro = alertas.enviar_telegram(
            telegram_token, telegram_chat,
            resumo_simulacao(lidos, chamadas, len(sem_leitura), alertas_para_enviar))
        print("\n>>> Telegram (simulacao): %s" % ("enviado" if ok_envio else erro))
        return

    if carga_inicial:
        # tudo ja foi gravado como pendente (aparece na aba Urgente); no
        # Telegram so o resumo, e marca todos notificados
        enviado, motivo = nuvem_comum.enviar_resumo_carga_inicial(
            supabase_url, service_key, telegram_token, telegram_chat,
            alertas_para_enviar, ORIGEM, "Monitor Volly")
    else:
        enviado, motivo = nuvem_comum.enviar_alertas(
            supabase_url, service_key, telegram_token, telegram_chat,
            alertas_para_enviar, ORIGEM, "Voos com alteração (monitor Volly)", do_pdf)
    if enviado:
        print("\n>>> Telegram: enviado")
    elif enviado is False:
        print("\n>>> Telegram: %s" % motivo)


def resumo_batimento(chamadas, orcamento, lookups, limite_batido, sem_leitura,
                     incompletos=0):
    """detalhe do batimento `monitor-volly` (o supervisor le isto).

    `sem_leitura`: [(chave, voos_crm, motivo)] - motivo e um de
    nao_encontrado, numero_incompleto, composto_so_malha, trecho_nao_encontrado,
    limite, sem_snapshot (ou "erro" pra resposta que a Volly nao explicou).
    """
    por_motivo = {}
    for _, _, motivo in sem_leitura:
        por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
    return {
        "chamadas": chamadas,
        "orcamento": orcamento,
        "lookups_hoje": lookups,
        "limite_batido": bool(limite_batido),
        "incompletos": incompletos,
        "sem_leitura": len(sem_leitura),
        "sem_leitura_por_motivo": por_motivo,
        "sem_leitura_lista": [
            {"voo_ids": [v["id"] for v in voos_crm],
             "localizador": voos_crm[0].get("localizador"),
             "numero_voo": chave[0], "data": chave[1], "motivo": motivo}
            for chave, voos_crm, motivo in sem_leitura[:MAX_LISTA_SEM_LEITURA]],
    }


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("O monitor Volly (nuvem)", erro)
        sys.exit(1)
