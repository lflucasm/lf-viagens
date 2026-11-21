"""Teste avulso: a GOL responde a um deep link real quando o Chrome roda
num runner Linux (GitHub Actions) sob Xvfb, em vez do Mac?

So prova o navegador - nao mexe em CRM, banco nem Telegram. Existe pra
responder UMA pergunta antes de investir em checar_gol_cloud.py: no Mac
(IP residencial) a GOL ja falha ~50% por score de reCAPTCHA - IP de
datacenter pode piorar isso. Rodar algumas vezes e olhar a taxa.

Uso:  xvfb-run -a python3 scripts/teste_gol_headless.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import gol
from playwright.sync_api import sync_playwright

# TSTAFX: reserva real ativa (30/08/2026 NAT->GIG, ver conversa).
LOCALIZADOR = "TSTAFX"
ORIGEM = "NAT"
SOBRENOME = "LIMA"

URL_CONSULTA = ("https://b2c.voegol.com.br/minhas-viagens/encontrar-viagem"
                "?codigoReserva=%s&origem=%s&sobrenome=%s")
URL_DETALHE = "detalhes-da-viagem"


def _sucesso(capturado):
    """success:true no corpo da API - mesmo campo que gol.motivo_da_falha
    olha (`corpo.get("success") is False`), so que pro lado positivo."""
    for registro in capturado.values():
        corpo = registro.get("json")
        if isinstance(corpo, dict) and corpo.get("success") is True:
            return True
    return False


def main():
    url = URL_CONSULTA % (LOCALIZADOR, ORIGEM, SOBRENOME)
    capturado = {}

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            "/tmp/perfil-teste-gol",
            channel="chrome",
            headless=False,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )
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
        print("Abrindo %s" % url)
        pagina.goto(url, timeout=45000, wait_until="domcontentloaded")

        # espera a API responder E a pagina ter tempo de navegar depois - a
        # primeira versao deste teste parava assim que capturava a resposta,
        # sem dar tempo do redirect acontecer, e chamou de "FALHOU" um
        # success:true real (bug do teste, nao da GOL - ver conversa 20/08).
        limite = time.time() + 66
        while time.time() < limite:
            pagina.wait_for_timeout(3000)
            if URL_DETALHE in pagina.url:
                break
            if gol.motivo_da_falha(capturado):
                break
            if _sucesso(capturado):
                pagina.wait_for_timeout(3000)  # da tempo do redirect
                break

        print("\nURL final: %s" % pagina.url)
        print("Respostas capturadas: %d" % len(capturado))
        for r in capturado.values():
            print("  %s -> %s" % (r["url"], r["status"]))
            if r["json"]:
                print("  corpo: %s" % str(r["json"])[:300])

        recusa = gol.motivo_da_falha(capturado)
        if recusa:
            print("\n>>> FALHOU: %s" % recusa)
            ctx.close()
            sys.exit(1)

        if URL_DETALHE in pagina.url or _sucesso(capturado):
            print("\n>>> SUCESSO.")
            ctx.close()
            sys.exit(0)

        print("\n>>> FALHOU: nao chegou nem recusou em 66s (pagina lenta/rede?)")
        ctx.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
