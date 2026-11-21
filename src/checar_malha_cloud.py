"""Checagem pela malha (AeroDataBox), 100% na nuvem - roda no GitHub Actions,
sem o voos.db local e sem o Mac ligado.

E a mesma logica de checar_malha.py (mesmos malha.py/provedor_malha.py/
comparacao.py, sem alteracao), so trocando onde o estado mora: em vez do
SQLite local, tudo isso vive no Supabase do painel web -

    lista de voos ativos ......... tabela voos (espelhada da Volly pela
                                     ingestao, ingestao_cloud.py)
    rotacao (ultima checagem) ..... tabela malha_checagens
    orcamento/cota .............. tabela malha_cota
    achados ...................... tabela historico (origem_local_id fica NULL -
                                     achado nasceu aqui, nao no SQLite)
    o que a malha viu ............ tabela observacoes

Desde 26/09/2026 a malha e so RESERVA do monitor Volly (spec do fluxo na
nuvem, parte 2c): so consulta voo elegivel (ativo, futuro, sem `incompleto`)
que o monitor Volly NAO leu com confianca nas ultimas 12h - com ou sem
--tudo. So o --loc (botao "checar agora") consulta mesmo assim. Cada rodada
grava batimento `malha` pro supervisor.

Como aqui nao ha rodada.py depois para juntar e mandar os alertas, este script
manda o Telegram sozinho, achado por achado, com o mesmo teto de seguranca
(TETO_DE_ALERTAS) que a rodada usa contra bug de comparacao.

Uso:
    python3 src/checar_malha_cloud.py                # a rodada do dia
    python3 src/checar_malha_cloud.py --plano        # mostra o que faria
    python3 src/checar_malha_cloud.py --tudo         # ignora a rotacao (nao
                                                      # a cobertura da Volly)
    python3 src/checar_malha_cloud.py --limite 5     # experimentar barato
    python3 src/checar_malha_cloud.py --loc PNR      # so essa reserva, sem
                                                      # rotacao (botao do painel)
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import batimento
import comparacao
import fusos
import malha
import nuvem_comum
import supabase_rest
from provedor_malha import MalhaIndisponivel, ProvedorMalha

RESERVA_UNIDADES = 40
ORCAMENTO_DIARIO = 20
# Origem propria, separada do "malha" que checar_malha.py usa no Mac: os
# dois rodam no MESMO horario (ver checar-malha.yml, cron "mesmo horario da
# rodada da manha") mas leem/escrevem estados diferentes (SQLite local x
# Supabase, sincronizados so em UMA direcao por sincronizar_web.py). Com
# comparacao.comparar() comparando contra a ULTIMA leitura da fonte (nao
# mais o CRM - ver o motivo la), dois escritores dividindo o mesmo nome de
# origem podiam sobrescrever a baseline um do outro e gerar alerta falso de
# "mudou" quando so a fonte que leu por ultimo mudou. Mesmo raciocinio que
# ja levou checar_latam_cloud.py a usar "portal-latam-cloud".
ORIGEM = "malha-cloud"
ETAPA = "malha"

# Voo que o "Monitorar voo" da Volly (checar_volly_cloud.py) leu ha menos
# disso sai da rodada: a leitura e da MESMA AeroDataBox, so que na cota da
# Volly - a nossa sobra pros voos que ela nao cobre (noturnos, ver
# milhasflow.consultar_status_voo). So conta a origem de verdade, nao a de
# simulacao (senao a malha pararia de cobrir enquanto a Volly so simula).
ORIGEM_VOLLY = "volly-monitor"
HORAS_COBERTO_PELA_VOLLY = 30


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def elegivel(linha, horas_ate_embarque):
    """Trecho que alguma fonte deve checar: ativo, embarque futuro e sem
    `incompleto` (sem numero, numero composto ou sem fuso - marcado pela
    ingestao; spec 2026-09-26, parte 2). Vale pra malha e pro monitor Volly.

    Incompleto sai daqui e nao entra como "sem leitura": o supervisor ja
    lista esses trechos a parte, pelo motivo gravado na ingestao.
    """
    if linha.get("ativo") is False or linha.get("incompleto"):
        return False
    return horas_ate_embarque is not None and horas_ate_embarque >= 0


def voos_ativos(supabase_url, service_key, horizonte_dias):
    """Voos elegiveis dentro do horizonte, agrupados por (numero_voo, data).

    Equivalente a voos_para_checar() de checar_malha.py, so que lendo da
    tabela `voos` do Supabase em vez do CSV do MilhasFlow - espelhada da
    Volly a cada 2h pela ingestao (ingestao_cloud.py).

    Devolve (grupos ordenados por data, fora do horizonte, {chave: dias ate
    o embarque}, incompletos pulados).
    """
    linhas = supabase_rest.select(
        supabase_url, service_key, "voos",
        {"select": "id,localizador,cia,numero_voo,origem,destino,embarque,passageiros,"
                   "incompleto",
         "ativo": "eq.true", "numero_voo": "not.is.null", "embarque": "not.is.null"},
    )
    grupos = {}
    dias_por_chave = {}
    fora_do_horizonte = 0
    incompletos = 0
    for l in linhas:
        horas = fusos.horas_ate(l["embarque"])
        if not elegivel(l, horas):
            if l.get("incompleto") and horas is not None and horas >= 0:
                incompletos += 1
            continue
        antecedencia = horas / 24
        if antecedencia > horizonte_dias:
            fora_do_horizonte += 1
            continue
        voo_crm = dict(l)
        voo_crm.pop("incompleto", None)
        # `embarque` no Supabase e UTC (ver fusos.py); comparar a DATA crua
        # contra a malha (que da hora local) desalinha o calendario sempre
        # que o embarque local cair antes das 3h - mesma conversao que
        # sync.py ja faz pro CSV do Mac (ver checar_latam_cloud.voos_latam).
        voo_crm["embarque_local"] = fusos.texto_local(voo_crm.pop("embarque"), l["origem"])
        # numero no padrao IATA (a API nao acha "1885" cru nem "GOL1549"):
        # a chave e o que vai pra consulta, e o mesmo criterio do monitor Volly
        chave = (comparacao.numero_iata(voo_crm["numero_voo"], voo_crm.get("cia")),
                 voo_crm["embarque_local"][:10])
        grupos.setdefault(chave, []).append(voo_crm)
        atual = dias_por_chave.get(chave)
        if atual is None or antecedencia < atual:
            dias_por_chave[chave] = antecedencia

    ordenado = sorted(grupos.items(), key=lambda i: i[0][1])
    return ordenado, fora_do_horizonte, dias_por_chave, incompletos


def vistos_pela_volly(supabase_url, service_key, horas=HORAS_COBERTO_PELA_VOLLY):
    """ids de voo com leitura confiavel da Volly nas ultimas `horas`.

    So existe observacao `volly-monitor` quando a leitura passou em
    malha.confiavel (ver processar_contratos), entao "tem observacao" ja e
    "leitura confiavel". Em UTC de verdade dos dois lados desde 26/09/2026:
    o `visto_em` gravado e o `desde` daqui mudaram juntos pra agora_utc().
    """
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat(timespec="seconds")
    linhas = supabase_rest.select(
        supabase_url, service_key, "observacoes",
        {"select": "voo_id", "origem": "eq.%s" % ORIGEM_VOLLY, "visto_em": "gte.%s" % desde})
    return {l["voo_id"] for l in linhas}


def grupos_da_rodada(grupos, so_esses, cobertos):
    """Quem a malha consulta nesta rodada (antes da rotacao/orcamento).

    Malha e so reserva (spec 2026-09-26, parte 2c): fica com o grupo que tem
    ao menos um trecho sem leitura confiavel da Volly (`cobertos` = ids com
    observacao volly-monitor nas ultimas 12h) - com ou sem --tudo. Com --loc
    (botao "checar agora") so filtra pelo localizador: quem clicou quer a
    malha tambem, mesmo com a Volly em dia.
    """
    if so_esses:
        return [(chave, voos_crm) for chave, voos_crm in grupos
                if any((v.get("localizador") or "").upper() in so_esses for v in voos_crm)]
    return [(chave, voos_crm) for chave, voos_crm in grupos
            if not all(v["id"] in cobertos for v in voos_crm)]


def cota_malha(supabase_url, service_key):
    linhas = supabase_rest.select(
        supabase_url, service_key, "malha_cota", {"select": "*", "id": "eq.1"})
    return linhas[0] if linhas else None


def observado_antes(supabase_url, service_key, origem=ORIGEM):
    """{voo_id: {"partida", "rota"}} - a ULTIMA leitura da malha, ANTES desta
    rodada sobrescrever. Baseline que comparacao.comparar() usa no lugar do
    CRM para horario_alterado/rota_alterada (ver o motivo no docstring dela).
    """
    linhas = supabase_rest.select(
        supabase_url, service_key, "observacoes",
        {"select": "voo_id,partida,rota,situacao", "origem": "eq.%s" % origem})
    return {l["voo_id"]: l for l in linhas}


def checagens_de_malha(supabase_url, service_key):
    linhas = supabase_rest.select(
        supabase_url, service_key, "malha_checagens", {"select": "chave,ultima"})
    resultado = {}
    for l in linhas:
        numero, _, data = l["chave"].partition("|")
        resultado[(numero, data)] = l["ultima"]
    return resultado


def unidades_malha_hoje(supabase_url, service_key, unidades_por_consulta, hoje):
    linhas = supabase_rest.select(
        supabase_url, service_key, "malha_checagens",
        {"select": "chave", "ultima": "eq.%s" % hoje})
    return len(linhas) * unidades_por_consulta


def marcar_checagem_malha(supabase_url, service_key, numero_voo, data, hoje):
    supabase_rest.upsert(
        supabase_url, service_key, "malha_checagens",
        [{"chave": "%s|%s" % (numero_voo, data), "ultima": hoje, "vezes": 1}],
        "chave",
    )


def salvar_cota_malha(supabase_url, service_key, restantes, limite, reset_em):
    supabase_rest.upsert(
        supabase_url, service_key, "malha_cota",
        [{"id": 1, "restantes": restantes, "limite": limite, "reset_em": reset_em,
          "visto_em": nuvem_comum.agora_utc()}],
        "id",
    )


def checar_um(numero, data, voos_crm, provedor, supabase_url, service_key,
              hoje, baseline, do_pdf):
    """Consulta e processa um (numero_voo, data): grava observacao/achado se
    conferivel, e monta os itens de alerta prontos pro Telegram.

    Devolve (situacao, alertas_novos) - situacao e "ok"/"falha"/"parcial".
    MalhaIndisponivel sobe direto: e parada de cota (decisao do chamador,
    que interrompe a rodada), nao falha deste item so.
    """
    contratos, erro = provedor.voo(numero, data)
    if erro:
        print("       falhou: %s" % erro)
        return "falha", []

    marcar_checagem_malha(supabase_url, service_key, numero, data, hoje)

    # a comparacao casa numero+data: o CRM "1885" contra "G3 1885" da API
    # viraria "ausente na companhia" falso (mesmo ajuste do monitor Volly)
    # `composto`: conexao num trecho so ("TP1930 + TP1928") - o primeiro voo
    # nao chega ao destino do trecho, rota diferente ali nao e remanejamento
    voos_crm = [dict(v, numero_voo=numero, composto="+" in (v.get("numero_voo") or ""))
                for v in voos_crm]

    return processar_contratos(contratos, voos_crm, supabase_url, service_key,
                               baseline, do_pdf,
                               achados_extras=comparacao.trecho_diferente_da_venda)


def processar_contratos(contratos, voos_crm, supabase_url, service_key,
                        baseline, do_pdf, origem=ORIGEM, gravar_achados=True,
                        achados_extras=None, ja_avisados=None, visto_em=None):
    """Resposta crua da AeroDataBox -> observacao gravada + alertas.

    Separado de checar_um porque o "Monitorar voo" da Volly guarda a MESMA
    resposta crua (flight_status_snapshots.raw) - checar_volly_cloud.py usa
    este mesmo caminho com a sua propria `origem` (baseline propria).

    `gravar_achados=False` (simulacao): grava so a observacao (baseline da
    propria origem) e devolve os achados sem tocar em historico/Telegram.

    `achados_extras(segmento, voos_crm)`: checagens a mais da fonte (a Volly
    confere venda x companhia). `ja_avisados`: {(voo_id, tipo, detalhe)} a
    tirar antes de gravar - opcional desde 26/09/2026, porque o dedupe da
    mesma fonte agora e de nuvem_comum.gravar_achado.

    `visto_em`: quando a leitura foi FEITA de verdade (ex.: `fetched_at` do
    snapshot da Volly). Default agora_utc() - certo pra malha, que consulta
    a API na hora. O monitor Volly le cache as vezes com 10-20h (revisao de
    27/09/2026: sem isso a `observacoes.visto_em` mentia "agora" com snapshot
    velho, e a malha parava de cobrir o voo achando que a Volly acabou de
    olhar).

    Devolve (situacao, itens) - situacao e "ok"/"falha"/"alerta"; itens sao
    os alertas prontos pro Telegram (ou os achados crus, na simulacao).
    """
    leitura = malha.ler_resposta(contratos)
    if not leitura["encontrada"]:
        print("       %s" % leitura["motivo"])
        return "falha", []

    segmento, motivo = malha.escolher(leitura, voos_crm[0])
    if segmento is None:
        print("       %s" % motivo)
        return "falha", []

    achados = []
    for voo in voos_crm:
        achados += malha.achados_de_status(segmento, voo)
    if achados_extras:
        achados += achados_extras(segmento, voos_crm)

    pode, porque = malha.confiavel(segmento)
    if pode:
        # Compara ANTES de gravar: usa a leitura ANTERIOR da malha
        # (baseline) e so depois essa leitura de hoje sobrescreve.
        achados += comparacao.comparar(
            {"segmentos": [segmento], "segmentos_nao_expandidos": 0},
            voos_crm, baseline)
        for voo_id, partida, rota, situacao in comparacao.observacoes_da_leitura(
                {"segmentos": [segmento]}, voos_crm):
            supabase_rest.upsert(
                supabase_url, service_key, "observacoes",
                [{"voo_id": voo_id, "origem": origem, "partida": partida,
                  "rota": rota, "situacao": situacao,
                  "visto_em": visto_em or nuvem_comum.agora_utc()}],
                "voo_id,origem",
            )
    else:
        print("       leitura parcial (%s) - so status explicito" % porque)

    relevantes = [a for a in achados if a["voo_crm"]]
    # voo que mudou de data tambem "some" da data antiga - o mesmo fato
    # viraria dois alertas (data_alterada + ausente_na_companhia)
    remarcados = {a["voo_crm"]["id"] for a in relevantes if a["tipo"] == "data_alterada"}
    relevantes = [a for a in relevantes
                  if not (a["tipo"] == "ausente_na_companhia" and a["voo_crm"]["id"] in remarcados)]
    if ja_avisados:
        relevantes = [a for a in relevantes
                      if (a["voo_crm"]["id"], a["tipo"], a["detalhe"]) not in ja_avisados]
    if not relevantes:
        return "ok", []

    if not gravar_achados:
        for a in relevantes:
            print("       ALERTA [%s] %s" % (a["tipo"], a["detalhe"][:70]))
        return "alerta", relevantes

    # dedupe da mesma fonte e confirmacao entre fontes ficam em
    # nuvem_comum.gravar_achado (26/09/2026) - achado repetido ou ja visto
    # por outra fonte nao volta como alerta
    alertas_novos = []
    for a in relevantes:
        item = nuvem_comum.gravar_achado(supabase_url, service_key, a, origem, do_pdf)
        if item:
            alertas_novos.append(item)

    return ("alerta" if alertas_novos else "ok"), alertas_novos


# Saldo guardado mais velho que isso, e baixo demais pra pagar uma consulta,
# nao vale mais como prova de cota esgotada (ver cota_vigente).
DIAS_SALDO_VELHO = 1


def cota_vigente(cota, agora=None):
    """(saldo guardado, motivo): a cota de `malha_cota` so se for confiavel.

    O saldo e atualizado so por quem chama a API (cabecalhos de resposta).
    Em 29/09/2026 ele ficou em 41 unidades (piso 40, consulta de 2): o
    orcamento deu 1, nenhuma consulta coube, e como nenhuma chamada era feita
    o saldo nunca mais se atualizou - a malha ficou 18 dias sem consultar,
    mesmo com o ciclo renovado em 30/09. Por isso o saldo guardado e
    descartado (None) quando:
      - o ciclo ja renovou (`reset_em` passou): o saldo e do ciclo anterior;
      - esta velho e nao paga nem uma consulta: sem uma chamada nao ha como
        saber o saldo real. Com None o orcamento volta ao padrao, a primeira
        consulta traz o saldo de verdade e o piso (RESERVA_UNIDADES) protege
        a cota na propria rodada.
    """
    if not cota or cota.get("restantes") is None:
        return None, None
    agora = agora or datetime.now(timezone.utc)
    reset = nuvem_comum._instante(cota.get("reset_em"))
    if reset is not None and reset <= agora:
        return None, "ciclo da cota renovou em %s; o saldo guardado e do ciclo anterior" % (
            reset.strftime("%d/%m"))
    visto = nuvem_comum._instante(cota.get("visto_em"))
    sobra = max(0, cota["restantes"] - RESERVA_UNIDADES)
    if (visto is not None and agora - visto > timedelta(days=DIAS_SALDO_VELHO)
            and sobra < malha.UNIDADES_POR_CONSULTA):
        return None, ("saldo de %d unidades guardado em %s nao paga nem uma consulta; "
                      "a proxima chamada confere o saldo real" % (
                          cota["restantes"], visto.strftime("%d/%m")))
    return cota, None


def orcamento_do_dia(cota, agora=None):
    dias = malha.DIAS_DO_CICLO
    agora = agora or datetime.now(timezone.utc)
    cota, descartada = cota_vigente(cota, agora)
    if cota is None:
        return ORCAMENTO_DIARIO, "padrao (%s)" % (
            descartada or "a API ainda nao informou saldo")
    restantes = cota["restantes"]
    reset = nuvem_comum._instante(cota.get("reset_em"))
    if reset is not None:
        dias = max(1, (reset - agora).days + 1)
    disponivel = max(0, restantes - RESERVA_UNIDADES)
    return (int(disponivel / dias),
            "saldo real %d - reserva %d, em %d dia(s) ate renovar"
            % (restantes, RESERVA_UNIDADES, dias))


def main():
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    tudo = "--tudo" in sys.argv
    plano = "--plano" in sys.argv
    # --loc PNR[,PNR]: so essa(s) reserva(s), sem rotacao nem orcamento - e o
    # que o botao "checar agora" do painel dispara (ver
    # .github/workflows/checar-malha.yml). Mesmo uso de checar_gol.py/
    # checar_azul.py/checar_latam.py.
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}
        tudo = True

    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    malha_url = _obrigatorio("MALHA_API_URL").rstrip("/")
    malha_header = _obrigatorio("MALHA_API_HEADER")
    malha_key = _obrigatorio("MALHA_API_KEY")

    fusos.carregar_aprendidos(supabase_url, service_key)

    if plano:
        # sem batimento: simulacao nao pode contar pro supervisor como
        # malha que rodou (mesma regra de ingestao_cloud.py)
        rodar(supabase_url, service_key, malha_url, malha_header, malha_key,
              batimento.Rodada(), limite, tudo, plano, so_esses)
        return
    with batimento.rodada(supabase_url, service_key, ETAPA) as b:
        rodar(supabase_url, service_key, malha_url, malha_header, malha_key,
              b, limite, tudo, plano, so_esses)


def rodar(supabase_url, service_key, malha_url, malha_header, malha_key,
          b, limite, tudo, plano, so_esses):
    """A rodada em si. `b` (batimento.Rodada) recebe lidos/alertas/falhas e
    o detalhe que o supervisor le."""
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    horizonte = int(os.environ.get("MALHA_DIAS", "120"))

    provedor = ProvedorMalha(malha_url, malha_header, malha_key)

    # baseline da comparacao: o que a malha viu da ULTIMA vez, nao o CRM (ver
    # o motivo em comparacao.comparar). Buscado uma vez so, antes de qualquer
    # upsert desta rodada sobrescrever.
    baseline = observado_antes(supabase_url, service_key)
    # links de consulta prontos, sincronizados pelo Mac (ver
    # nuvem_comum.links_pdf_do_supabase)
    do_pdf = nuvem_comum.links_pdf_do_supabase(supabase_url, service_key)

    grupos, fora, dias_por_chave, incompletos = voos_ativos(
        supabase_url, service_key, horizonte)
    print("Voos futuros no horizonte ..... %d" % len(grupos))
    if fora:
        print("Fora do horizonte (%d dias) ... %d" % (horizonte, fora))
    if incompletos:
        print("Incompletos (nao checaveis) ... %d" % incompletos)

    # reserva da Volly: com ou sem --tudo, voo que o monitor Volly leu com
    # confianca nas ultimas 12h sai da rodada (ver grupos_da_rodada)
    cobertos = set() if so_esses else vistos_pela_volly(supabase_url, service_key)
    antes = len(grupos)
    grupos = grupos_da_rodada(grupos, so_esses, cobertos)
    if so_esses and not grupos:
        print("Nenhum localizador bate com %s" % ", ".join(sorted(so_esses)))
        sys.exit(1)
    if not so_esses:
        b.detalhe["cobertos_pela_volly"] = antes - len(grupos)
        if antes - len(grupos):
            print("Cobertos pela Volly (<%dh) .... %d" % (
                HORAS_COBERTO_PELA_VOLLY, antes - len(grupos)))
    b.detalhe["elegiveis_sem_volly"] = len(grupos)
    b.detalhe["incompletos"] = incompletos

    hoje = datetime.now().strftime("%Y-%m-%d")
    cota = cota_malha(supabase_url, service_key)
    orcamento, porque = orcamento_do_dia(cota)
    print("Orcamento de hoje ............. %d unidades (%s)" % (orcamento, porque))
    b.detalhe["orcamento"] = orcamento

    if tudo:
        print("Rotacao ignorada (--tudo) ..... %d consultas" % len(grupos))
    else:
        gasto_hoje = unidades_malha_hoje(
            supabase_url, service_key, malha.UNIDADES_POR_CONSULTA, hoje)
        se_sobra = max(0, orcamento - gasto_hoje)
        if gasto_hoje:
            print("Ja gasto hoje ................. %d unidades (sobram %d)"
                  % (gasto_hoje, se_sobra))

        ultimas = checagens_de_malha(supabase_url, service_key)
        candidatos = [{"chave": chave, "dias": dias_por_chave.get(chave),
                       "ultima": ultimas.get(chave)} for chave, _ in grupos]

        faixas, diag = malha.ajustar_faixas(candidatos, orcamento)
        print("Faixas ....................... %s  (fator %.2f)" % (
            " / ".join("<=%s:%dd" % (l if l else "+", i) for l, i in faixas),
            diag["fator"]))

        escolhidos, relatorio = malha.priorizar(
            candidatos, orcamento_unidades=se_sobra, faixas=faixas)
        ordem = {chave: i for i, chave in enumerate(escolhidos)}
        grupos = sorted([g for g in grupos if g[0] in ordem],
                        key=lambda g: ordem[g[0]])
        print("Ainda no prazo da rotacao ..... %d" % relatorio.get("ainda_no_prazo", 0))
        if relatorio.get("sem_orcamento"):
            print("Adiados por orcamento ......... %d" % relatorio["sem_orcamento"])
            b.detalhe["adiados_por_orcamento"] = relatorio["sem_orcamento"]

    if limite is not None:
        grupos = grupos[:limite]
    print("Vou consultar ................. %d  (%d unidades, orcamento %d)\n"
          % (len(grupos), len(grupos) * malha.UNIDADES_POR_CONSULTA, orcamento))

    if plano:
        for (numero, data), _ in grupos:
            print("   %-10s %s" % (numero, data))
        print("\n(--plano: nada foi consultado nem gravado)")
        return

    ok = alertas_qtd = falhas = lidos = 0
    alertas_para_enviar = []
    interrompida = None

    for i, ((numero, data), voos_crm) in enumerate(grupos, 1):
        saldo = provedor.unidades_restantes
        if saldo is not None and saldo < RESERVA_UNIDADES:
            interrompida = "cota chegou a %d unidades (piso %d)" % (saldo, RESERVA_UNIDADES)
            print("\n>>> %s" % interrompida)
            break

        print("[%d/%d] %s  %s" % (i, len(grupos), numero, data))
        try:
            situacao, alertas_novos = checar_um(
                numero, data, voos_crm, provedor, supabase_url, service_key,
                hoje, baseline, do_pdf)
        except MalhaIndisponivel as e:
            print("\nERRO: %s" % e)
            interrompida = str(e)
            break
        except Exception as e:
            # um item ruim (Supabase soluco etc) nao pode derrubar o resto
            # da rodada nem os alertas ja detectados antes dele.
            print("       erro inesperado: %s" % str(e)[:150])
            falhas += 1
            continue

        if situacao == "falha":
            falhas += 1
        elif situacao == "alerta":
            lidos += 1
            alertas_para_enviar += alertas_novos
            alertas_qtd += len(alertas_novos)
        else:
            lidos += 1
            ok += 1

    if provedor.unidades_restantes is not None:
        reset_em = None
        dias_reset = provedor.dias_para_reset()
        if dias_reset:
            reset_em = (datetime.now() + timedelta(days=dias_reset)).isoformat(timespec="seconds")
        salvar_cota_malha(supabase_url, service_key,
                          provedor.unidades_restantes, provedor.unidades_limite, reset_em)

    b.lidos = lidos
    b.alertas = alertas_qtd
    b.falhas = falhas
    b.detalhe["chamadas"] = provedor.chamadas
    b.detalhe["cota_restante"] = provedor.unidades_restantes
    if interrompida:
        b.detalhe["interrompida"] = interrompida

    print("\n" + "=" * 62)
    print("  chamadas HTTP ............... %d" % provedor.chamadas)
    print("  conferidos sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d" % alertas_qtd)
    print("  falharam .................... %d" % falhas)
    print("=" * 62)
    if interrompida:
        print("\n  RODADA INTERROMPIDA: %s" % interrompida)

    # Junta com o que ficou pendente de uma rodada anterior (Telegram falhou,
    # token errado etc), respeita o teto de seguranca e manda pro Telegram -
    # logica comum aos checadores de nuvem (ver nuvem_comum.enviar_alertas).
    enviado, motivo = nuvem_comum.enviar_alertas(
        supabase_url, service_key, telegram_token, telegram_chat,
        alertas_para_enviar, ORIGEM, "Voos com alteração (malha)", do_pdf)
    if enviado is None:
        pass
    elif enviado:
        print("\n>>> Telegram: enviado")
    else:
        print("\n>>> Telegram: %s" % motivo)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("A checagem de malha (nuvem)", erro)
        sys.exit(1)
