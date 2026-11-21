"""Pecas comuns aos checadores que rodam 100% na nuvem (GitHub Actions, sem
Mac): checar_malha_cloud.py, checar_volly_cloud.py e os portais
checar_{latam,gol,azul}_cloud.py.

Extraido de checar_malha_cloud.py quando o segundo checador de nuvem
apareceu - as duas fontes usam exatamente a mesma logica de link/retry/
envio, so o `origem` no historico/observacoes muda. Desde 26/09/2026 tambem
o unico ponto de insert em `historico` (gravar_achado: dedupe + confirmacao
entre fontes) e o teto sem prender do Telegram (enviar_alertas).
"""

import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import alertas
import painel
import qualidade
import supabase_rest

def agora_utc():
    """Instante atual em ISO com fuso de verdade (UTC).

    O padrao antigo `datetime.now().isoformat() + "-03:00"` so estava certo
    no Mac: o runner do GitHub Actions roda em UTC, entao o horario gravado
    ficava 3h no futuro. Todo timestamp novo gravado da nuvem usa isto.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# URL publica do painel (Vercel), so para montar o link "ver no painel" que
# vai no alerta - nao e segredo, por isso tem default em vez de exigir
# variavel de ambiente igual SUPABASE_WEB_URL etc.
PAINEL_WEB_URL = os.environ.get("PAINEL_WEB_URL", "https://lf-viagens-admin.vercel.app").rstrip("/")

# Teto contra enxurrada (spec do fluxo na nuvem, parte 3): acima disso numa
# rodada o Telegram so recebe um aviso de "segurado" e os alertas ficam na
# aba Urgente. Era 15 (mesmo de rodada.py, incidente de 68 alertas falsos em
# 29/07/2026); subiu pra 30 em 26/09/2026 porque a primeira rodada real do
# monitor Volly ja tinha 16 divergencias venda x companhia legitimas - e
# segurar nao prende mais nada (ver enviar_alertas).
TETO_DE_ALERTAS = 30

# Alertas por mensagem do Telegram. Mensagem maior que 4000 caracteres e
# cortada (alertas.enviar_telegram), entao o bloco tambem fecha antes disso.
TAMANHO_BLOCO = 25
CARACTERES_POR_MENSAGEM = 3800

# Segurado sai sozinho depois disso, mesmo sem ninguem liberar no site -
# alerta nunca fica preso (spec, parte 3).
HORAS_SEGURADO = 24
CHAVE_SEGURADO = "telegram_segurado"
CHAVE_LIBERADO = "telegram_liberado"   # gravada pela RPC liberar_alertas_segurados

# Mesma mudanca vista por duas fontes (ex.: Volly e portal LATAM) e UM alerta
# so (spec, parte 3): a segunda fonte grava `confirmado`, sem Telegram. O
# "mesmo fato" e por grupo, nao por tipo exato - a Volly acusa
# horario_venda_diverge e o portal acusa horario_alterado pra mesma mudanca
# de horario. Tipo fora daqui (sem_confirmacao, status_desconhecido,
# em_contingencia...) sempre alerta por conta propria.
GRUPO_ALERTA = {
    "horario_alterado": "horario", "alterado_pela_companhia": "horario",
    "horario_venda_diverge": "horario", "data_alterada": "horario",
    "alteracao_voo": "horario",
    "trecho_cancelado": "cancelamento", "possivel_cancelamento": "cancelamento",
    "cancelamento": "cancelamento", "reserva_perdida": "cancelamento",
    "ausente_na_companhia": "cancelamento", "sem_voo_no_trecho": "cancelamento",
    "rota_alterada": "rota", "voo_desviado": "rota", "passageiro_remanejado": "rota",
    "atraso": "atraso",
}
HORAS_CONFIRMACAO = 48
DIAS_LEMBRETE_CANCELAMENTO = 2

# Origem do sync do Mac com o CRM: evento dela nao e alerta (web/lib/tipos.ts
# ehAlerta), entao tambem nao pode ser "confirmado" por outra fonte.
ORIGEM_CRM = "milhasflow"


def links_pdf_do_supabase(supabase_url, service_key):
    """{localizador: url} sincronizado pelo Mac (ver
    sincronizar_web.links_pdf_para_sincronizar).

    Quem roda no GitHub Actions nao tem acesso a pasta de PDFs nem ao
    vinculos_latam.json do Mac - por isso o link da LATAM (que exige o
    numero de compra) so aparece aqui depois que uma rodada do Mac ja
    sincronizou. GOL/Azul nao dependem disso: painel.link_para monta o
    link deles so com o CRM quando esta tabela nao tem a reserva.
    """
    linhas = supabase_rest.select(
        supabase_url, service_key, "links_pdf", {"select": "localizador,url"})
    return {l["localizador"].upper(): l["url"] for l in linhas if l.get("url")}


def enriquecer_com_link(item, do_pdf=None):
    """Acrescenta passageiro e os dois links prontos ao item: o da reserva na
    companhia (PDF sincronizado do Mac > montado so com o CRM - mesma logica
    do painel local) e o da mesma reserva no nosso painel.
    """
    voo = {"cia": item.get("cia"), "localizador": item.get("localizador"),
           "origem": item.get("origem"), "numero_voo": item.get("numero_voo"),
           "sobrenome": qualidade.sobrenome(item.get("passageiros")),
           "sobrenome_completo": qualidade.sobrenome_completo(item.get("passageiros"))}
    link, _fonte_link = painel.link_para(voo, do_pdf or {})
    item["passageiro"] = qualidade.primeiro_passageiro(item.get("passageiros"))
    item["link"] = link
    item["link_painel"] = alertas.link_painel(PAINEL_WEB_URL, item.get("id"))
    return item


def _instante(texto):
    """timestamptz do PostgREST -> datetime com fuso. None se ilegivel.

    Python 3.9 (Mac) nao aceita "Z" nem fracao de segundo com 1-5 digitos,
    que o PostgREST devolve (ex.: .12345) - normaliza antes.
    """
    if not texto:
        return None
    try:
        t = str(texto).replace("Z", "+00:00").replace(" ", "T", 1)
        m = re.match(r"^(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(.*)$", t)
        if m and m.group(2):
            t = "%s.%s%s" % (m.group(1), m.group(2)[:6].ljust(6, "0"), m.group(3))
        instante = datetime.fromisoformat(t)
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante


def _agora(agora=None):
    return agora or datetime.now(timezone.utc)


def embarca_em_ate(embarque_local, dias, agora=None):
    """True se o embarque ('AAAA-MM-DD HH:MM', hora local) cai ate `dias`
    dias a partir de hoje (data de Brasilia). Rodada de fim de tarde dos
    portais (portais.yml, 23/10/2026): so as reservas que embarcam logo."""
    if not embarque_local:
        return False
    hoje_br = _agora(agora) - timedelta(hours=3)
    return embarque_local[:10] <= (hoje_br + timedelta(days=dias)).strftime("%Y-%m-%d")


def decidir_achado(linhas_do_voo, tipo, detalhe, origem, agora=None):
    """O que fazer com um achado desta fonte, dado o historico do voo.

    Devolve (decisao, outra_origem):
      ("duplicado", None) - esta fonte ja gravou (voo, tipo, detalhe): o mesmo
          fato nao volta a alertar a cada rodada (era o `ja_avisados` do
          monitor Volly; os portais e a malha nao tinham e repetiam status
          como "cancelado" toda rodada);
      ("confirmado", origem) - outra fonte tem alerta pendente do MESMO grupo
          (GRUPO_ALERTA) nas ultimas HORAS_CONFIRMACAO: e o mesmo fato visto
          de novo, entra no site como fonte adicional, sem Telegram;
      ("alterado", None) - alerta novo.
    """
    for l in linhas_do_voo:
        if (l.get("origem") == origem and l.get("campo") == tipo
                and (l.get("valor_novo") or "") == (detalhe or "")):
            return "duplicado", None
    grupo = GRUPO_ALERTA.get(tipo)
    if not grupo:
        return "alterado", None
    limite = _agora(agora) - timedelta(hours=HORAS_CONFIRMACAO)
    for l in linhas_do_voo:
        if (l.get("evento") != "alterado" or l.get("resolvido")
                or l.get("origem") in (origem, ORIGEM_CRM)
                or GRUPO_ALERTA.get(l.get("campo")) != grupo):
            continue
        quando = _instante(l.get("detectado_em"))
        if quando is not None and quando >= limite:
            return "confirmado", l.get("origem")
    return "alterado", None


def gravar_achado(supabase_url, service_key, achado, origem, do_pdf=None, agora=None):
    """Unico ponto de insert em `historico` dos checadores de nuvem (malha,
    monitor Volly, portais LATAM/GOL/Azul).

    `achado`: {"tipo", "detalhe", "voo_crm"} como malha/comparacao/latam/gol/
    azul devolvem. Aplica o dedupe da mesma fonte e a confirmacao entre
    fontes (ver decidir_achado) e devolve o item pronto pro Telegram - ou
    None quando nao ha o que avisar (duplicado ou confirmacao).
    """
    voo = achado["voo_crm"]
    tipo, detalhe = achado["tipo"], achado["detalhe"]
    # Voo que sumiu volta a alertar perto do embarque, mesmo ja verificado:
    # TSTACX (G3 1885) ficou de 18 a 30/10/2026 sem voo e o dedupe calou.
    if (GRUPO_ALERTA.get(tipo) == "cancelamento"
            and embarca_em_ate(voo.get("embarque_local"), DIAS_LEMBRETE_CANCELAMENTO, agora)):
        detalhe += " (embarca em até %d dias)" % DIAS_LEMBRETE_CANCELAMENTO
    linhas = supabase_rest.select(
        supabase_url, service_key, "historico",
        {"select": "id,campo,valor_novo,origem,evento,resolvido,detectado_em",
         "voo_id": "eq.%s" % voo["id"]})
    decisao, outra = decidir_achado(linhas, tipo, detalhe, origem, agora)
    if decisao == "duplicado":
        print("       ja avisado [%s] %s" % (tipo, detalhe[:60]))
        return None

    confirmado = decisao == "confirmado"
    gravado = supabase_rest.inserir(supabase_url, service_key, "historico", {
        "voo_id": voo["id"], "evento": "confirmado" if confirmado else "alterado",
        "campo": tipo, "valor_novo": detalhe, "origem": origem,
        "detectado_em": agora_utc(),
        # confirmacao nao vai pro Telegram: ja nasce notificada, senao o
        # supervisor a veria como "pendente de Telegram"
        "notificado": confirmado,
    })
    if confirmado:
        print("       confirma alerta de %s [%s] %s" % (outra, tipo, detalhe[:50]))
        return None

    print("       ALERTA [%s] %s" % (tipo, detalhe[:70]))
    item = dict(voo)
    item["tipo"] = tipo
    item["detalhe"] = "%s %s" % (item.get("numero_voo") or "?", detalhe)
    item["historico_id"] = gravado["id"] if gravado else None
    return enriquecer_com_link(item, do_pdf)


def pendentes_de_notificar(supabase_url, service_key, origem, do_pdf=None):
    """Achados desta fonte que ja foram gravados mas o Telegram nao confirmou
    envio (rodada anterior travou, token errado, teto segurou). Reentram no
    lote de hoje, igual rodada.py faz com `alertas_pendentes` - sem isso um
    alerta que falhou de enviar fica perdido para sempre, porque este script
    nao tem uma rodada seguinte que o revisite (ao contrario do voos.db local).

    Cada item leva `resolvido`: quem ja foi verificado no site enquanto
    esperava nao precisa mais sair no Telegram (ver enviar_alertas).
    """
    linhas = supabase_rest.select(
        supabase_url, service_key, "historico",
        {"select": "id,campo,valor_novo,resolvido,"
                   "voos(id,localizador,cia,numero_voo,origem,passageiros)",
         "origem": "eq.%s" % origem, "evento": "eq.alterado", "notificado": "eq.false"},
    )
    itens = []
    for l in linhas:
        voo = l.get("voos") or {}
        item = {
            "historico_id": l["id"], "id": voo.get("id"),
            "localizador": voo.get("localizador"), "cia": voo.get("cia"),
            "numero_voo": voo.get("numero_voo"), "origem": voo.get("origem"),
            "passageiros": voo.get("passageiros"), "tipo": l["campo"],
            "detalhe": "%s %s" % (voo.get("numero_voo") or "?", l["valor_novo"] or ""),
            "resolvido": bool(l.get("resolvido")),
        }
        itens.append(enriquecer_com_link(item, do_pdf))
    return itens


def marcar_notificados(supabase_url, service_key, historico_ids):
    ids = [str(h) for h in historico_ids if h]
    # um PATCH por lote (id=in.(...)) em vez de um por alerta: a liberacao
    # de um segurado pode ter dezenas de uma vez
    for i in range(0, len(ids), 100):
        supabase_rest.atualizar(
            supabase_url, service_key, "historico",
            {"id": "in.(%s)" % ",".join(ids[i:i + 100])}, {"notificado": True})


def ler_estado_telegram(supabase_url, service_key):
    """(linha telegram_segurado, linha telegram_liberado) de supervisor_estado,
    cada uma None se nao existir."""
    linhas = supabase_rest.select(
        supabase_url, service_key, "supervisor_estado",
        {"select": "chave,aberto_em,avisado_em,detalhe",
         "chave": "in.(%s,%s)" % (CHAVE_SEGURADO, CHAVE_LIBERADO)})
    por_chave = {l["chave"]: l for l in linhas}
    return por_chave.get(CHAVE_SEGURADO), por_chave.get(CHAVE_LIBERADO)


def _origens_seguradas(segurado):
    return dict(((segurado or {}).get("detalhe") or {}).get("origens") or {})


def decidir_envio(quantidade, origem, segurado, liberado, teto=TETO_DE_ALERTAS, agora=None):
    """O que fazer com os `quantidade` alertas desta origem nesta rodada.

    "enviar" - abaixo do teto e nada segurado desta origem;
    "segurar_avisando" - passou do teto agora: manda o aviso UMA vez;
    "segurar" - ja segurado e avisado: nao repete o aviso a cada rodada;
    "liberar" - estava segurado e alguem liberou no site depois que segurou
        (telegram_liberado mais novo) ou ja faz HORAS_SEGURADO: manda tudo.

    O segurado e por origem (detalhe.origens = {origem: desde}) porque cada
    checador so reenvia os pendentes da propria origem: um so `aberto_em`
    global deixaria a enxurrada de uma fonte liberar/prender a de outra.
    """
    desde = _instante(_origens_seguradas(segurado).get(origem))
    if desde is None:
        return "segurar_avisando" if quantidade > teto else "enviar"
    liberado_em = _instante((liberado or {}).get("aberto_em"))
    if liberado_em is not None and liberado_em > desde:
        return "liberar"
    if _agora(agora) - desde >= timedelta(hours=HORAS_SEGURADO):
        return "liberar"
    return "segurar"


def registrar_segurado(supabase_url, service_key, segurado, origem, quantidade):
    """Grava (ou acrescenta a origem em) telegram_segurado - e a linha que faz
    o botao "Liberar alertas segurados" aparecer na aba Urgente."""
    agora = agora_utc()
    origens = _origens_seguradas(segurado)
    origens[origem] = agora
    qtds = dict(((segurado or {}).get("detalhe") or {}).get("quantidades") or {})
    qtds[origem] = quantidade
    supabase_rest.upsert(supabase_url, service_key, "supervisor_estado", [{
        "chave": CHAVE_SEGURADO,
        "aberto_em": (segurado or {}).get("aberto_em") or agora,
        "avisado_em": agora,
        "detalhe": {"origens": origens, "quantidades": qtds},
    }], "chave")


def soltar_segurado(supabase_url, service_key, segurado, origem):
    """Tira a origem do segurado; sem mais nenhuma, apaga a linha (o botao
    some do site)."""
    origens = _origens_seguradas(segurado)
    origens.pop(origem, None)
    qtds = dict(((segurado or {}).get("detalhe") or {}).get("quantidades") or {})
    qtds.pop(origem, None)
    if not origens:
        _apagar_estado(supabase_url, service_key, CHAVE_SEGURADO)
        return
    supabase_rest.upsert(supabase_url, service_key, "supervisor_estado", [{
        "chave": CHAVE_SEGURADO, "aberto_em": min(origens.values()),
        "avisado_em": (segurado or {}).get("avisado_em"),
        "detalhe": {"origens": origens, "quantidades": qtds},
    }], "chave")


def _apagar_estado(supabase_url, service_key, chave):
    # supabase_rest nao tem DELETE (nenhum outro script apaga nada); fica
    # aqui, restrito a supervisor_estado
    req = urllib.request.Request(
        supabase_url.rstrip("/") + "/rest/v1/supervisor_estado?" +
        urllib.parse.urlencode({"chave": "eq.%s" % chave}),
        method="DELETE",
        headers={"apikey": service_key, "Authorization": "Bearer " + service_key,
                 "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


def _gravidade(item):
    return 0 if alertas.ICONE.get(item.get("tipo")) == "🔴" else 1


def blocos_de_mensagem(itens, tamanho=TAMANHO_BLOCO, caracteres=CARACTERES_POR_MENSAGEM):
    """Parte os alertas em blocos de ate `tamanho`, fechando o bloco antes
    se o texto passar de `caracteres` (links longos da companhia estouram o
    limite do Telegram bem antes de 25 alertas). Vermelhos primeiro."""
    blocos, atual, tam = [], [], 0
    for item in sorted(itens, key=_gravidade):
        n = len(alertas.formatar_alerta(item)) + 1
        if atual and (len(atual) >= tamanho or tam + n > caracteres):
            blocos.append(atual)
            atual, tam = [], 0
        atual.append(item)
        tam += n
    if atual:
        blocos.append(atual)
    return blocos


def _hora_brasilia():
    # o runner do Actions e UTC; datetime.now() daria a hora 3h adiantada
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M")


def enviar_em_blocos(supabase_url, service_key, telegram_token, telegram_chat,
                     itens, titulo):
    """Manda os alertas em mensagens de ate TAMANHO_BLOCO e marca notificado
    bloco a bloco - se um bloco falhar, os seguintes ficam pendentes pra
    proxima rodada, sem perder os que ja sairam."""
    blocos = blocos_de_mensagem(itens)
    for n, bloco in enumerate(blocos, 1):
        cabecalho = "⚠️ %s — %s" % (titulo, _hora_brasilia())
        if len(blocos) > 1:
            cabecalho += " (%d/%d)" % (n, len(blocos))
        ok_envio, erro = alertas.enviar_telegram(
            telegram_token, telegram_chat, alertas.montar_mensagem(bloco, cabecalho))
        if not ok_envio:
            return False, erro
        marcar_notificados(supabase_url, service_key, [a.get("historico_id") for a in bloco])
    return True, None


def _link_urgente():
    return "%s/urgente" % PAINEL_WEB_URL


def texto_segurado(titulo, quantidade, teto):
    link = _link_urgente()
    return ("⚠️ <b>%s segurada</b>\n\n%d alertas de uma vez — acima do teto de %d.\n"
            "Nada foi disparado aqui; estão todos na aba Urgente: "
            '<a href="%s">%s</a>\n\n'
            "Saem sozinhos em %dh, ou antes se alguém clicar em "
            "\"Liberar alertas segurados\" na aba Urgente."
            % (titulo, quantidade, teto, link, link, HORAS_SEGURADO))


def _juntar_pendentes(supabase_url, service_key, alertas_para_enviar, origem, do_pdf):
    """Novos desta rodada + pendentes de rodada anterior (sem repetir). Os
    pendentes ja resolvidos no site sao marcados notificados sem envio."""
    anteriores = pendentes_de_notificar(supabase_url, service_key, origem, do_pdf)
    ja = {i.get("historico_id") for i in alertas_para_enviar}
    anteriores = [a for a in anteriores if a["historico_id"] not in ja]
    resolvidos = [a["historico_id"] for a in anteriores if a.get("resolvido")]
    if resolvidos:
        marcar_notificados(supabase_url, service_key, resolvidos)
    return alertas_para_enviar + [a for a in anteriores if not a.get("resolvido")]


def enviar_alertas(supabase_url, service_key, telegram_token, telegram_chat,
                   alertas_para_enviar, origem, titulo, do_pdf=None,
                   teto=TETO_DE_ALERTAS):
    """Junta com pendentes de rodada anterior, aplica o teto sem prender e
    manda pro Telegram em blocos - o fim de fluxo comum aos checadores de
    nuvem.

    Teto (spec, parte 3): acima dele manda o aviso de "segurado" uma vez so
    (supervisor_estado telegram_segurado) e os alertas esperam na aba
    Urgente; saem quando alguem clicar "Liberar alertas segurados" no site
    ou depois de HORAS_SEGURADO. Antes de 26/09/2026 o aviso se repetia a
    cada rodada e os alertas ficavam presos para sempre.

    Devolve (enviado, motivo) para o chamador so imprimir.
    """
    todos = _juntar_pendentes(supabase_url, service_key, alertas_para_enviar, origem, do_pdf)
    segurado, liberado = ler_estado_telegram(supabase_url, service_key)
    if not todos:
        # tudo que estava segurado foi resolvido no site: nada mais a soltar
        if origem in _origens_seguradas(segurado):
            soltar_segurado(supabase_url, service_key, segurado, origem)
        return None, "nada a enviar"

    decisao = decidir_envio(len(todos), origem, segurado, liberado, teto)

    if decisao == "segurar":
        return False, "segurada (aviso ja enviado): %d alertas esperando liberacao" % len(todos)

    if decisao == "segurar_avisando":
        ok_envio, erro = alertas.enviar_telegram(
            telegram_token, telegram_chat, texto_segurado(titulo, len(todos), teto))
        # so registra com o aviso entregue: sem o aviso, a proxima rodada
        # tenta de novo em vez de segurar calada
        if ok_envio:
            registrar_segurado(supabase_url, service_key, segurado, origem, len(todos))
            return False, "segurada: %d alertas > teto de %d" % (len(todos), teto)
        return False, "segurada, mas o aviso falhou: %s" % erro

    ok_envio, erro = enviar_em_blocos(
        supabase_url, service_key, telegram_token, telegram_chat, todos, titulo)
    if ok_envio and decisao == "liberar":
        soltar_segurado(supabase_url, service_key, segurado, origem)
    return ok_envio, erro


def enviar_resumo_carga_inicial(supabase_url, service_key, telegram_token, telegram_chat,
                                alertas_para_enviar, origem, titulo):
    """Primeira carga (checar_volly_cloud.py --carga-inicial): as alteracoes
    que ja existiam ao ligar vao pro site como pendentes, mas no Telegram
    saem num resumo so, sem a lista - e sem passar pelo teto. Marca todos
    notificados so se o resumo foi entregue."""
    todos = _juntar_pendentes(supabase_url, service_key, alertas_para_enviar, origem, None)
    if not todos:
        return None, "nada a enviar"
    link = _link_urgente()
    texto = ("📋 <b>%s — carga inicial</b>\n\n%d alterações já existentes — ver aba "
             'Urgente: <a href="%s">%s</a>' % (titulo, len(todos), link, link))
    ok_envio, erro = alertas.enviar_telegram(telegram_token, telegram_chat, texto)
    if ok_envio:
        marcar_notificados(supabase_url, service_key, [a.get("historico_id") for a in todos])
    return ok_envio, erro


def avisar_quebra(titulo, erro):
    """Telegram de socorro quando o proprio checador de nuvem quebra - sem
    isso uma excecao nao tratada falha calada no log do GitHub Actions, que
    ninguem olha todo dia (ao contrario do Telegram).
    """
    alertas.enviar_telegram(
        os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
        "🚨 <b>%s quebrou</b>\n\n<pre>%s</pre>" % (titulo, str(erro)[:300]))
