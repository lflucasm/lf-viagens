"""Supervisor: o "agente mestre" do fluxo de monitoramento na nuvem (parte 5
do spec 2026-09-26). Roda no fim de cada ciclo (ciclo.yml) e so
LE o painel - batimentos, voos, historico, observacoes e propostas_volly.
Nao autentica na Volly nem consulta companhia nenhuma.

Existe por causa de 15 a 26/09/2026: a rodada do Mac ficou travada no
captcha da Volly e a lista de voos congelou por 11 dias sem ninguem notar.
Aqui cada etapa e conferida pelo batimento que ela grava; o que estiver
fora do esperado vira problema:

    problema = {"chave": "sup:...", "nivel": "vermelho"|"laranja"|"amarelo",
                "texto": "..."}

Problema novo -> Telegram na hora + linha em `supervisor_estado`; continua
aberto -> nada (nao repete); sumiu -> "normalizado" + apaga a linha. As
chaves sao prefixadas com `sup:` pra nao colidir com as flags do aviso
(`telegram_segurado`/`telegram_liberado`, fase 4).

Roda no fim de cada ciclo (ciclo.yml, desde 23/10/2026: a cada 2h das 07h
as 23h de Brasilia, nada de madrugada). Resumo diario na primeira rodada a
partir das 10h UTC (07h de Brasilia). A falta dele e o alarme de que o
proprio GitHub Actions parou.

Uso:
    python3 src/supervisor.py            # rodada real (Telegram + estado)
    python3 src/supervisor.py --plano    # avalia e imprime, sem Telegram nem escrita
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import batimento
import nuvem_comum
import qualidade
import ritmo_humano
import supabase_rest

ETAPA = "supervisor"
PREFIXO = "sup:"
CHAVE_RESUMO = "sup:resumo_diario"

ICONE_NIVEL = {"vermelho": "🔴", "laranja": "🟠", "amarelo": "🟡"}
ORDEM_NIVEL = {"vermelho": 0, "laranja": 1, "amarelo": 2}

# Etapas que autenticam na Volly: qualquer uma delas com erro de login e o
# refresh_token compartilhado (milhasflow_auth_state) que morreu - derruba
# todas de uma vez, por isso vermelho.
ETAPAS_VOLLY = ("ingestao", "monitor-volly", "portal-latam", "reconferencia", "aplicar-volly")

# Janela em que cada etapa agendada precisa ter rodado (ok ou nao), em horas.
# Conferida contra os crons NOMINAIS em 26/09/2026, mas o agendador do
# GitHub Actions deste repo atrasa e pula rodadas bem mais do que isso -
# revisao final de 27/09/2026 mediu, no historico real:
#   ingestao (cron 0 */2)  as vezes so roda a cada 5-7h (mover-crm, mesmo
#                          cron, tem o mesmo atraso)
#   monitor-volly (15 *)   chegou a rodar so 5-6x no dia inteiro
#   malha (0 10/0 21)      janela real de ate 15,3h entre rodadas OK
#   portal-latam (15 10/21) fila do milhasflow-auth atrasa ~5h
#   portal-gol/azul         mesma fila
# Janelas alargadas com folga generosa pra nao virar alarme falso todo dia -
# o supervisor serve pra pegar quando a etapa parou de verdade (dias), nao
# pra cobrar pontualidade do agendador de terceiro.
JANELA_ETAPA_H = {
    "malha": 20,
    "portal-latam": 20,
    "portal-gol": 20,
    "portal-azul": 30,
    "email-cias": 8,
}
JANELA_INGESTAO_OK_H = 8
JANELA_MONITOR_OK_H = 6
JANELA_LOGIN_H = 4

QUEDA_FUTUROS_MAX = 0.30           # futuros_ativos caiu mais que isso -> vermelho
RODADAS_MEDIA = 10                 # rodadas anteriores na media (queda / taxa de falha)
TAXA_FALHA_MIN = 0.30              # abaixo disso nunca e problema

# Prazo de cobertura acompanha a validade da leitura no ritmo de pessoa do
# monitor Volly (ritmo_humano.VENCIMENTO_POR_FAIXA, 28/09/2026: 4h/10h/16h/
# 30h conforme o embarque) mais uma folga - senao todo voo distante viraria
# "sem leitura" entre duas consultas normais.
def prazo_cobertura_h(horas_ate_embarque):
    validade = ritmo_humano.horas_de_validade(horas_ate_embarque)
    return validade + max(4, validade * 0.5)
LISTA_MAX = 15                     # voos listados no texto do problema

TELEGRAM_PENDENTE_MIN = 30
SEGURADO_AVISO_H = 1               # segurado pelo teto ha mais que isso -> amarelo
PROPOSTA_PRAZO_MIN = 10
PROPOSTA_JANELA_D = 3              # verificado mais velho que isso sai da conta

# Timestamps gravados antes de 26/09/2026 com `datetime.now() + "-03:00"` no
# runner UTC ficaram 3h no futuro. Instante mais de 5 min no futuro e tratado
# como esse bug (volta 3h) - assim um alerta antigo nao "some" da conta de
# atraso por 3h, e uma leitura antiga nao conta como mais nova do que e.
FOLGA_FUTURO = timedelta(minutes=5)
DESVIO_BUG_FUSO = timedelta(hours=3)

HORA_RESUMO_UTC = 10               # 07h America/Sao_Paulo (primeiro ciclo do dia)

# erro de auth no texto da excecao (detalhe.erro, gravado por batimento.rodada)
# quando a etapa nao marcou erro_login explicitamente - ex.: a ingestao
_ERRO_AUTH = re.compile(
    r"auth/v1|captcha|refresh.?token|invalid.?grant|already used|"
    r"login nao retornou|jwt expired|http 401", re.IGNORECASE)


# ------------------------------------------------------------ tempo

def _instante(texto):
    """ISO do PostgREST -> datetime com fuso. Python 3.9 nao aceita "Z" nem
    fracao de segundo com 1-5 digitos no fromisoformat, e o PostgREST devolve
    as duas coisas conforme o valor."""
    if not texto:
        return None
    if isinstance(texto, datetime):
        momento = texto
    else:
        s = str(texto).strip().replace(" ", "T", 1).replace("Z", "+00:00")
        if re.search(r"[+-]\d{2}$", s):
            s += ":00"          # "+00" curto, que o 3.9 tambem recusa
        m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", s)
        if m:
            fracao = (m.group(2) or "")[1:7]
            s = m.group(1) + ("." + fracao.ljust(6, "0") if fracao else "") + m.group(3)
        try:
            momento = datetime.fromisoformat(s)
        except ValueError:
            return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def _tolerante(texto, agora):
    """Como _instante, desfazendo o bug antigo do +3h (ver FOLGA_FUTURO)."""
    momento = _instante(texto)
    if momento is not None and momento > agora + FOLGA_FUTURO:
        momento -= DESVIO_BUG_FUSO
    return momento


def _horas(delta):
    return delta.total_seconds() / 3600.0


def _ha(momento, agora):
    """'ha 5h' / 'ha 40 min' pro texto do problema."""
    if momento is None:
        return "nunca"
    minutos = int((agora - momento).total_seconds() // 60)
    if minutos < 90:
        return "há %d min" % max(minutos, 0)
    if minutos < 48 * 60:
        return "há %dh" % (minutos // 60)
    return "há %d dias" % (minutos // (24 * 60))


def _desde(momento, agora):
    """'desde 26/09 22:37 (ha 5h)', ou a falta de batimento na janela lida."""
    if momento is None:
        return "há mais de 7 dias (nenhum batimento)"
    return "desde %s (%s)" % (_brt(momento), _ha(momento, agora))


def _brt(momento):
    """dd/mm HH:MM em Brasilia (UTC-3 fixo desde o fim do horario de verao)."""
    if momento is None:
        return "?"
    return (momento - timedelta(hours=3)).strftime("%d/%m %H:%M")


# ------------------------------------------------------------ leitura

def ler_dados(supabase_url, service_key, agora):
    """Tudo que avaliar() precisa, lido do painel com a service key.

    Janelas de leitura bem maiores que as das regras: o custo e pequeno
    (~150 voos, ~700 observacoes) e as medias precisam das rodadas antigas.
    """
    def sel(tabela, params):
        return supabase_rest.select(supabase_url, service_key, tabela, params)

    def iso(delta):
        return (agora - delta).isoformat(timespec="seconds")

    agora_iso = agora.isoformat(timespec="seconds")
    return {
        "batimentos": sel("batimentos", {
            "select": "id,etapa,inicio,fim,ok,lidos,alertas,falhas,detalhe",
            "inicio": "gte.%s" % iso(timedelta(days=7)),
            "order": "inicio.desc", "limit": "2000"}),
        "voos": sel("voos", {
            "select": "id,localizador,cia,numero_voo,origem,destino,embarque,incompleto,passageiros",
            "ativo": "eq.true", "embarque": "gt.%s" % agora_iso}),
        # sem filtro de data: o visto_em antigo pode estar +3h (bug) e uma
        # leitura de 26h atras ainda interessa pro motivo
        "observacoes": sel("observacoes", {"select": "voo_id,origem,visto_em"}),
        # alertas abertos (resumo) e pendentes de Telegram saem da mesma lista
        "historico": sel("historico", {
            "select": "id,voo_id,campo,origem,detectado_em,notificado,resolvido",
            "evento": "eq.alterado", "origem": "neq.milhasflow",
            "resolvido": "not.is.true"}),
        "verificados": sel("historico", {
            "select": "id,voo_id,campo,verificado_em",
            "verificado_em": "gte.%s" % iso(timedelta(days=PROPOSTA_JANELA_D + 1))}),
        "propostas": sel("propostas_volly", {
            "select": "id,historico_id,criado_em,status",
            "criado_em": "gte.%s" % iso(timedelta(days=PROPOSTA_JANELA_D + 1))}),
        "estado": sel("supervisor_estado", {"select": "chave,aberto_em,avisado_em,detalhe"}),
    }


def apagar_estado(supabase_url, service_key, chave):
    """DELETE numa linha de supervisor_estado (supabase_rest nao tem delete)."""
    req = urllib.request.Request(
        supabase_url.rstrip("/") + "/rest/v1/supervisor_estado?" + urllib.parse.urlencode(
            {"chave": "eq.%s" % chave}),
        method="DELETE",
        headers={"apikey": service_key, "Authorization": "Bearer " + service_key,
                 "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


# ------------------------------------------------------------ regras

def _por_etapa(batimentos):
    """{etapa: [batimento, ...]} do mais novo pro mais velho."""
    grupos = {}
    for b in batimentos:
        grupos.setdefault(b.get("etapa"), []).append(b)
    for lista in grupos.values():
        lista.sort(key=lambda b: _instante(b.get("inicio")) or datetime.min.replace(
            tzinfo=timezone.utc), reverse=True)
    return grupos


def _concluidos(lista):
    """Rodadas que terminaram (ok gravado). Rodada em andamento (fim nulo)
    nao conta nem como ok nem como falha."""
    return [b for b in lista if b.get("ok") is not None]


def _detalhe(b):
    d = b.get("detalhe")
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except ValueError:
            d = {}
    return d if isinstance(d, dict) else {}


def _taxa_falha(b):
    """falhas / (lidos + falhas): `lidos` dos checadores ja exclui as falhas
    (ok + alertas), entao falhas/lidos passaria de 100% e dividiria por zero
    na rodada em que tudo falhou."""
    falhas = b.get("falhas") or 0
    total = (b.get("lidos") or 0) + falhas
    return falhas / float(total) if total else None


def regra_ingestao(por_etapa, agora):
    problemas = []
    rodadas = _concluidos(por_etapa.get("ingestao", []))
    oks = [b for b in rodadas if b.get("ok")]
    ultima_ok = _instante(oks[0]["inicio"]) if oks else None
    if ultima_ok is None or _horas(agora - ultima_ok) >= JANELA_INGESTAO_OK_H:
        extra = ""
        if rodadas and not rodadas[0].get("ok"):
            erro = _detalhe(rodadas[0]).get("erro")
            extra = "\nÚltima tentativa falhou%s" % (": %s" % erro[:150] if erro else "")
        problemas.append({
            "chave": PREFIXO + "ingestao", "nivel": "vermelho",
            "texto": "Ingestão da Volly sem rodada ok %s (esperado a cada 2h)%s" % (
                _desde(ultima_ok, agora), extra)})
    if oks:
        atual = _detalhe(oks[0]).get("futuros_ativos")
        anteriores = [_detalhe(b).get("futuros_ativos") for b in oks[1:RODADAS_MEDIA + 1]]
        anteriores = [n for n in anteriores if isinstance(n, (int, float))]
        if isinstance(atual, (int, float)) and anteriores:
            media = sum(anteriores) / float(len(anteriores))
            if media > 0 and atual < media * (1 - QUEDA_FUTUROS_MAX):
                problemas.append({
                    "chave": PREFIXO + "ingestao:queda", "nivel": "vermelho",
                    "texto": "Voos futuros na ingestão caíram para %d (média recente %.0f, "
                             "queda de %.0f%%)" % (atual, media, 100 * (1 - atual / media))})
    return problemas


def regra_correcao_desfeita(por_etapa):
    """Correcao aplicada na Volly que voltou ao valor antigo, segundo a
    ultima ingestao ok (aplicar_volly_cloud.correcoes_desfeitas). Vermelho:
    o passageiro pode estar com o horario errado de novo."""
    oks = [b for b in _concluidos(por_etapa.get("ingestao", [])) if b.get("ok")]
    if not oks:
        return []
    desfeitas = _detalhe(oks[0]).get("correcoes_desfeitas") or []
    if not desfeitas:
        return []
    linhas = ["• %s%s — %s" % ((d.get("mensagem") or d.get("voo_id") or "?")
                               .replace("✏️ Na Volly mudaria — ", "")[:120],
                               " (👤 %s)" % d["passageiros"] if d.get("passageiros") else "",
                               d.get("motivo") or "")
              for d in desfeitas[:10]]
    return [{"chave": PREFIXO + "correcao-desfeita", "nivel": "vermelho",
             "texto": "%d correção(ões) aplicada(s) na Volly foram desfeitas "
                      "(emissão ressincronizada ou editada?)\n%s" % (len(desfeitas), "\n".join(linhas))}]


def regra_login_volly(por_etapa, agora):
    """Erro de login em etapa Volly nas ultimas 2h. Ignora a falha que ja foi
    superada por uma rodada ok DEPOIS dela: toda etapa Volly autentica no
    inicio, entao rodada ok = token vivo de novo."""
    todas = []
    for etapa in ETAPAS_VOLLY:
        todas += [(etapa, b) for b in _concluidos(por_etapa.get(etapa, []))]
    oks = [_instante(b["inicio"]) for _, b in todas if b.get("ok")]
    ultimo_ok = max(oks) if oks else None
    falhas = []
    for etapa, b in todas:
        inicio = _instante(b.get("inicio"))
        if inicio is None or _horas(agora - inicio) >= JANELA_LOGIN_H:
            continue
        if ultimo_ok is not None and ultimo_ok > inicio:
            continue
        d = _detalhe(b)
        if d.get("erro_login") or _ERRO_AUTH.search(str(d.get("erro") or "")):
            falhas.append((inicio, etapa, d))
    if not falhas:
        return []
    falhas.sort(key=lambda f: f[0], reverse=True)
    inicio, etapa, d = falhas[0]
    erro = str(d.get("erro") or "")[:150]
    return [{
        "chave": PREFIXO + "login-volly", "nivel": "vermelho",
        "texto": "Login na Volly falhando (%s, %s)%s\nEtapas afetadas: %s" % (
            etapa, _ha(inicio, agora), "\n%s" % erro if erro else "",
            ", ".join(sorted({f[1] for f in falhas})))}]


def regra_monitor_volly(por_etapa, agora):
    rodadas = _concluidos(por_etapa.get("monitor-volly", []))
    oks = [b for b in rodadas if b.get("ok")]
    ultima_ok = _instante(oks[0]["inicio"]) if oks else None
    if ultima_ok is not None and _horas(agora - ultima_ok) < JANELA_MONITOR_OK_H:
        return []
    extra = ""
    if rodadas and not rodadas[0].get("ok"):
        erro = _detalhe(rodadas[0]).get("erro")
        extra = "\nÚltima tentativa falhou%s" % (": %s" % erro[:150] if erro else "")
    return [{"chave": PREFIXO + "monitor-volly", "nivel": "laranja",
             "texto": "Monitor Volly sem rodada ok %s (esperado a cada 2h, das 07h às 23h)%s" % (
                 _desde(ultima_ok, agora), extra)}]


def regra_etapas_agendadas(por_etapa, agora):
    """Portais e malha: rodaram na janela, e a ultima rodada nao quebrou nem
    falhou bem acima do proprio historico."""
    problemas = []
    for etapa, janela in sorted(JANELA_ETAPA_H.items()):
        rodadas = _concluidos(por_etapa.get(etapa, []))
        chave = PREFIXO + etapa
        ultima = rodadas[0] if rodadas else None
        inicio = _instante(ultima["inicio"]) if ultima else None
        if inicio is None or _horas(agora - inicio) >= janela:
            problemas.append({"chave": chave, "nivel": "laranja",
                              "texto": "%s sem rodar %s (esperado em até %dh)" % (
                                  etapa, _desde(inicio, agora), janela)})
            continue
        if not ultima.get("ok"):
            erro = str(_detalhe(ultima).get("erro") or "")[:150]
            problemas.append({"chave": chave, "nivel": "laranja",
                              "texto": "%s: última rodada quebrou (%s)%s" % (
                                  etapa, _ha(inicio, agora), "\n%s" % erro if erro else "")})
            continue
        taxa = _taxa_falha(ultima)
        if taxa is None or taxa <= TAXA_FALHA_MIN:
            continue
        historico = [_taxa_falha(b) for b in rodadas[1:RODADAS_MEDIA + 1]]
        historico = [t for t in historico if t is not None]
        media = sum(historico) / len(historico) if historico else 0.0
        # 100% de falha nunca e "normal": o portal GOL passou semanas com
        # lidos=0 e a media dele tambem era 100%, entao a regra calava
        if taxa > 2 * media or not ultima.get("lidos"):
            problemas.append({"chave": chave, "nivel": "laranja",
                              "texto": "%s: %d de %d consultas falharam (%.0f%%; média "
                                       "recente %.0f%%)" % (
                                           etapa, ultima.get("falhas") or 0,
                                           (ultima.get("lidos") or 0) + (ultima.get("falhas") or 0),
                                           100 * taxa, 100 * media)})
    return problemas


# Malha que roda "ok" mas nao consulta nada: a janela e o minimo de rodadas
# concluidas dentro dela. A malha roda 2x/dia, entao 2 rodadas em 30h e a
# prova de que nao foi um dia isolado.
JANELA_MALHA_SEM_CONSULTA_H = 30
RODADAS_MALHA_SEM_CONSULTA = 2


def regra_malha_sem_consultar(por_etapa, agora):
    """Malha que terminou ok, com voo adiado por falta de orcamento, e zero
    chamadas em todas as rodadas da janela.

    Pegadinha de 29/09 a 17/10/2026: o saldo velho da cota (41, piso 40) fez
    o orcamento dar 1 unidade, nenhuma consulta de 2 unidades coube, e a
    malha passou 18 dias saindo `ok` com `lidos=0` sem ninguem saber. So
    "adiados_por_orcamento > 0" separa isso de rodada legitimamente vazia
    (todos os voos ainda dentro do prazo da rotacao).
    """
    recentes = [b for b in _concluidos(por_etapa.get("malha", []))
                if b.get("ok") and _instante(b.get("inicio")) is not None
                and _horas(agora - _instante(b["inicio"])) < JANELA_MALHA_SEM_CONSULTA_H]
    if len(recentes) < RODADAS_MALHA_SEM_CONSULTA:
        return []
    for b in recentes:
        d = _detalhe(b)
        if d.get("chamadas") != 0 or not (d.get("adiados_por_orcamento") or 0) > 0:
            return []
    d = _detalhe(recentes[0])
    return [{"chave": PREFIXO + "malha-sem-consulta", "nivel": "laranja",
             "texto": "Malha rodou %d vezes em %dh sem consultar nenhum voo: %d adiados "
                      "por orçamento (orçamento %s, cota %s). Os voos que a Volly não lê "
                      "(noturnos, sem leitura) estão sem cobertura de reserva." % (
                          len(recentes), JANELA_MALHA_SEM_CONSULTA_H,
                          d.get("adiados_por_orcamento") or 0,
                          d.get("orcamento", "?"), d.get("cota_restante", "?"))}]


def voos_elegiveis(voos, agora):
    """ativo (ja filtrado na leitura), embarque futuro, sem `incompleto`."""
    saida = []
    for v in voos:
        embarque = _instante(v.get("embarque"))
        if v.get("incompleto") or embarque is None or embarque <= agora:
            continue
        saida.append(v)
    return saida


def voos_incompletos(voos, agora):
    saida = []
    for v in voos:
        embarque = _instante(v.get("embarque"))
        if v.get("incompleto") and embarque is not None and embarque > agora:
            saida.append(v)
    return sorted(saida, key=lambda v: v.get("embarque") or "")


def ultima_leitura_por_voo(observacoes, agora):
    """{voo_id: instante da leitura mais nova, de qualquer fonte}. Fica de
    fora a origem de simulacao (`*-plano`): --plano grava pra comparar, mas
    nao e leitura de verdade que alguem vai usar."""
    ultima = {}
    for o in observacoes:
        if (o.get("origem") or "").endswith("-plano"):
            continue
        visto = _tolerante(o.get("visto_em"), agora)
        if visto is None:
            continue
        atual = ultima.get(o.get("voo_id"))
        if atual is None or visto > atual:
            ultima[o.get("voo_id")] = visto
    return ultima


def motivos_sem_leitura(por_etapa):
    """{voo_id: motivo} da ultima rodada concluida do monitor Volly."""
    rodadas = _concluidos(por_etapa.get("monitor-volly", []))
    if not rodadas:
        return {}
    motivos = {}
    for item in _detalhe(rodadas[0]).get("sem_leitura_lista") or []:
        for voo_id in item.get("voo_ids") or []:
            motivos[voo_id] = item.get("motivo")
    return motivos


def sem_cobertura(voos, observacoes, por_etapa, agora):
    """[(voo, ultima_leitura, motivo)] dos elegiveis sem leitura no prazo,
    embarque mais proximo primeiro."""
    leituras = ultima_leitura_por_voo(observacoes, agora)
    motivos = motivos_sem_leitura(por_etapa)
    faltando = []
    for v in voos_elegiveis(voos, agora):
        embarque = _instante(v["embarque"])
        prazo = prazo_cobertura_h(_horas(embarque - agora))
        visto = leituras.get(v["id"])
        if visto is None or _horas(agora - visto) >= prazo:
            faltando.append((v, visto, motivos.get(v["id"])))
    faltando.sort(key=lambda f: f[0].get("embarque") or "")
    return faltando


def _linha_voo(v, extra=""):
    embarque = _instante(v.get("embarque"))
    nomes = qualidade.nomes_passageiros(v.get("passageiros"), limite=2)
    return "%s %s %s%s%s" % (v.get("localizador") or "?", v.get("numero_voo") or "-",
                             embarque.strftime("%d/%m") if embarque else "?",
                             " (%s)" % nomes if nomes else "", extra)


def regra_cobertura(voos, observacoes, por_etapa, agora):
    faltando = sem_cobertura(voos, observacoes, por_etapa, agora)
    if not faltando:
        return []
    linhas = []
    for v, visto, motivo in faltando[:LISTA_MAX]:
        partes = ["última leitura %s" % _ha(visto, agora) if visto else "nunca lido"]
        if motivo:
            partes.append(motivo)
        linhas.append("• " + _linha_voo(v, " (%s)" % ", ".join(partes)))
    if len(faltando) > LISTA_MAX:
        linhas.append("… e mais %d" % (len(faltando) - LISTA_MAX))
    total = len(voos_elegiveis(voos, agora))
    return [{"chave": PREFIXO + "cobertura", "nivel": "laranja",
             "texto": "%d de %d voos sem leitura no prazo (24h, ou 4h se embarca em "
                      "menos de 24h)\n%s" % (len(faltando), total, "\n".join(linhas))}]


def origens_seguradas(estado):
    """{origem: desde} de `telegram_segurado` (fase 4, nuvem_comum): acima do
    teto a origem fica segurada ate alguem liberar no site ou passar 24h, e o
    proprio checador solta na rodada seguinte. Aceita lista tambem, por
    garantia, se o formato mudar."""
    for e in estado:
        if e.get("chave") == "telegram_segurado":
            origens = (e.get("detalhe") or {}).get("origens") or {}
            if isinstance(origens, list):
                return dict((o, e.get("aberto_em")) for o in origens)
            return dict(origens)
    return {}


def _pendentes_telegram(historico, agora):
    """[(detectado, historico)] de alerta gravado, nao resolvido e nao
    avisado. `confirmado` (segunda fonte, fase 4) ja nem vem na leitura:
    grava notificado = true e nao e alerta."""
    pendentes = []
    for h in historico:
        if h.get("notificado") is not False or h.get("resolvido"):
            continue
        origem = h.get("origem") or ""
        if origem == "milhasflow" or origem.endswith("-plano"):
            continue
        detectado = _tolerante(h.get("detectado_em"), agora)
        if detectado is not None:
            pendentes.append((detectado, h))
    return pendentes


def regra_telegram_pendente(historico, estado, agora):
    """Alerta sem Telegram ha mais de 30 min -> vermelho. Origem segurada de
    proposito pelo teto (fase 4) fica fora: segurado nao e Telegram quebrado.
    Ela vira um amarelo proprio se o segurado passar de 1h sem liberar."""
    seguradas = origens_seguradas(estado)
    limite = agora - timedelta(minutes=TELEGRAM_PENDENTE_MIN)
    todos = _pendentes_telegram(historico, agora)
    problemas = []

    atrasados = sorted([p for p in todos if p[0] < limite
                        and (p[1].get("origem") or "") not in seguradas], key=lambda p: p[0])
    if atrasados:
        origens = sorted({p[1].get("origem") or "?" for p in atrasados})
        problemas.append({
            "chave": PREFIXO + "telegram-pendente", "nivel": "vermelho",
            "texto": "%d alertas gravados e não avisados no Telegram (mais antigo %s; "
                     "origens: %s)" % (len(atrasados), _ha(atrasados[0][0], agora),
                                       ", ".join(origens))})

    velhas = {}
    for origem, desde in seguradas.items():
        momento = _instante(desde)
        if momento is None or agora - momento >= timedelta(hours=SEGURADO_AVISO_H):
            velhas[origem] = momento
    if velhas:
        qtd = len([p for p in todos if (p[1].get("origem") or "") in velhas])
        momentos = [m for m in velhas.values() if m is not None]
        mais_velho = min(momentos) if momentos else None
        problemas.append({
            "chave": PREFIXO + "telegram-segurado", "nivel": "amarelo",
            "texto": "%d alertas segurados aguardando liberação (origens %s; segurado %s) "
                     "— botão \"Liberar alertas segurados\" na aba Urgente" % (
                         qtd, ", ".join(sorted(velhas)), _ha(mais_velho, agora))})
    return problemas


def regra_verificado_sem_proposta(verificados, propostas, agora):
    propostas_por_hist = {}
    for p in propostas:
        propostas_por_hist.setdefault(p.get("historico_id"), []).append(
            _instante(p.get("criado_em")))
    faltando = []
    for h in verificados:
        verificado = _instante(h.get("verificado_em"))
        if verificado is None:
            continue
        idade = agora - verificado
        if idade < timedelta(minutes=PROPOSTA_PRAZO_MIN) or idade > timedelta(days=PROPOSTA_JANELA_D):
            continue
        criadas = [c for c in propostas_por_hist.get(h.get("id"), []) if c is not None]
        if any(c >= verificado for c in criadas):
            continue
        faltando.append((verificado, h))
    if not faltando:
        return []
    faltando.sort(key=lambda f: f[0])
    linhas = ["• alerta %s (voo %s, verificado %s)" % (
        h.get("id"), (h.get("voo_id") or "?")[:8], _ha(v, agora)) for v, h in faltando[:LISTA_MAX]]
    return [{"chave": PREFIXO + "verificado-sem-proposta", "nivel": "laranja",
             "texto": "%d alertas verificados sem proposta da reconferência em %d min\n%s" % (
                 len(faltando), PROPOSTA_PRAZO_MIN, "\n".join(linhas))}]


def avaliar(dados, agora):
    """Pura: dados (ver ler_dados) + instante -> [problema], mais grave primeiro.

    Trechos `incompleto` nao sao problema: entram so no resumo diario.
    """
    por_etapa = _por_etapa(dados.get("batimentos") or [])
    problemas = []
    problemas += regra_ingestao(por_etapa, agora)
    problemas += regra_login_volly(por_etapa, agora)
    problemas += regra_correcao_desfeita(por_etapa)
    problemas += regra_monitor_volly(por_etapa, agora)
    problemas += regra_etapas_agendadas(por_etapa, agora)
    problemas += regra_malha_sem_consultar(por_etapa, agora)
    problemas += regra_cobertura(dados.get("voos") or [], dados.get("observacoes") or [],
                                 por_etapa, agora)
    problemas += regra_telegram_pendente(dados.get("historico") or [],
                                         dados.get("estado") or [], agora)
    problemas += regra_verificado_sem_proposta(dados.get("verificados") or [],
                                               dados.get("propostas") or [], agora)
    problemas.sort(key=lambda p: (ORDEM_NIVEL.get(p["nivel"], 9), p["chave"]))
    return problemas


# ------------------------------------------------------------ estado + Telegram

def _titulo(texto):
    return (texto or "").split("\n", 1)[0][:160]


def comparar_estado(problemas, estado):
    """(novos, normalizados): problema sem linha `sup:` no estado, e linha
    `sup:` (menos o resumo) sem problema correspondente."""
    abertos = {e["chave"]: e for e in estado
               if (e.get("chave") or "").startswith(PREFIXO) and e["chave"] != CHAVE_RESUMO}
    atuais = {p["chave"] for p in problemas}
    novos = [p for p in problemas if p["chave"] not in abertos]
    normalizados = [e for chave, e in sorted(abertos.items()) if chave not in atuais]
    return novos, normalizados


def texto_problema(p):
    return "%s <b>Supervisor</b> — %s" % (ICONE_NIVEL.get(p["nivel"], "⚪"),
                                          _escapar(p["texto"]))


def texto_normalizado(linha):
    d = linha.get("detalhe") or {}
    return "✅ normalizado: %s" % _escapar(_titulo(d.get("texto") or linha.get("chave")))


def _escapar(texto):
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def aplicar_estado(supabase_url, service_key, telegram_token, telegram_chat,
                   problemas, estado, agora):
    """Telegram so do que mudou e grava o estado DEPOIS do envio ok - se o
    Telegram falhar, a proxima rodada ve o mesmo problema como novo e tenta
    de novo, em vez de o aviso se perder."""
    novos, normalizados = comparar_estado(problemas, estado)
    agora_iso = agora.isoformat(timespec="seconds")
    enviados = []
    for p in novos:
        ok, erro = alertas.enviar_telegram(telegram_token, telegram_chat, texto_problema(p))
        if not ok:
            print("AVISO: Telegram do problema %s falhou (%s)" % (p["chave"], erro))
            continue
        supabase_rest.upsert(supabase_url, service_key, "supervisor_estado", [{
            "chave": p["chave"], "aberto_em": agora_iso, "avisado_em": agora_iso,
            "detalhe": {"nivel": p["nivel"], "texto": p["texto"]}}], "chave")
        enviados.append(p["chave"])
    fechados = []
    for linha in normalizados:
        ok, erro = alertas.enviar_telegram(telegram_token, telegram_chat,
                                           texto_normalizado(linha))
        if not ok:
            print("AVISO: Telegram do normalizado %s falhou (%s)" % (linha["chave"], erro))
            continue
        apagar_estado(supabase_url, service_key, linha["chave"])
        fechados.append(linha["chave"])
    return enviados, fechados


# ------------------------------------------------------------ resumo diario

ETAPAS_RESUMO = ("ingestao", "monitor-volly", "malha", "portal-latam", "portal-gol",
                 "portal-azul")


def etapa_com_problema(etapa, problemas):
    alvo = PREFIXO + etapa
    return any(p["chave"] == alvo or p["chave"].startswith(alvo + ":") for p in problemas)


def montar_resumo(dados, problemas, agora):
    voos = dados.get("voos") or []
    elegiveis = voos_elegiveis(voos, agora)
    por_etapa = _por_etapa(dados.get("batimentos") or [])
    faltando = sem_cobertura(voos, dados.get("observacoes") or [], por_etapa, agora)
    cobertos = len(elegiveis) - len(faltando)
    pct = 100.0 * cobertos / len(elegiveis) if elegiveis else 100.0
    # mesmo recorte da aba Urgente: alerta nao resolvido de voo ativo futuro
    ids_futuros = {v.get("id") for v in voos}
    abertos = [h for h in dados.get("historico") or []
               if not h.get("resolvido") and h.get("voo_id") in ids_futuros
               and not (h.get("origem") or "").endswith("-plano")]
    incompletos = voos_incompletos(voos, agora)

    linhas = ["📋 <b>Resumo diário do monitoramento</b> — %s" % _brt(agora)[:5], ""]
    linhas.append("✈️ Voos monitorados: <b>%d</b>" % len(elegiveis))
    linhas.append("📡 Cobertura: <b>%.0f%%</b> (%d de %d lidos no prazo)" % (
        pct, cobertos, len(elegiveis)))
    linhas.append("🚨 Alertas abertos no site: <b>%d</b> (em %d voos)" % (
        len(abertos), len({h.get("voo_id") for h in abertos})))
    linhas.append("")
    linhas.append("<b>Etapas</b>")
    for etapa in ETAPAS_RESUMO:
        rodadas = _concluidos(por_etapa.get(etapa, []))
        quando = _ha(_instante(rodadas[0]["inicio"]), agora) if rodadas else "nunca"
        icone = "⚠️" if etapa_com_problema(etapa, problemas) else "✅"
        linhas.append("%s %s (última %s)" % (icone, etapa, quando))
    linhas.append("")
    if problemas:
        linhas.append("<b>Problemas abertos (%d)</b>" % len(problemas))
        for p in problemas:
            linhas.append("%s %s" % (ICONE_NIVEL.get(p["nivel"], "⚪"), _escapar(_titulo(p["texto"]))))
    else:
        linhas.append("Nenhum problema aberto.")
    if incompletos:
        linhas.append("")
        linhas.append("🟡 <b>Trechos incompletos (%d)</b> — não são checados" % len(incompletos))
        for v in incompletos[:10]:
            linhas.append("• %s — %s" % (_escapar(_linha_voo(v)), _escapar(v.get("incompleto"))))
        if len(incompletos) > 10:
            linhas.append("… e mais %d" % (len(incompletos) - 10))
    linhas.append("")
    linhas.append("<i>A falta deste resumo é o alarme: se ele não chegar até as 08h, "
                  "o GitHub Actions (ou o próprio supervisor) parou.</i>")
    return "\n".join(linhas)


def resumo_devido(estado, agora):
    """A partir da rodada das 10h UTC e ainda nao mandou hoje.

    `>=` e nao `==`: o agendador do Actions atrasa e pula rodadas neste repo
    (malha das 10h rodando as 14h-15h, crons de 2h rodando a cada 5-7h) -
    com `==` basta a rodada das 10h cair pra 11h e o dia fica sem resumo,
    que e justamente o falso alarme de "Actions parou"."""
    if agora.hour < HORA_RESUMO_UTC:
        return False
    for e in estado:
        if e.get("chave") == CHAVE_RESUMO:
            return (e.get("detalhe") or {}).get("dia") != agora.date().isoformat()
    return True


def enviar_resumo(supabase_url, service_key, telegram_token, telegram_chat, texto, agora):
    ok, erro = alertas.enviar_telegram(telegram_token, telegram_chat, texto)
    if not ok:
        print("AVISO: resumo diario nao saiu (%s)" % erro)
        return False
    agora_iso = agora.isoformat(timespec="seconds")
    supabase_rest.upsert(supabase_url, service_key, "supervisor_estado", [{
        "chave": CHAVE_RESUMO, "aberto_em": agora_iso, "avisado_em": agora_iso,
        "detalhe": {"dia": agora.date().isoformat()}}], "chave")
    return True


# ------------------------------------------------------------ rodada

def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def imprimir(problemas, dados, agora):
    print("Supervisor — %s UTC (%s Brasília)" % (agora.strftime("%d/%m %H:%M"), _brt(agora)))
    print("  batimentos lidos (7 dias) ... %d" % len(dados.get("batimentos") or []))
    print("  voos elegiveis .............. %d" % len(voos_elegiveis(dados.get("voos") or [], agora)))
    if not problemas:
        print("\nNenhum problema.")
    for p in problemas:
        print("\n%s [%s] %s" % (ICONE_NIVEL.get(p["nivel"], "?"), p["chave"], p["texto"]))


def rodar(supabase_url, service_key, telegram_token, telegram_chat, agora, plano, b=None):
    dados = ler_dados(supabase_url, service_key, agora)
    problemas = avaliar(dados, agora)
    imprimir(problemas, dados, agora)
    novos, normalizados = comparar_estado(problemas, dados["estado"])

    if plano:
        print("\n(--plano) novos: %s | normalizados: %s" % (
            [p["chave"] for p in novos] or "-", [e["chave"] for e in normalizados] or "-"))
        print("\n(--plano) resumo diario %s:\n" % (
            "seria enviado agora" if resumo_devido(dados["estado"], agora)
            else "(so na rodada das 11h UTC; texto de hoje)"))
        print(montar_resumo(dados, problemas, agora))
        return problemas

    enviados, fechados = aplicar_estado(supabase_url, service_key, telegram_token,
                                        telegram_chat, problemas, dados["estado"], agora)
    print("\nTelegram: %d problema(s) novo(s), %d normalizado(s)" % (len(enviados), len(fechados)))
    resumo = False
    if resumo_devido(dados["estado"], agora):
        resumo = enviar_resumo(supabase_url, service_key, telegram_token, telegram_chat,
                               montar_resumo(dados, problemas, agora), agora)
        print("Resumo diario: %s" % ("enviado" if resumo else "falhou"))
    if b is not None:
        b.lidos = len(voos_elegiveis(dados.get("voos") or [], agora))
        b.alertas = len(enviados)
        b.detalhe = {"abertos": [p["chave"] for p in problemas], "novos": enviados,
                     "normalizados": fechados, "resumo_diario": resumo}
    return problemas


def main():
    plano = "--plano" in sys.argv
    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    agora = datetime.now(timezone.utc)
    if plano:
        # sem batimento: simulacao nao conta como supervisor que rodou
        rodar(supabase_url, service_key, telegram_token, telegram_chat, agora, True)
        return
    with batimento.rodada(supabase_url, service_key, ETAPA) as b:
        rodar(supabase_url, service_key, telegram_token, telegram_chat, agora, False, b)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("O supervisor (nuvem)", erro)
        sys.exit(1)
