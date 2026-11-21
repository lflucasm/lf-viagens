"""Checagem LATAM, 100% na nuvem - roda no GitHub Actions sob Xvfb, sem PDF
nem iCloud (portanto sem depender do Mac ligado).

Duas coisas precisavam ser resolvidas pra isso existir, ambas confirmadas em
12/08/2026:

  1. De onde vem o deep link (?orderId=...&lastname=...) sem PDF local? Do
     MilhasFlow: emission_link/ticket_file_url ja trazem o numero de compra
     (ver milhasflow.extrair_pedido_latam). Cobre ~62% das reservas LATAM
     ativas hoje - o resto sao vendas antigas sem PDF gerado pelo MilhasFlow,
     que o Mac (checar_latam.py) continua cobrindo.
  2. O anti-bot da LATAM barra headless - Chrome de verdade sob Xvfb, canal
     "chrome", passa (ver scripts/teste_latam_headless.py).

Roda EM PARALELO ao checar_latam.py do Mac por um periodo de validacao
(pedido do proprietário: ~2 meses, ate meados de outubro de 2026) - origem propria
("portal-latam-cloud") pra nao competir de baseline com a origem do Mac
("portal-latam"). Se as duas concordarem no periodo, o Mac se aposenta desta
parte; ate la, os dois convivem e podem ate se confirmar mutuamente (ver
rodada.alertas_pendentes, que junta achados iguais de fontes diferentes).

Uso:
    xvfb-run -a python3 src/checar_latam_cloud.py
    xvfb-run -a python3 src/checar_latam_cloud.py --limite 5
    xvfb-run -a python3 src/checar_latam_cloud.py --loc PNR
    xvfb-run -a python3 src/checar_latam_cloud.py --dias 7   # so quem embarca em ate 7 dias
"""

import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import batimento
import comparacao
import fusos
import latam
import limitador
import nuvem_comum
import supabase_rest
from milhasflow import MilhasFlow, extrair_pedido_latam
from navegador import SINAIS_DE_BLOQUEIO

ORIGEM = "portal-latam-cloud"

URL_GERENCIAR = ("https://www.latamairlines.com/br/pt/minhas-viagens/"
                 "second-detail/?orderId=%s&lastname=%s")
API_PEDIDO = "/bff/mytrips/v1/order/id/"
ETAPA = "portal-latam"
ERRO_BLOQUEIO = "bloqueada pela LATAM - entrando em quarentena"

PERFIL = "/tmp/perfil-latam-cloud"


class MilhasFlowConfig(object):
    """Config minima pra reaproveitar MilhasFlow sem importar src/config.py
    inteiro (que exige variaveis do bot local, tipo caminho do banco)."""

    def __init__(self):
        self.email = _obrigatorio("MILHASFLOW_EMAIL")
        self.senha = _obrigatorio("MILHASFLOW_SENHA")
        self.anon_key = _obrigatorio("MILHASFLOW_ANON_KEY")
        self.organization_id = _obrigatorio("ORGANIZATION_ID")
        self.supabase_url = _obrigatorio("SUPABASE_URL").rstrip("/")
        # cache do token entre rodadas - no Mac sobrevive de uma checagem
        # pra outra; aqui o runner e descartado no fim mesmo, entao so
        # evita duas idas ao login DENTRO desta mesma execucao.
        self.caminho_tokens = "/tmp/milhasflow_tokens.json"
        # painel (milhasflow_auth_state) - deixa o refresh_token sobreviver
        # entre rodadas do Actions em vez de cair pro login por senha
        # (bloqueado por captcha desde 14/09/2026, ver milhasflow.py).
        self.supabase_web_url = os.environ.get("SUPABASE_WEB_URL", "").rstrip("/")
        self.supabase_web_service_key = os.environ.get("SUPABASE_WEB_SERVICE_KEY", "")


def autenticar_volly(mf, detalhe):
    """Garante o token da Volly logo no inicio da rodada. Se falhar (refresh
    morto, login por senha barrado pelo captcha desde 14/09/2026), marca
    `detalhe["erro_login"] = True` no batimento e relanca - o supervisor
    (fase 6 do fluxo na nuvem) le exatamente esse campo pra avisar que o
    login da Volly caiu, em vez de so ver "falhou" sem motivo."""
    try:
        mf._token()
    except Exception:
        detalhe["erro_login"] = True
        raise


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def voos_latam(supabase_url, service_key):
    """Voos LATAM ativos do Supabase, agrupados por emissao_id - um pedido
    da LATAM pode cobrir varios trechos (ida e volta, conexoes)."""
    linhas = supabase_rest.select(
        supabase_url, service_key, "voos",
        {"select": "id,emissao_id,localizador,cia,numero_voo,origem,destino,"
                   "embarque,passageiros,status,incompleto",
         "ativo": "eq.true", "cia": "eq.LATAM", "emissao_id": "not.is.null"},
    )
    por_emissao = {}
    for l in linhas:
        # trecho ja voado (ou que a agencia ja descartou) nao importa pra
        # comparacao - so gera ruido, tipo o LA3490 da TSTANX (26/07, ja
        # dismissed) comparado contra uma resposta velha da LATAM em
        # 12/08/2026. O Mac ja tem essa trava via latam.tem_trecho_futuro();
        # aqui e por trecho, nao por reserva, porque a volta (outro voo,
        # ainda futura) tem que continuar sendo conferida.
        horas = fusos.horas_ate(l["embarque"])
        if horas is None or horas < 0 or l.get("status") == "dismissed":
            continue
        # trecho incompleto (sem numero, numero composto, sem fuso - marcado
        # pela ingestao) nao e checavel: o horario local sairia errado
        if l.get("incompleto"):
            continue
        voo_crm = dict(l)
        voo_crm.pop("status", None)
        voo_crm.pop("incompleto", None)
        # `embarque` no Supabase e UTC (ver fusos.py); comparar a DATA crua
        # contra o portal (que mostra hora local) desalinha o calendario
        # sempre que o embarque local cair antes das 3h - foi o que gerou
        # alerta falso pra TSTAPX/LA3494 em 12/08/2026 (21:00 local virou
        # "01/09" em vez de "31/08"). Mesma conversao que sync.py ja faz
        # pro CSV do Mac.
        voo_crm["embarque_local"] = fusos.texto_local(voo_crm.pop("embarque"), l["origem"])
        por_emissao.setdefault(l["emissao_id"], []).append(voo_crm)
    return por_emissao


def pedidos_latam(mf, por_emissao):
    """{orderId: {"url", "sobrenome", "voos"}} - so as emissoes com link
    resolvivel entram (ver extrair_pedido_latam)."""
    emissoes = mf.buscar_links_latam(por_emissao.keys())
    pedidos = {}
    sem_link = 0
    for emissao in emissoes:
        voos = por_emissao.get(emissao["id"]) or []
        if not voos:
            continue
        pedido, sobrenome = extrair_pedido_latam(emissao)
        if not pedido:
            sem_link += 1
            continue
        pedidos[pedido] = {
            "url": URL_GERENCIAR % (pedido, urllib.parse.quote(sobrenome)),
            "sobrenome": sobrenome,
            "voos": voos,
        }
    return pedidos, sem_link


def linhas_links_pdf(voos, emissoes):
    """Linhas de `links_pdf` (uma por localizador) com o link da reserva na
    LATAM. O site so mostra o botao da cia a partir dessa tabela (que o Mac
    alimentava e parou em 14/09/2026) - sem isto, reserva LATAM nova ficava
    sem link mesmo com o "Nro compra" ja no MilhasFlow (caso TSTAHX).

    `voos`: trechos LATAM ativos (localizador, emissao_id, origem, embarque,
    passageiros) - todos, nao so os checaveis: trecho incompleto ou ja voado
    tambem merece o botao. `emissoes`: vendas do MilhasFlow casadas por id ou
    por localizador (trecho sem emissao_id).
    """
    por_id = {e["id"]: e for e in emissoes if e.get("id")}
    por_loc = {(e.get("localizador") or "").upper(): e for e in emissoes}
    primeiro = {}
    for v in voos:
        loc = (v.get("localizador") or "").upper()
        if not loc:
            continue
        atual = primeiro.get(loc)
        # primeiro trecho da reserva, como sincronizar_web
        if atual is None or (v.get("embarque") or "") < (atual.get("embarque") or ""):
            primeiro[loc] = v

    agora = nuvem_comum.agora_utc()
    linhas = []
    for loc, v in primeiro.items():
        emissao = por_id.get(v.get("emissao_id")) or por_loc.get(loc)
        if not emissao:
            continue
        pedido, sobrenome = extrair_pedido_latam(emissao)
        if not pedido:
            continue
        linhas.append({
            "localizador": loc, "pedido": pedido, "companhia": "LATAM",
            "origem": v.get("origem"), "sobrenome": sobrenome,
            "url": URL_GERENCIAR % (pedido, urllib.parse.quote(sobrenome)),
            "util": True, "atualizado_em": agora,
        })
    return linhas


def gravar_links_latam(mf, supabase_url, service_key):
    """Atualiza `links_pdf` com o link de toda reserva LATAM ativa que tenha
    numero de compra no MilhasFlow. Devolve quantas linhas gravou."""
    voos = supabase_rest.select(
        supabase_url, service_key, "voos",
        {"select": "localizador,emissao_id,origem,embarque",
         "ativo": "eq.true", "cia": "eq.LATAM"})
    ids = {v["emissao_id"] for v in voos if v.get("emissao_id")}
    sem_id = {(v.get("localizador") or "").upper() for v in voos
              if not v.get("emissao_id") and v.get("localizador")}
    emissoes = mf.buscar_links_latam(ids) if ids else []
    if sem_id:
        emissoes += mf.buscar_links_latam_por_localizador(sem_id)
    linhas = linhas_links_pdf(voos, emissoes)
    supabase_rest.upsert(supabase_url, service_key, "links_pdf", linhas, "localizador")
    return len(linhas)


def abrir_e_capturar(ctx, url, espera_s=15):
    """Abre a URL e devolve (json, erro) da primeira resposta que casar com
    API_PEDIDO - mesmo padrao de navegador.Navegador.json_da_api, sem as
    partes especificas do Mac (AppleScript, janela fora da tela)."""
    limitador.aguardar(url)
    capturado = {}

    def ao_responder(resposta):
        if API_PEDIDO in resposta.url and not capturado:
            try:
                capturado["dados"] = resposta.json()
            except Exception:
                pass

    pagina = ctx.new_page()
    pagina.on("response", ao_responder)
    try:
        pagina.goto(url, timeout=45000, wait_until="domcontentloaded")
        limite = time.time() + espera_s
        while not capturado and time.time() < limite:
            pagina.wait_for_timeout(500)

        if not capturado:
            texto = (pagina.inner_text("body") or "")[:1500].lower()
            if any(s in texto for s in SINAIS_DE_BLOQUEIO):
                limitador.registrar_bloqueio(url)
                return None, ERRO_BLOQUEIO
            return None, "a API nao respondeu"
        return capturado["dados"], None
    except Exception as e:
        return None, str(e)[:200]
    finally:
        pagina.close()


def checar_um(pedido, info, ctx, baseline, do_pdf, supabase_url, service_key):
    """Consulta e processa um pedido: grava observacao/achado e monta os
    itens de alerta prontos pro Telegram.

    Devolve (situacao, alertas_novos) - situacao e "ok"/"falha"/"alerta", ou
    "bloqueio"/"quarentena" (falhas que o batimento conta a parte).
    """
    bloqueado, faltam = limitador.esta_bloqueado(info["url"])
    if bloqueado:
        print("       em quarentena por mais %d min - pulando" % faltam)
        return "quarentena", []

    dados, erro = abrir_e_capturar(ctx, info["url"])
    if erro or not dados:
        print("       falhou: %s -> conferencia manual" % (erro or "sem conteudo"))
        return ("bloqueio" if erro == ERRO_BLOQUEIO else "falha"), []

    leitura = latam.ler_api(dados)
    if not leitura["encontrada"]:
        print("       reserva NAO localizada no portal")
        return "falha", []

    voos_da_reserva = info["voos"]
    por_chave = {(latam._normaliza_voo(v["numero_voo"]),
                 (v["embarque_local"] or "")[:10]): v for v in voos_da_reserva}
    achados = comparacao.comparar(leitura, voos_da_reserva, baseline)
    achados += latam.achados_de_status(leitura, por_chave)

    for voo_id, partida, rota, situacao in \
            comparacao.observacoes_da_leitura(leitura, voos_da_reserva):
        supabase_rest.upsert(
            supabase_url, service_key, "observacoes",
            [{"voo_id": voo_id, "origem": ORIGEM, "partida": partida,
              "rota": rota, "situacao": situacao,
              "visto_em": nuvem_comum.agora_utc()}],
            "voo_id,origem",
        )

    alertas_novos = []
    relevantes = [a for a in achados if a["voo_crm"]]
    if not relevantes:
        print("       OK - %d trecho(s)" % len(leitura["segmentos"]))
        return "ok", alertas_novos

    # dedupe + confirmacao entre fontes: nuvem_comum.gravar_achado
    for a in relevantes:
        item = nuvem_comum.gravar_achado(supabase_url, service_key, a, ORIGEM, do_pdf)
        if item:
            alertas_novos.append(item)

    return ("alerta" if alertas_novos else "ok"), alertas_novos


def main():
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}

    dias = None
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])

    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")

    fusos.carregar_aprendidos(supabase_url, service_key)
    # batimento `portal-latam` pro supervisor (fluxo na nuvem, 26/09/2026)
    with batimento.rodada(supabase_url, service_key, ETAPA) as b:
        rodar(supabase_url, service_key, b, limite, so_esses, dias)


def rodar(supabase_url, service_key, b, limite, so_esses, dias=None):
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    mf = MilhasFlow(MilhasFlowConfig())
    autenticar_volly(mf, b.detalhe)

    por_emissao = voos_latam(supabase_url, service_key)
    print("Emissoes LATAM ativas ......... %d" % len(por_emissao))

    pedidos, sem_link = pedidos_latam(mf, por_emissao)
    print("Com link resolvivel ........... %d" % len(pedidos))
    if sem_link:
        print("Sem emission_link/ticket_file_url (venda antiga, sem PDF"
              " no MilhasFlow) .. %d - cobertas so pelo Mac por ora" % sem_link)
    b.detalhe["sem_link"] = sem_link
    try:
        b.detalhe["links_gravados"] = gravar_links_latam(mf, supabase_url, service_key)
    except Exception as e:
        # link do site e conveniencia; nunca derruba a checagem
        print("AVISO: nao consegui gravar links_pdf (%s)" % e)

    itens = sorted(pedidos.items())
    if so_esses:
        itens = [(p, info) for p, info in itens
                 if any(v["localizador"].upper() in so_esses for v in info["voos"])]
        if not itens:
            print("Nenhum localizador bate com %s" % ", ".join(sorted(so_esses)))
            sys.exit(1)
    if dias is not None:
        itens = [(p, info) for p, info in itens
                 if any(nuvem_comum.embarca_em_ate(v["embarque_local"], dias)
                        for v in info["voos"])]
        b.detalhe["so_proximos_dias"] = dias
    if limite is not None:
        itens = itens[:limite]
    print("Vou consultar .................. %d\n" % len(itens))
    b.detalhe["consultas"] = len(itens)
    b.detalhe["bloqueios"] = 0
    b.detalhe["em_quarentena"] = 0

    if not itens:
        return

    # baseline da comparacao: a ULTIMA leitura desta fonte (nao o CRM - ver
    # o motivo em comparacao.comparar). Origem propria, separada do Mac.
    baseline = {l["voo_id"]: l for l in supabase_rest.select(
        supabase_url, service_key, "observacoes",
        {"select": "voo_id,partida,rota,situacao", "origem": "eq.%s" % ORIGEM})}
    do_pdf = nuvem_comum.links_pdf_do_supabase(supabase_url, service_key)

    ok = falhas = alertas_qtd = lidos = 0
    alertas_para_enviar = []

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PERFIL,
            channel="chrome",
            headless=False,        # headless e barrado pela LATAM
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )

        for i, (pedido, info) in enumerate(itens, 1):
            print("[%d/%d] %s (%s)" % (i, len(itens), pedido, info["sobrenome"]))
            try:
                situacao, alertas_novos = checar_um(
                    pedido, info, ctx, baseline, do_pdf, supabase_url, service_key)
            except Exception as e:
                # um pedido ruim (Supabase soluco, Playwright caiu) nao pode
                # derrubar o resto da rodada nem os alertas ja detectados
                # antes dele - checar_malha_cloud.py tem a mesma protecao
                # (checar_um la tambem), o de la so tem ADEMAIS um `break`
                # por cota (MalhaIndisponivel), que nao existe aqui porque a
                # LATAM nao tem cota - so recaptcha/bloqueio por reserva.
                print("       erro inesperado: %s" % str(e)[:150])
                situacao, alertas_novos = "falha", []

            if situacao == "bloqueio":
                b.detalhe["bloqueios"] += 1
                falhas += 1
            elif situacao == "quarentena":
                b.detalhe["em_quarentena"] += 1
                falhas += 1
            elif situacao == "falha":
                falhas += 1
            elif situacao == "alerta":
                lidos += 1
                alertas_para_enviar += alertas_novos
                alertas_qtd += len(alertas_novos)
            else:
                lidos += 1
                ok += 1

        ctx.close()

    b.lidos, b.alertas, b.falhas = lidos, alertas_qtd, falhas

    print("\n" + "=" * 62)
    print("  RESULTADO DA CHECAGEM LATAM (nuvem)")
    print("=" * 62)
    print("  consultas feitas ............ %d" % len(itens))
    print("  conferidas sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d" % alertas_qtd)
    print("  falharam ..................... %d" % falhas)
    print("=" * 62)

    enviado, motivo = nuvem_comum.enviar_alertas(
        supabase_url, service_key, telegram_token, telegram_chat,
        alertas_para_enviar, ORIGEM, "Voos com alteração (LATAM, nuvem)", do_pdf)
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
        nuvem_comum.avisar_quebra("A checagem LATAM (nuvem)", erro)
        sys.exit(1)
