"""Regras de decisao do robo de movimentacao do CRM (funil Pos-Venda do
MilhasFlow/Volly) - ver docs/superpowers/specs/2026-08-24-automacao-crm-
milhasflow-design.md.

Camada pura: recebe os trechos de voo ja lidos (mesmo formato que
sync.montar_voos usa - chaves origem/destino/embarque/chegada) e o estado
atual do card, devolve a coluna alvo. Nao acessa rede - testavel por
testes/rodar_testes.py, mesmo espirito de malha.py/comparacao.py.
"""

import re
from datetime import datetime, timedelta, timezone

# column_key de cada coluna do funil Pos-Venda - descoberto na pratica
# (nao documentado pelo MilhasFlow/Volly), ver a spec.
COL_AGUARDANDO_VIAGEM = "aguardando_viagem"
COL_CHECKUP_NACIONAL = "custom_1787888677492"
COL_CHECKUP_INTERNACIONAL = "custom_1787888757679"
COL_PROXIMA_NACIONAL = "custom_1787540129258"
COL_PROXIMA_INTERNACIONAL = "custom_1787540481015"
COL_EM_VIAGEM = "em_viagem"
COL_AGUARDANDO_FEEDBACK = "feedback"
COL_CONCLUIDO = "concluido"

# Colunas terminais que nunca tem whatsapp_message configurado no Volly (nem
# deveriam ter - nao ha o que avisar). Usado tanto na hora de planejar (pula
# a exigencia de mensagem) quanto na hora de executar (pula telefone/
# agendamento) - fica num lugar so em vez de cada lado checar `==
# COL_CONCLUIDO` por conta propria.
COLUNAS_SEM_MENSAGEM = {COL_CONCLUIDO}

# Decisoes do proprietário (2026-08-24)
NACIONAL_DIAS = 8
INTERNACIONAL_DIAS = 23
FEEDBACK_DIAS = 2

# Decisoes do proprietário (2026-08-28) - novo estagio "Checkup" antes de "Viagem
# Proxima": contato mais cedo (31d/46d) pra perguntar como anda a
# organizacao da viagem; so mais perto do embarque (NACIONAL_DIAS/
# INTERNACIONAL_DIAS acima) e que entra a mensagem de "sua viagem esta
# chegando" de Viagem Proxima.
NACIONAL_CHECKUP_DIAS = 31
INTERNACIONAL_CHECKUP_DIAS = 46

# Aeroportos do Brasil (IATA). O board mostra uma tag "Nacional"/
# "Internacional" por card, mas isso e calculado do lado do site a partir
# do codigo do aeroporto - nao e um campo de dado que a API expoe. Mantemos
# nossa propria lista pra classificar do mesmo jeito, sem depender de campo
# nenhum do MilhasFlow.
BRASIL_IATA = {
    "AAX", "AFL", "AJU", "ARU", "BEL", "BFH", "BPS", "BSB", "BVB", "BVH",
    "CAC", "CAW", "CFB", "CFC", "CGB", "CGH", "CGR", "CKS", "CLV", "CMG",
    "CNF", "CPV", "CWB", "CXJ", "CZS", "DIQ", "ERM", "FEN", "FLN", "FOR",
    "GEL", "GIG", "GRU", "GYN", "GVR", "IGU", "IOS", "IPN", "ITA", "JCB",
    "JDO", "JJD", "JOI", "JPA", "JTC", "LDB", "LEC", "MAB", "MAO", "MCP",
    "MCZ", "MEA", "MGF", "MII", "MOC", "MVF", "NAT", "NVT", "PET", "PFB",
    "PMW", "POA", "PPB", "PVH", "QGF", "RAO", "REC", "RBR", "RIA", "RVD",
    "SDU", "SJK", "SJP", "SLZ", "SSA", "STM", "SSZ", "TFF", "THE", "UBA",
    "UDI", "UNA", "VCP", "VDC", "VIX", "XAP",
    # codigos metropolitanos/multi-aeroporto (cobrem mais de um aeroporto
    # fisico da mesma cidade) - achado real em producao, 28/08/2026: "BHZ"
    # (Belo Horizonte, cobre CNF/PLU) aparecia em trecho de onibus da Sabia
    # e, por nao estar aqui, virava "internacional" por engano.
    "BHZ", "RIO", "SAO",
}

# So conta um origem/destino pra classificacao se parecer mesmo um codigo
# IATA (3 letras). Sem isso, lixo de dado tipo "SAO-TIETE" (nome de
# terminal rodoviario colado no campo, achado real em producao 28/08/2026)
# faz `all(eh_brasileiro(...))` falhar e o card vira "internacional" por
# um dado que nem e codigo de aeroporto nenhum.
RE_CODIGO_IATA = re.compile(r"^[A-Z]{3}$")


def eh_codigo_iata(codigo):
    return bool(RE_CODIGO_IATA.match((codigo or "").strip().upper()))


def _coletar_locators(no, encontrados):
    """Percorre o JSON de `flights` (que varia de formato - as vezes
    outbound/return direto, as vezes `options`/`flight_sub_options`
    aninhados - ver a spec) coletando todo valor de campo `locator` nao
    vazio, em qualquer profundidade."""
    if isinstance(no, dict):
        valor = no.get("locator")
        if isinstance(valor, str) and valor.strip():
            encontrados.add(valor.strip().upper())
        for v in no.values():
            _coletar_locators(v, encontrados)
    elif isinstance(no, list):
        for item in no:
            _coletar_locators(item, encontrados)


def locators_da_cotacao(quote):
    """Localizadores encontrados no `flights` de uma cotacao do CRM.

    As cotacoes do Pos-Venda sao copias da cotacao original aprovada (ver
    a spec) - nao ha link direto (emission_id/crm_quote_id) pra achar a
    emissao de verdade. O jeito que funciona: casar esses localizadores
    contra `reminders.locator`, que e o dado que o motor de checagem ja
    confia.
    """
    encontrados = set()
    _coletar_locators(quote.get("flights"), encontrados)
    return encontrados


def eh_brasileiro(codigo):
    return (codigo or "").strip().upper() in BRASIL_IATA


def tem_tag_onibus(tags):
    """True se a cotacao tem a tag "ONIBUS" (`quote.tags`, formato
    "<nome>|<cor>" tipo "ONIBUS|#6366f1" - visto em cotacoes reais). Usado
    pra nunca classificar trecho de onibus como internacional mesmo quando
    o campo origem/destino vem com nome completo da estacao (ex "Rio de
    Janeiro (Novo Rio)") em vez de qualquer codigo - texto livre desse
    jeito nao passa nem pelo filtro de eh_codigo_iata, entao sem essa
    excecao explicita a cotacao ficaria sem dado suficiente pra classificar
    (achado real em producao, 2026-08-28). Decisao do proprietário: onibus nunca
    e internacional, ponto - nunca visto saindo do Brasil."""
    return any((t or "").split("|")[0].strip().upper() == "ONIBUS" for t in (tags or []))


def classificar_viagem(trechos, tags=None):
    """'nacional' | 'internacional' | None (sem dado suficiente).

    tags: `quote.tags` da cotacao - se tiver a tag ONIBUS, forca nacional
    assim que houver QUALQUER dado de trecho (ver tem_tag_onibus), antes
    de filtrar por eh_codigo_iata - onibus as vezes vem com nome completo
    da estacao em vez de codigo, e ainda assim precisa contar como dado
    suficiente.

    Pra cotacao sem essa tag, so conta origem/destino que parece codigo
    IATA de verdade (3 letras, ver eh_codigo_iata) - achado real em
    producao (28/08/2026): "SAO-TIETE" (nome de terminal rodoviario colado
    no campo) fazia uma cotacao 100% nacional virar "internacional" por um
    dado que nem e codigo de aeroporto.
    """
    tem_dado = any(t.get("origem") or t.get("destino") for t in trechos)
    if not tem_dado:
        return None
    if tem_tag_onibus(tags):
        return "nacional"
    codigos = set()
    for t in trechos:
        for campo in ("origem", "destino"):
            c = (t.get(campo) or "").strip().upper()
            if eh_codigo_iata(c):
                codigos.add(c)
    if not codigos:
        return None
    return "nacional" if all(eh_brasileiro(c) for c in codigos) else "internacional"


def resumo_rota(trechos):
    """String tipo "GRU-LIS, LIS-GRU" com os aeroportos REAIS dos trechos
    vinculados (via locator/reminders), na ordem de embarque - pra deixar
    auditavel no log/aviso qual dado concreto decidiu nacional vs
    internacional, sem depender do `title` digitado na cotacao (que pode
    nao bater com o trecho de verdade). Vazio se nao ha trecho nenhum."""
    validos = [t for t in trechos if t.get("origem") and t.get("destino")]
    validos.sort(key=lambda t: t.get("embarque") or "")
    return ", ".join("%s-%s" % (t["origem"], t["destino"]) for t in validos)


def primeiro_e_volta(trechos):
    """(embarque_1_trecho_iso, ha_volta, chegada_da_volta_iso).

    'Ha volta' e detectada de forma estrutural - a viagem volta pro
    aeroporto de onde saiu -, nao por um campo de direcao do MilhasFlow:
    nenhum campo do tipo la (flight_direction/flight_leg_order/
    flight_group_index) tem valor conhecido ou documentado em lugar nenhum
    do projeto, e assumir um valor errado quebraria a regra em silencio.
    Essa checagem cobre viagem simples, ida e volta, e ida e volta com
    conexao (o ultimo trecho cronologico e que fecha o ciclo).

    trechos: lista de dicts com origem/destino/embarque/chegada (mesmas
    chaves que sync.montar_voos produz), ja filtrados pra uma emissao so.
    Sem trecho valido, devolve (None, False, None).
    """
    validos = [t for t in trechos
               if t.get("embarque") and t.get("chegada")
               and t.get("origem") and t.get("destino")]
    if not validos:
        return None, False, None

    primeiro = min(validos, key=lambda t: t["embarque"])
    ultimo = max(validos, key=lambda t: t["chegada"])

    ha_volta = (ultimo is not primeiro
                and ultimo["destino"].strip().upper() == primeiro["origem"].strip().upper())
    return primeiro["embarque"], ha_volta, (ultimo["chegada"] if ha_volta else None)


def para_datetime(iso):
    """Publica (usada tambem por mover_crm_cloud.py, sem duplicar) - se o
    MilhasFlow algum dia mandar um horario sem fuso, cai pra UTC em vez de
    devolver um datetime "naive" que quebraria a comparacao com `agora`
    (tz-aware) mais na frente. Mesma protecao que fusos.para_local ja tem
    pro mesmo tipo de dado."""
    if not iso:
        return None
    try:
        momento = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def embarque_ja_ocorreu(trechos, agora):
    """True se o 1o trecho ja embarcou. Usado pra pegar card esquecido em
    Aguardando Viagem cujo cliente pode estar viajando AGORA (embarcou mas
    a viagem ainda nao terminou) - esse caso fica ambiguo demais pro robo
    decidir sozinho, precisa de olhar humano."""
    embarque_ida, _, _ = primeiro_e_volta(trechos)
    embarque_dt = para_datetime(embarque_ida)
    return bool(embarque_dt and embarque_dt < agora)


def viagem_ja_terminou(trechos, agora):
    """True se a viagem INTEIRA (ida, e volta se houver) ja aconteceu -
    usado pra fechar direto em Concluido um card esquecido em Aguardando
    Viagem (achado real em producao em 24/08/2026: 7 cards parados com a
    viagem ja no passado). Pedido do proprietário: nesse caso nao faz sentido
    passar pelas mensagens intermediarias ("sua viagem esta chegando",
    "boa viagem") pra uma viagem que ja acabou - fecha direto.
    """
    validos = [t for t in trechos if t.get("chegada")]
    if not validos:
        return False
    ultima_chegada = max(t["chegada"] for t in validos)
    chegada_dt = para_datetime(ultima_chegada)
    return bool(chegada_dt and chegada_dt < agora)


def calcular_estagio_alvo(coluna_atual, trechos, entrou_em_feedback, agora, tags=None):
    """Devolve o column_key alvo, ou None se o card deve ficar onde esta.

    coluna_atual: column_key atual do card (crm_quote_placements.column_key).
    trechos: trechos de voo da emissao ligada a cotacao (ver
        primeiro_e_volta) - lista vazia = sem emissao vinculada ainda.
    entrou_em_feedback: datetime UTC de quando entrou em Aguardando
        Feedback (crm_estagios.entrou_em), ou None.
    agora: datetime UTC.
    tags: `quote.tags` da cotacao - ver classificar_viagem/tem_tag_onibus.

    So move pra frente - nunca reverte um card automaticamente. Coluna nao
    reconhecida (card fora do fluxo automatizado) tambem devolve None.
    """
    embarque_ida, ha_volta, chegada_volta = primeiro_e_volta(trechos)
    embarque_dt = para_datetime(embarque_ida)

    if coluna_atual == COL_AGUARDANDO_VIAGEM:
        if tem_tag_onibus(tags):
            # decisao do proprietário (28/08/2026): onibus nao tem check-in (a
            # mensagem de Viagem Proxima fala de check-in) nem faz sentido
            # ter "checkup" antes do embarque - pula direto pros estagios
            # que so existem depois que a viagem comecou de verdade, sem
            # aviso nenhum antes disso. Fluxo pedido: aguardando -> em
            # viagem -> feedback -> concluido, SEMPRE passando por
            # feedback (por isso nao usa viagem_ja_terminou aqui - pra
            # onibus so de ida, o unico trecho "terminar" e o proprio
            # embarque ja ter chegado, o que fecharia direto em Concluido
            # sem passar por Aguardando Feedback, contrariando o pedido).
            if not embarque_dt or embarque_dt > agora:
                return None
            if not ha_volta:
                return COL_AGUARDANDO_FEEDBACK
            chegada_volta_dt = para_datetime(chegada_volta)
            if not chegada_volta_dt or chegada_volta_dt > agora:
                return COL_EM_VIAGEM
            return COL_AGUARDANDO_FEEDBACK
        if viagem_ja_terminou(trechos, agora):
            # card esquecido com a viagem INTEIRA ja no passado (achado
            # real em producao, 24/08/2026) - pedido do proprietário: fecha
            # direto, sem passar pelas mensagens intermediarias que nao
            # fariam sentido pra uma viagem que ja acabou.
            return COL_CONCLUIDO
        if not embarque_dt or embarque_dt < agora:
            # embarcou mas a viagem ainda nao terminou - cliente pode
            # estar viajando agora. Ambiguo demais pra avancar sozinho;
            # quem chama decide se isso vira alerta de "olhar humano"
            # (mesmo dado, embarque_ja_ocorreu).
            return None
        dias_restantes = (embarque_dt - agora).total_seconds() / 86400
        classificacao = classificar_viagem(trechos, tags)
        if classificacao == "nacional" and dias_restantes <= NACIONAL_CHECKUP_DIAS:
            return COL_CHECKUP_NACIONAL
        if classificacao == "internacional" and dias_restantes <= INTERNACIONAL_CHECKUP_DIAS:
            return COL_CHECKUP_INTERNACIONAL
        return None

    if coluna_atual == COL_CHECKUP_NACIONAL:
        if embarque_dt and (embarque_dt - agora).total_seconds() / 86400 <= NACIONAL_DIAS:
            return COL_PROXIMA_NACIONAL
        return None

    if coluna_atual == COL_CHECKUP_INTERNACIONAL:
        if embarque_dt and (embarque_dt - agora).total_seconds() / 86400 <= INTERNACIONAL_DIAS:
            return COL_PROXIMA_INTERNACIONAL
        return None

    if coluna_atual in (COL_PROXIMA_NACIONAL, COL_PROXIMA_INTERNACIONAL):
        if not embarque_dt or embarque_dt > agora:
            return None
        return COL_EM_VIAGEM if ha_volta else COL_AGUARDANDO_FEEDBACK

    if coluna_atual == COL_EM_VIAGEM:
        chegada_dt = para_datetime(chegada_volta)
        if not ha_volta or not chegada_dt or chegada_dt > agora:
            return None
        return COL_AGUARDANDO_FEEDBACK

    if coluna_atual == COL_AGUARDANDO_FEEDBACK:
        if not entrou_em_feedback:
            return None
        if agora - entrou_em_feedback >= timedelta(days=FEEDBACK_DIAS):
            return COL_CONCLUIDO
        return None

    return None


def primeiro_nome(nome_completo):
    return (nome_completo or "").strip().split(" ")[0] or "cliente"


RE_PLACEHOLDER_SOBRANDO = re.compile(r"\{\{[^}]*\}\}")


def montar_mensagem(template, nome_completo):
    """None se o template nao existe OU se sobrar algum {{placeholder}} que
    a gente nao sabe substituir - so conhecemos {{primeiro_nome}} (unico
    visto num template real ate agora). Melhor nao mandar nada do que
    mandar um "{{outra_coisa}}" literal pro WhatsApp do cliente."""
    if not template:
        return None
    mensagem = template.replace("{{primeiro_nome}}", primeiro_nome(nome_completo))
    if RE_PLACEHOLDER_SOBRANDO.search(mensagem):
        return None
    return mensagem


def selecionar_novidades(planejadas, pendencias, erros_validacao, avisos_anteriores):
    """Filtra pro que ainda nao foi avisado por Telegram - pedido do proprietário
    (2026-08-28): sem isso, o mesmo "moveria Fulano de X pra Y" seria
    reenviado a cada rodada do cron (2/2h) pra sempre, ja que em --plano
    nada no board realmente muda de uma rodada pra outra.

    avisos_anteriores: {crm_quote_id: aviso} - o que ja foi mandado antes
    (lido de crm_avisos_plano). Devolve (planejadas_novas, pendencias_novas,
    erros_novos, avisos_atuais) - avisos_atuais e {crm_quote_id: aviso}
    coincidindo com TUDO que esta nas 3 listas de entrada (mudado ou nao),
    pra quem chama gravar de volta sem perder o registro de quem nao mudou.

    So considera "novo" quando o aviso em si mudou (card entrou na lista,
    ou o alvo/motivo mudou) - card sem quote_id (nao deveria acontecer,
    mas por seguranca) sempre conta como novidade, nunca falha silenciosa.
    """
    avisos_atuais = {}
    planejadas_novas = []
    for item in planejadas:
        aviso = "planejada:%s" % item["coluna_para"]
        quote_id = item.get("quote_id")
        if quote_id:
            avisos_atuais[quote_id] = aviso
        if not quote_id or avisos_anteriores.get(quote_id) != aviso:
            planejadas_novas.append(item)

    def _filtrar(lista, prefixo):
        novos = []
        for quote_id, nome, motivo in lista:
            aviso = "%s:%s" % (prefixo, motivo)
            if quote_id:
                avisos_atuais[quote_id] = aviso
            if not quote_id or avisos_anteriores.get(quote_id) != aviso:
                novos.append((quote_id, nome, motivo))
        return novos

    pendencias_novas = _filtrar(pendencias, "pendencia")
    erros_novos = _filtrar(erros_validacao, "erro")

    return planejadas_novas, pendencias_novas, erros_novos, avisos_atuais


def formatar_iso_z(momento):
    """Inverso de para_datetime: datetime -> ISO em UTC terminando em "Z"
    (formato que o Volly usa nos campos de data). Usada tanto aqui quanto
    em mover_crm_cloud.py, pra nao repetir a mesma formatacao em 3 lugares
    diferentes."""
    return momento.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")


def calcular_agendamento(agora, followup_dias, followup_hora, fuso_brasilia):
    """scheduled_at (ISO UTC) = agora + followup_dias dias, na followup_hora
    (HH:MM:SS) de Brasilia - mesma conta confirmada contra um agendamento
    real (ver spec): moveu 24/08, followup_days=7, followup_time=09:00:00
    -> scheduled_at 2026-08-31T12:00:00Z (09h Brasilia).

    fuso_brasilia: tzinfo de America/Sao_Paulo (injetado pelo chamador,
    que ja tem zoneinfo disponivel - mantem este modulo sem import de
    zoneinfo).
    """
    if followup_dias is None or not followup_hora:
        return None
    hora, minuto, segundo = [int(p) for p in followup_hora.split(":")[:3]]
    data_alvo = (agora.astimezone(fuso_brasilia) + timedelta(days=followup_dias)).date()
    momento_local = datetime(data_alvo.year, data_alvo.month, data_alvo.day,
                             hora, minuto, segundo, tzinfo=fuso_brasilia)
    return formatar_iso_z(momento_local)
