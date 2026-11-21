"""Checagem Azul, 100% na nuvem - roda no GitHub Actions sob Xvfb, sem Mac.

Nao depende de PDF: localizador e origem ja estao no CRM (Supabase), nem
sobrenome pede - mesmo raciocinio de src/checar_azul.py (Mac), so trocando
voos_atual.csv/voos.db por Supabase.

Roda EM PARALELO ao checar_azul.py do Mac por um periodo de validacao
(mesmo acordo da LATAM/GOL - origem propria "portal-azul-cloud").

CUIDADO REDOBRADO (foi a Azul que limitou o IP da agencia em 29/07/2026):
  - quarentena CONSULTADA E GRAVADA no Supabase (limitador_cloud.py), nao em
    arquivo local - runner de nuvem e descartavel e nao lembraria sozinho um
    bloqueio da rodada anterior.
  - quarentena conferida ANTES de abrir o Chrome, igual ao Mac.
  - 2 recusas seguidas param a rodada (a GOL tolera 3).
  - sinal de bloqueio na pagina poe quarentena e para tudo na hora.
  - teto de 20 reservas por rodada.

Validado por teste manual (scripts/teste_azul_headless.py) antes de existir:
1 de 1 passou, sem bloqueio, de IP de datacenter.

Uso:
    xvfb-run -a python3 src/checar_azul_cloud.py
    xvfb-run -a python3 src/checar_azul_cloud.py --limite 5
    xvfb-run -a python3 src/checar_azul_cloud.py --loc PNR
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import azul
import batimento
import comparacao
import fusos
import limitador_cloud
import nuvem_comum
import supabase_rest
from playwright.sync_api import sync_playwright

ORIGEM = "portal-azul-cloud"
PERFIL = "/tmp/perfil-azul-cloud"
ETAPA = "portal-azul"

ESPERA_MAXIMA_CICLOS = 20
TOLERANCIA_BLOQUEIO = 2
TETO_POR_RODADA = 20


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def voos_azul(supabase_url, service_key):
    """Mesma forma de voos_gol_cloud.voos_gol: um item por localizador (com
    a origem do primeiro trecho ainda nao voado) + todos os trechos futuros
    por reserva, pra comparacao.comparar poder casar qualquer um."""
    linhas = supabase_rest.select(
        supabase_url, service_key, "voos",
        {"select": "id,localizador,cia,numero_voo,origem,destino,embarque,passageiros,"
                   "incompleto",
         "ativo": "eq.true", "cia": "eq.AZUL"},
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
        atual = por_localizador.get(loc)
        if atual is None or voo_crm["embarque_local"] < atual["embarque_local"]:
            por_localizador[loc] = voo_crm

    por_reserva = {}
    for v in todos_futuros:
        por_reserva.setdefault(v["localizador"], []).append(v)

    return por_localizador, por_reserva


def checar_um(loc, ref, voos_da_reserva, ctx, baseline, do_pdf,
              supabase_url, service_key):
    """Devolve (situacao, alertas_novos, bloqueio_geral: bool)."""
    url = azul.montar_url(loc, ref["origem"])
    limitador_cloud.aguardar(supabase_url, service_key, url)

    capturado = {}
    pagina = ctx.new_page()

    def ao_responder(resposta):
        if azul.API_CAPTURA in resposta.url:
            registro = {"url": resposta.url, "status": resposta.status, "json": None}
            try:
                registro["json"] = resposta.json()
            except Exception:
                pass
            capturado[resposta.url] = registro

    pagina.on("response", ao_responder)
    try:
        pagina.goto(url, timeout=45000, wait_until="domcontentloaded")
        recusa = e_bloqueio = None
        esperou = 0
        for _ in range(ESPERA_MAXIMA_CICLOS):
            pagina.wait_for_timeout(3000)
            esperou += 3
            recusa, e_bloqueio = azul.motivo_da_falha(capturado)
            if recusa or azul.resposta_do_booking(capturado):
                break
        texto = pagina.inner_text("body")
    except Exception as e:
        pagina.close()
        print("       falhou: %s -> conferencia manual" % str(e)[:70])
        return "falha", [], False
    finally:
        pagina.close()

    sinal = azul.sinal_de_bloqueio(texto)
    if sinal or e_bloqueio:
        limitador_cloud.registrar_bloqueio(supabase_url, service_key, url)
        print("       a Azul bloqueou o acesso (%s). Quarentena registrada." % (sinal or recusa))
        return "falha", [], True

    if recusa:
        print("       %s -> painel manual" % recusa)
        return "falha", [], False

    booking = azul.resposta_do_booking(capturado)
    if booking is None:
        print("       a API nao respondeu em %ds -> conferencia manual" % esperou)
        return "falha", [], False

    leitura = azul.ler_api(booking.get("json"))
    if not leitura["encontrada"]:
        print("       a API respondeu mas sem itinerario -> manual")
        return "falha", [], False

    devolvido = (leitura.get("localizador") or "").upper()
    if devolvido and devolvido != loc.upper():
        print("       a API devolveu %s, esperado %s -> manual" % (devolvido, loc))
        return "falha", [], False

    achados = azul.achados_de_aviso(leitura, voos_da_reserva)

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
        if leitura.get("confiavel"):
            print("       OK - %s, %d trecho(s)" % (
                leitura.get("status_pedido") or "?", len(leitura["segmentos"])))
            return "ok", [], False
        print("       sem aviso na pagina, mas a leitura nao conclui nada -> manual")
        return "falha", [], False

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

    # conferir a quarentena antes de abrir o Chrome - nao se testa a Azul
    # "so mais uma vez" mesmo aqui.
    url_teste = azul.montar_url("XXXXXX", "XXX")
    bloqueado, faltam = limitador_cloud.esta_bloqueado(supabase_url, service_key, url_teste)
    if bloqueado:
        print("A Azul esta em quarentena por mais %d min." % faltam)
        b.detalhe["quarentena_min"] = faltam
        sys.exit(2)

    por_localizador, por_reserva = voos_azul(supabase_url, service_key)
    print("Localizadores AZUL consultaveis ... %d" % len(por_localizador))

    itens = sorted(por_localizador.items(), key=lambda i: i[1]["embarque_local"])
    if so_esses:
        itens = [(loc, ref) for loc, ref in itens if loc.upper() in so_esses]
        if not itens:
            print("Nenhum localizador bate com %s" % ", ".join(sorted(so_esses)))
            sys.exit(1)
    if limite is not None:
        itens = itens[:limite]
    if len(itens) > TETO_POR_RODADA:
        print("  (teto de %d por rodada; %d ficam para a proxima)"
              % (TETO_POR_RODADA, len(itens) - TETO_POR_RODADA))
        itens = itens[:TETO_POR_RODADA]
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
    interrompido = None

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PERFIL, channel="chrome", headless=False,
            locale="pt-BR", timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )

        for i, (loc, ref) in enumerate(itens, 1):
            if interrompido or seguidas >= TOLERANCIA_BLOQUEIO:
                nao_consultadas.append(loc)
                continue

            print("[%d/%d] %s  %s" % (i, len(itens), loc, ref["origem"]))
            try:
                situacao, alertas_novos, bloqueio_geral = checar_um(
                    loc, ref, por_reserva.get(loc, []), ctx, baseline, do_pdf,
                    supabase_url, service_key)
            except Exception as e:
                print("       erro inesperado: %s" % str(e)[:150])
                situacao, alertas_novos, bloqueio_geral = "falha", [], False

            if bloqueio_geral:
                b.detalhe["bloqueios"] += 1
                interrompido = "a Azul bloqueou o acesso - rodada interrompida"

            if situacao == "falha":
                falhas += 1
                seguidas += 1
                if seguidas >= TOLERANCIA_BLOQUEIO:
                    print("\n>>> %d recusas seguidas: parando a rodada da Azul.\n" % seguidas)
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
    print("  RESULTADO DA CHECAGEM AZUL (nuvem)")
    print("=" * 62)
    print("  consultas feitas ............ %d" % len(itens))
    print("  conferidas sem mudanca ...... %d" % ok)
    print("  com alerta .................. %d" % alertas_qtd)
    print("  falharam ..................... %d" % falhas)
    if nao_consultadas:
        print("  nao consultadas (parada) .... %d" % len(nao_consultadas))
    print("=" * 62)
    if interrompido:
        print("\n  RODADA INTERROMPIDA: %s" % interrompido)
        b.detalhe["interrompida"] = interrompido

    enviado, motivo = nuvem_comum.enviar_alertas(
        supabase_url, service_key, telegram_token, telegram_chat,
        alertas_para_enviar, ORIGEM, "Voos com alteração (Azul, nuvem)", do_pdf)
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
    # batimento `portal-azul` pro supervisor (fluxo na nuvem, 26/09/2026)
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
        nuvem_comum.avisar_quebra("A checagem Azul (nuvem)", erro)
        sys.exit(1)
