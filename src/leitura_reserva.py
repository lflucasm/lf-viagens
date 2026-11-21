"""Le UMA reserva no portal da companhia (LATAM/GOL/Azul) sem gravar nada.

Usado pela reconferencia (reconferir_cloud.py): depois do "Verificado -
passageiro avisado", o portal e a fonte mais forte que existe (e a unica
que ve a RESERVA do passageiro - cancelamento, reacomodacao, troca de voo).
Prioridade da verdade no spec (parte 4, 26/09/2026): portal > monitor
Volly > malha.

Reaproveita por import o que os checadores de nuvem ja tem - montagem do
link, captura da API, parsers (latam.ler_api, gol.ler_pagina,
azul.ler_api), quarentena - mas NAO grava observacao, historico nem
Telegram: quem decide o que fazer com a leitura e a reconferencia. Os
checar_*_cloud.py nao foram mexidos (a fase 4 estava neles ao mesmo tempo);
a espera da pagina de GOL/Azul, que la mora dentro de checar_um junto com a
gravacao, esta repetida aqui na forma minima.

Precisa de Chrome real sob Xvfb (anti-bot), igual os checadores:
    xvfb-run -a python3 src/reconferir_cloud.py --voo ID --historico ID
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import azul
import fusos
import gol
import latam
import limitador
import limitador_cloud
import qualidade
import supabase_rest

# Mesmos codigos de origem dos checadores de portal - e o que o site mostra
# como fonte (ROTULO_ORIGEM em web/lib/tipos.ts).
FONTE = {
    "LATAM": "portal-latam-cloud",
    "GOL": "portal-gol-cloud",
    "AZUL": "portal-azul-cloud",
}
PERFIL = "/tmp/perfil-reconferencia"

# mesma tolerancia dos checadores (ciclos de 3s)
CICLOS_GOL = 22
CICLOS_AZUL = 20


def tem_portal(cia):
    return (cia or "").upper() in FONTE


def _origem_da_reserva(supabase_url, service_key, loc, padrao):
    """Origem do primeiro trecho ainda nao voado da reserva - e o que o link
    da GOL/Azul pede (mesma regra de checar_gol_cloud.voos_gol)."""
    try:
        linhas = supabase_rest.select(
            supabase_url, service_key, "voos",
            {"select": "origem,embarque", "localizador": "eq.%s" % loc, "ativo": "eq.true"})
    except Exception:
        return padrao
    futuros = [l for l in linhas
               if l.get("origem") and (fusos.horas_ate(l.get("embarque")) or -1) >= 0]
    if not futuros:
        return padrao
    return min(futuros, key=lambda l: l["embarque"])["origem"]


def _ler_latam(ctx, loc, voo, mf):
    # import aqui: checar_latam_cloud puxa milhasflow/navegador, que so
    # interessam quando a cia e LATAM
    import checar_latam_cloud
    if not voo.get("emissao_id"):
        return None, "trecho sem emissao na Volly - sem deep link da LATAM"
    pedidos, _ = checar_latam_cloud.pedidos_latam(mf, {voo["emissao_id"]: [voo]})
    if not pedidos:
        return None, "emissao sem emission_link/ticket_file_url - sem deep link da LATAM"
    info = next(iter(pedidos.values()))
    bloqueado, faltam = limitador.esta_bloqueado(info["url"])
    if bloqueado:
        return None, "LATAM em quarentena por mais %d min" % faltam
    dados, erro = checar_latam_cloud.abrir_e_capturar(ctx, info["url"])
    if erro or not dados:
        return None, erro or "sem conteudo"
    leitura = latam.ler_api(dados)
    if not leitura["encontrada"]:
        return None, "reserva nao localizada no portal da LATAM"
    return leitura, None


def _capturar(ctx, url, trecho_api):
    """Abre a pagina e devolve (pagina, capturado) - quem chama espera."""
    capturado = {}
    pagina = ctx.new_page()

    def ao_responder(resposta):
        if trecho_api in resposta.url:
            registro = {"url": resposta.url, "status": resposta.status, "json": None}
            try:
                registro["json"] = resposta.json()
            except Exception:
                pass
            capturado[resposta.url] = registro

    pagina.on("response", ao_responder)
    pagina.goto(url, timeout=45000, wait_until="domcontentloaded")
    return pagina, capturado


def _ler_gol(ctx, loc, voo, supabase_url, service_key):
    sobrenome = qualidade.sobrenome(voo.get("passageiros"))
    if not sobrenome:
        return None, "sem sobrenome no cadastro - o link da GOL exige"
    origem = _origem_da_reserva(supabase_url, service_key, loc, voo.get("origem"))
    url = gol.montar_url(loc, origem, sobrenome)
    limitador_cloud.aguardar(supabase_url, service_key, url)
    pagina, capturado = _capturar(ctx, url, gol.API_CONSULTA)
    try:
        chegou = reacomodada = False
        for _ in range(CICLOS_GOL):
            pagina.wait_for_timeout(3000)
            if gol.URL_DETALHE in pagina.url:
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
    finally:
        pagina.close()

    if reacomodada:
        # a pagina pede "voce concorda com a alteracao?" e nao mostra o voo
        # novo - proposta_volly.de_leitura_portal vira sem_proposta explicado
        return {"encontrada": True, "reacomodada": True, "cancelada": False,
                "segmentos": []}, None
    recusa = gol.motivo_da_falha(capturado)
    if recusa:
        return None, recusa
    leitura = gol.ler_pagina(texto)
    if not leitura["encontrada"]:
        return None, "a GOL nao mostrou a reserva (chegou=%s)" % chegou
    if not leitura.get("confiavel") and not leitura.get("cancelada"):
        # itinerario com conexao funde trechos no parser de texto - horario
        # lido assim nao sustenta proposta (mesma regra do checador)
        return None, "leitura parcial da GOL (%s)" % leitura.get("motivo")
    return leitura, None


def _ler_azul(ctx, loc, voo, supabase_url, service_key):
    origem = _origem_da_reserva(supabase_url, service_key, loc, voo.get("origem"))
    url = azul.montar_url(loc, origem)
    bloqueado, faltam = limitador_cloud.esta_bloqueado(supabase_url, service_key, url)
    if bloqueado:
        return None, "Azul em quarentena por mais %s min" % faltam
    limitador_cloud.aguardar(supabase_url, service_key, url)
    pagina, capturado = _capturar(ctx, url, azul.API_CAPTURA)
    try:
        recusa = e_bloqueio = None
        for _ in range(CICLOS_AZUL):
            pagina.wait_for_timeout(3000)
            recusa, e_bloqueio = azul.motivo_da_falha(capturado)
            if recusa or azul.resposta_do_booking(capturado):
                break
        texto = pagina.inner_text("body")
    finally:
        pagina.close()

    sinal = azul.sinal_de_bloqueio(texto)
    if sinal or e_bloqueio:
        # foi a Azul que limitou o IP da agencia (29/07/2026): bloqueio vale
        # pra rodada seguinte dos checadores tambem
        limitador_cloud.registrar_bloqueio(supabase_url, service_key, url)
        return None, "a Azul bloqueou o acesso (%s)" % (sinal or recusa)
    if recusa:
        return None, recusa
    booking = azul.resposta_do_booking(capturado)
    if booking is None:
        return None, "a API da Azul nao respondeu"
    leitura = azul.ler_api(booking.get("json"))
    if not leitura["encontrada"]:
        return None, "a API da Azul respondeu sem itinerario"
    devolvido = (leitura.get("localizador") or "").upper()
    if devolvido and devolvido != loc.upper():
        return None, "a Azul devolveu %s, esperado %s" % (devolvido, loc)
    if not leitura.get("confiavel") and not leitura.get("cancelada"):
        return None, "leitura parcial da Azul (%s)" % leitura.get("motivo")
    return leitura, None


def ler_reserva(cia, loc, voo, mf=None, supabase_url=None, service_key=None):
    """Le a reserva `loc` no portal da `cia`. Devolve (leitura, erro).

    `voo`: linha de `voos` do painel (origem, passageiros, emissao_id).
    `leitura` sai no formato comum dos parsers (encontrada, cancelada,
    segmentos[] com data/partida/chegada LOCAIS), mais `reacomodada` quando
    a GOL cai na tela de reacomodacao. Nunca levanta: portal fora do ar,
    Playwright ausente ou anti-bot viram `erro` e a reconferencia segue com
    a proxima fonte.
    """
    cia = (cia or "").upper()
    if cia not in FONTE:
        return None, "sem portal na nuvem para %s" % (cia or "cia vazia")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright nao instalado"
    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                PERFIL + "-" + cia.lower(), channel="chrome",
                headless=False,        # headless e barrado pelas cias
                locale="pt-BR", timezone_id="America/Sao_Paulo",
                viewport={"width": 1440, "height": 900})
            try:
                if cia == "LATAM":
                    return _ler_latam(ctx, loc, voo, mf)
                if cia == "GOL":
                    return _ler_gol(ctx, loc, voo, supabase_url, service_key)
                return _ler_azul(ctx, loc, voo, supabase_url, service_key)
            finally:
                ctx.close()
    except Exception as erro:
        return None, "portal %s falhou: %s" % (cia, str(erro)[:150])
