"""Checagem GOL, 100% na nuvem - roda no GitHub Actions sob Xvfb, sem Mac.

Ao contrario da LATAM, nao depende de PDF/iCloud: localizador, origem e
sobrenome ja estao no CRM (Supabase), entao a cobertura e de 100% dos
localizadores GOL desde o primeiro dia - mesmo raciocinio de
src/checar_gol.py (Mac), so trocando voos_atual.csv/voos.db por Supabase.

Roda EM PARALELO ao checar_gol.py do Mac por um periodo de validacao (mesmo
acordo da LATAM - origem propria "portal-gol-cloud", nao compete de
baseline com "portal-gol"). Se as duas concordarem, o Mac se aposenta desta
parte.

Risco aceito conscientemente (decisao com o proprietário, 20/08/2026): a GOL ja
falha ~50% por score de reCAPTCHA mesmo de IP residencial - validado por
teste manual (scripts/teste_gol_headless.py) que IP de datacenter nao piora
isso (2 de 3 passaram). O que passa vale; o que nao passa fica pendente
igual sempre ficou.

Uso:
    xvfb-run -a python3 src/checar_gol_cloud.py
    xvfb-run -a python3 src/checar_gol_cloud.py --limite 5
    xvfb-run -a python3 src/checar_gol_cloud.py --loc PNR
    xvfb-run -a python3 src/checar_gol_cloud.py --dias 7   # so quem embarca em ate 7 dias
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import batimento
import comparacao
import fusos
import gol
import limitador_cloud
import nuvem_comum
import qualidade
import supabase_rest
from playwright.sync_api import sync_playwright

ORIGEM = "portal-gol-cloud"
PERFIL = "/tmp/perfil-gol-cloud"
ETAPA = "portal-gol"
URL_DETALHE = "detalhes-da-viagem"

ESPERA_MAXIMA_CICLOS = 22       # mesma tolerancia do Mac: ate 66s
TOLERANCIA_BLOQUEIO = 3         # recusas seguidas antes de parar a rodada


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def voos_gol(supabase_url, service_key):
    """Voos GOL ativos e futuros do Supabase, agrupados por localizador -
    uma entrada por reserva, com a origem do primeiro trecho ainda nao voado
    (mesma regra de checar_gol.py:reservas_gol)."""
    linhas = supabase_rest.select(
        supabase_url, service_key, "voos",
        {"select": "id,localizador,cia,numero_voo,origem,destino,embarque,passageiros,"
                   "incompleto",
         "ativo": "eq.true", "cia": "eq.GOL"},
    )
    por_localizador = {}
    todos_futuros = []
    for l in linhas:
        horas = fusos.horas_ate(l["embarque"])
        if horas is None or horas < 0:
            continue
        # trecho incompleto (sem numero, numero composto, sem fuso - marcado
        # pela ingestao) nao e checavel: o horario local sairia errado
        if l.get("incompleto"):
            continue
        voo_crm = dict(l)
        voo_crm.pop("incompleto", None)
        voo_crm["embarque_local"] = fusos.texto_local(voo_crm.pop("embarque"), l["origem"])
        todos_futuros.append(voo_crm)

        loc = voo_crm["localizador"]
        if not loc or not voo_crm["origem"]:
            continue
        sobrenome = qualidade.sobrenome(voo_crm.get("passageiros"))
        if not sobrenome:
            continue
        atual = por_localizador.get(loc)
        if atual is None or voo_crm["embarque_local"] < atual["embarque_local"]:
            por_localizador[loc] = voo_crm

    # todos os trechos de cada reserva, pra comparacao.comparar poder casar
    # qualquer um deles - nao so o que definiu origem/sobrenome
    por_reserva = {}
    for v in todos_futuros:
        por_reserva.setdefault(v["localizador"], []).append(v)

    return por_localizador, por_reserva


def checar_um(loc, ref, voos_da_reserva, ctx, baseline, do_pdf,
              supabase_url, service_key):
    """Devolve (situacao, alertas_novos, recusa_bloqueio)."""
    url = gol.montar_url(loc, ref["origem"], qualidade.sobrenome(ref.get("passageiros")))
    limitador_cloud.aguardar(supabase_url, service_key, url)

    capturado = {}
    pagina = ctx.new_page()

    def ao_responder(resposta):
        if gol.API_CONSULTA in resposta.url:
            registro = {"url": resposta.url, "status": resposta.status, "json": None}
            try:
                registro["json"] = resposta.json()
            except Exception:
                pass
            capturado[resposta.url] = registro

    pagina.on("response", ao_responder)
    try:
        pagina.goto(url, timeout=45000, wait_until="domcontentloaded")
        chegou = reacomodada = False
        for _ in range(ESPERA_MAXIMA_CICLOS):
            pagina.wait_for_timeout(3000)
            if URL_DETALHE in pagina.url:
                chegou = True
                break
            if gol.URL_REACOMODACAO in pagina.url:
                reacomodada = True
                break
            if gol.motivo_da_falha(capturado):
                break
        if chegou:
            pagina.wait_for_timeout(3000)
        texto = pagina.inner_text("body")
    except Exception as e:
        pagina.close()
        print("       falhou: %s -> conferencia manual" % str(e)[:70])
        return "falha", [], False
    finally:
        pagina.close()

    if reacomodada:
        referencia = voos_da_reserva[0] if voos_da_reserva else None
        print("       GOL reacomodou o voo sozinha -> ALERTA")
        if not referencia:
            return "falha", [], False
        item = nuvem_comum.gravar_achado(supabase_url, service_key, {
            "tipo": "alterado_pela_companhia", "voo_crm": referencia,
            "detalhe": "a GOL reacomodou esta reserva automaticamente - verifique "
                       "manualmente qual trecho mudou (%s)" % url,
        }, ORIGEM, do_pdf)
        if not item:
            return "ok", [], False
        # no Telegram vai o resumo curto; a URL completa fica no historico
        item["detalhe"] = "%s reacomodado automaticamente pela GOL" % (
            referencia.get("numero_voo") or "?")
        return "alerta", [item], False

    recusa = gol.motivo_da_falha(capturado)
    if recusa:
        print("       %s -> painel manual" % recusa)
        return "falha", [], recusa == gol.BLOQUEIO_RECAPTCHA

    leitura = gol.ler_pagina(texto)
    if not leitura["encontrada"]:
        print("       nao carregou a reserva (chegou=%s) -> manual" % chegou)
        return "falha", [], False

    achados = gol.achados_de_aviso(leitura, voos_da_reserva)

    if leitura.get("confiavel"):
        achados += comparacao.comparar(leitura, voos_da_reserva, baseline)
        for voo_id, partida, rota, situacao in \
                comparacao.observacoes_da_leitura(leitura, voos_da_reserva):
            supabase_rest.upsert(
                supabase_url, service_key, "observacoes",
                [{"voo_id": voo_id, "origem": ORIGEM, "partida": partida, "rota": rota,
                  "situacao": situacao,
                  "visto_em": nuvem_comum.agora_utc()}],
                "voo_id,origem",
            )
    else:
        print("       leitura parcial (%s) - so avisos explicitos" % leitura.get("motivo"))

    relevantes = [a for a in achados if a["voo_crm"]]
    if not relevantes:
        print("       OK - %s, %d trecho(s)" % (
            leitura.get("status_pedido") or "?", len(leitura["segmentos"])))
        return "ok", [], False

    # dedupe + confirmacao entre fontes: nuvem_comum.gravar_achado
    alertas_novos = []
    for a in relevantes:
        item = nuvem_comum.gravar_achado(supabase_url, service_key, a, ORIGEM, do_pdf)
        if item:
            alertas_novos.append(item)
    return ("alerta" if alertas_novos else "ok"), alertas_novos, False


def rodar(b):
    """A rodada em si; `b` (batimento.Rodada) recebe os contadores."""
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])
    so_esses = set()
    if "--loc" in sys.argv:
        so_esses = {p.strip().upper()
                    for p in sys.argv[sys.argv.index("--loc") + 1].split(",")
                    if p.strip()}

    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    b.detalhe["bloqueios"] = 0

    por_localizador, por_reserva = voos_gol(supabase_url, service_key)
    print("Localizadores GOL consultaveis ... %d" % len(por_localizador))

    itens = sorted(por_localizador.items(), key=lambda i: i[1]["embarque_local"])
    if so_esses:
        itens = [(loc, ref) for loc, ref in itens if loc.upper() in so_esses]
        if not itens:
            print("Nenhum localizador bate com %s" % ", ".join(sorted(so_esses)))
            sys.exit(1)
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])
        # ref = primeiro trecho ainda nao voado da reserva (voos_gol)
        itens = [(loc, ref) for loc, ref in itens
                 if nuvem_comum.embarca_em_ate(ref["embarque_local"], dias)]
        b.detalhe["so_proximos_dias"] = dias
    if limite is not None:
        itens = itens[:limite]
    print("Vou consultar ..................... %d\n" % len(itens))

    if not itens:
        return

    baseline = {l["voo_id"]: l for l in supabase_rest.select(
        supabase_url, service_key, "observacoes",
        {"select": "voo_id,partida,rota,situacao", "origem": "eq.%s" % ORIGEM})}
    do_pdf = nuvem_comum.links_pdf_do_supabase(supabase_url, service_key)

    ok = falhas = alertas_qtd = seguidas = alertas_ok = 0
    nao_consultadas = []
    alertas_para_enviar = []

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PERFIL, channel="chrome", headless=False,
            locale="pt-BR", timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )

        for i, (loc, ref) in enumerate(itens, 1):
            if seguidas >= TOLERANCIA_BLOQUEIO:
                nao_consultadas.append(loc)
                continue

            print("[%d/%d] %s  %s" % (i, len(itens), loc, ref["origem"]))
            try:
                situacao, alertas_novos, foi_recaptcha = checar_um(
                    loc, ref, por_reserva.get(loc, []), ctx, baseline, do_pdf,
                    supabase_url, service_key)
            except Exception as e:
                print("       erro inesperado: %s" % str(e)[:150])
                situacao, alertas_novos, foi_recaptcha = "falha", [], False

            if situacao == "falha":
                falhas += 1
                if foi_recaptcha:
                    b.detalhe["bloqueios"] += 1
                seguidas = seguidas + 1 if foi_recaptcha else 0
                if seguidas >= TOLERANCIA_BLOQUEIO:
                    print("\n>>> %d recusas seguidas: parando a rodada da GOL.\n" % seguidas)
            elif situacao == "alerta":
                seguidas = 0
                alertas_ok += 1
                alertas_para_enviar += alertas_novos
                alertas_qtd += len(alertas_novos)
            else:
                seguidas = 0
                ok += 1

        ctx.close()

    b.lidos, b.alertas, b.falhas = ok + alertas_ok, alertas_qtd, falhas
    b.detalhe["consultas"] = len(itens)
    b.detalhe["nao_consultadas"] = len(nao_consultadas)

    print("\n" + "=" * 62)
    print("  RESULTADO DA CHECAGEM GOL (nuvem)")
    print("=" * 62)
    print("  consultas feitas ............ %d" % len(itens))
    print("  conferidas sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d" % alertas_qtd)
    print("  falharam ..................... %d" % falhas)
    if nao_consultadas:
        print("  nao consultadas (parada) .... %d" % len(nao_consultadas))
    print("=" * 62)

    enviado, motivo = nuvem_comum.enviar_alertas(
        supabase_url, service_key, telegram_token, telegram_chat,
        alertas_para_enviar, ORIGEM, "Voos com alteração (GOL, nuvem)", do_pdf)
    if enviado is None:
        pass
    elif enviado:
        print("\n>>> Telegram: enviado")
    else:
        print("\n>>> Telegram: %s" % motivo)


def main():
    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")
    fusos.carregar_aprendidos(supabase_url, service_key)
    # batimento `portal-gol` pro supervisor (fluxo na nuvem, 26/09/2026)
    with batimento.rodada(supabase_url, service_key, ETAPA) as b:
        rodar(b)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        import traceback
        traceback.print_exc()
        nuvem_comum.avisar_quebra("A checagem GOL (nuvem)", erro)
        sys.exit(1)
