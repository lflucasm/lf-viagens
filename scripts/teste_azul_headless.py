"""Teste avulso: a Azul responde a um deep link real quando o Chrome roda
num runner Linux (GitHub Actions) sob Xvfb, em vez do Mac?

So prova o navegador - nao mexe em CRM nem Telegram, mas CONSULTA e
ATUALIZA a quarentena no Supabase (limitador_estado) antes e depois, porque
foi a Azul que ja limitou o IP da agencia uma vez (29/07/2026). Sem essa
trava nao se testa a Azul de jeito nenhum, nem uma vez.

Uso:
  SUPABASE_WEB_URL=... SUPABASE_WEB_SERVICE_KEY=... \
      xvfb-run -a python3 scripts/teste_azul_headless.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import azul
import limitador_cloud
from playwright.sync_api import sync_playwright

# AB12CD: reserva real ativa (20/08/2026 REC->GRU, ver conversa).
LOCALIZADOR = "AB12CD"
ORIGEM = "REC"

ESPERA_MAXIMA_CICLOS = 20


def _obrigatorio(nome):
    valor = os.environ.get(nome, "")
    if not valor:
        print("ERRO: variavel de ambiente %s nao definida." % nome)
        sys.exit(1)
    return valor


def main():
    supabase_url = _obrigatorio("SUPABASE_WEB_URL").rstrip("/")
    service_key = _obrigatorio("SUPABASE_WEB_SERVICE_KEY")

    url = azul.montar_url(LOCALIZADOR, ORIGEM)

    bloqueado, faltam = limitador_cloud.esta_bloqueado(supabase_url, service_key, url)
    if bloqueado:
        print("A Azul esta em quarentena (Supabase) por mais %d min. Nao insisto." % faltam)
        sys.exit(2)

    limitador_cloud.aguardar(supabase_url, service_key, url)

    capturado = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            "/tmp/perfil-teste-azul",
            channel="chrome",
            headless=False,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )
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
        print("Abrindo %s" % url)
        pagina.goto(url, timeout=45000, wait_until="domcontentloaded")

        for _ in range(ESPERA_MAXIMA_CICLOS):
            pagina.wait_for_timeout(3000)
            recusa, e_bloqueio = azul.motivo_da_falha(capturado)
            if recusa or azul.resposta_do_booking(capturado):
                break

        texto = pagina.inner_text("body")
        print("\nRespostas capturadas: %d" % len(capturado))
        for r in capturado.values():
            print("  %s -> %s" % (r["url"], r["status"]))

        sinal = azul.sinal_de_bloqueio(texto)
        if sinal or e_bloqueio:
            limitador_cloud.registrar_bloqueio(supabase_url, service_key, url)
            print("\n>>> BLOQUEADA: %s. Quarentena registrada no Supabase." % (sinal or recusa))
            ctx.close()
            sys.exit(1)

        booking = azul.resposta_do_booking(capturado)
        if booking is None:
            print("\n>>> FALHOU: a API nao respondeu em %ds." % (ESPERA_MAXIMA_CICLOS * 3))
            ctx.close()
            sys.exit(1)

        leitura = azul.ler_api(booking.get("json"))
        if leitura["encontrada"]:
            print("\n>>> SUCESSO: reserva lida, %d trecho(s)." % len(leitura["segmentos"]))
            ctx.close()
            sys.exit(0)

        print("\n>>> FALHOU: API respondeu sem itinerario.")
        ctx.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
