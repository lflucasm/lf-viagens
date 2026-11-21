"""Camada de navegador: abre o deep link e devolve o texto da pagina.

Usa o Chrome real da maquina, nunca headless: o portal da LATAM detecta
headless e a API simplesmente nao responde (34 de 34 falharam no teste).
Quando a rodada e automatica, a janela e posicionada fora da tela.

Posicionar fora da tela NAO basta para nao incomodar: o PROCESSO do Chrome
ainda vira o app em primeiro plano, interrompendo o que o operador estiver
fazendo, mesmo sem janela visivel. E acontece de novo a CADA aba nova, nao so
quando o Chrome abre - medido em 30/07/2026: reativar so uma vez em __enter__
nao bastou, porque new_page() rouba o foco de volta a cada reserva checada.
Por isso _nova_pagina() reativa depois de toda aba criada, nao so na abertura.

Por PID, nao por nome: o Chrome do Playwright e o Chrome normal do operador se
chamam igual ("Google Chrome"), entao reativar por nome e ambiguo entre os
dois processos e pode devolver a janela errada. Via AppleScript (System
Events), que pode pedir permissao de Automacao na primeira vez (Ajustes do
Sistema > Privacidade e Seguranca > Automacao).

O perfil e recriado a cada rodada (perfil_limpo=True). Nao dependemos de
sessao salva, e perfil acumulado passou a derrubar o Chrome no meio da
execucao.

Regra que nao se quebra: se a pagina nao carregar ou aparecer desafio, o
sistema NAO insiste. Marca para conferencia manual e segue. Robo teimoso e o
que derruba IP e trava conta.
"""

import os
import shutil
import subprocess
import time

import limitador

PERFIL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".perfil-chrome")

TEMPO_LIMITE = 45000               # ms

# Sinais de que a companhia limitou o acesso. Aparecendo isso, a rodada para.
SINAIS_DE_BLOQUEIO = (
    "comportamento incomum",
    "acesso foi limitado",
    "access denied",
    "unusual traffic",
)


class NavegadorIndisponivel(Exception):
    pass


def _pid_frontmost():
    """PID do app em primeiro plano agora, ou None se nao der pra saber.

    PID, nao nome: o Chrome do Playwright roda com perfil proprio, processo
    separado do Chrome normal que o operador ja tenha aberto - mas os dois se
    chamam "Google Chrome". Reativar por NOME e ambiguo entre eles e pode
    simplesmente trazer a janela nova de volta, que foi o que aconteceu na
    pratica em 30/07/2026. Por PID nao tem como confundir os dois processos.

    `lsappinfo`, nao `osascript`: e ~10x mais rapido (~15ms contra ~135ms) por
    nao carregar o runtime do AppleScript so para LER quem esta em primeiro
    plano. So a reativacao (_reativar) precisa do osascript de verdade -
    `lsappinfo setfront` existe mas devolve ERROR -54 permErr por aqui.
    """
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        if not asn:
            return None
        saida = subprocess.run(["lsappinfo", "info", "-only", "pid", asn],
                               capture_output=True, text=True, timeout=2).stdout
        return int(saida.rsplit("=", 1)[-1].strip())
    except (ValueError, IndexError, subprocess.SubprocessError, OSError):
        return None


def _reativar(pid):
    """Traz esse processo de volta ao primeiro plano. Falha calada - nao e critico."""
    if not pid:
        return
    try:
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to set frontmost of '
             '(first application process whose unix id is %d) to true' % pid],
            capture_output=True, timeout=5)
    except Exception:
        pass


def _reativar_rapido(pid_alvo, tentativas=4, intervalo=0.08):
    """Confere se o foco mudou e reage na hora, em vez de dormir um tempo fixo
    e so entao reativar.

    Medido em 30/07/2026: dormir 0.3-0.4s antes de checar deixava o Chrome
    visivel por essa janela inteira, mesmo quando o roubo de foco e quase
    instantaneo (confirmado: acontece antes do PRIMEIRO check, sempre). Aqui
    o primeiro check ja acontece sem espera nenhuma; so ha pausa ENTRE
    tentativas, para o caso raro de pegar o instante exato da troca.
    """
    if not pid_alvo:
        return
    for _ in range(tentativas):
        atual = _pid_frontmost()
        if atual is not None and atual != pid_alvo:
            _reativar(pid_alvo)
            return
        time.sleep(intervalo)


class Navegador(object):
    """Context manager que mantem UM Chrome aberto para toda a rodada."""

    def __init__(self, visivel=True, discreto=False, perfil_limpo=False):
        # headless NAO serve para a LATAM: o anti-bot detecta e a API nunca
        # responde (testado em 29/07/2026, 34 de 34 falharam). Quando a rodada
        # e automatica usamos janela real posicionada fora da tela.
        self.visivel = visivel
        self.discreto = discreto
        # Perfil acumulado corrompe: em 29/07/2026 chegou a 247 MB e passou a
        # derrubar o Chrome no meio da rodada (TargetClosedError), o que eu
        # tinha diagnosticado errado como bloqueio por bot. Comecar limpo
        # resolve e nao custa nada - nao dependemos de sessao salva.
        self.perfil_limpo = perfil_limpo
        self._pw = None
        self._ctx = None
        self._ultima = 0.0
        self._pid_anterior = None   # quem estava em primeiro plano antes de tudo

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise NavegadorIndisponivel(
                "Playwright nao instalado. Rode:  .venv/bin/pip install playwright")

        if self.perfil_limpo and os.path.isdir(PERFIL):
            shutil.rmtree(PERFIL, ignore_errors=True)

        # Posicionar a janela fora da tela nao impede o PROCESSO de virar o
        # app em primeiro plano - sao coisas independentes no macOS. Guardamos
        # quem estava ativo antes de abrir, para devolver o foco depois de
        # cada aba nova (ver _nova_pagina).
        self._pid_anterior = _pid_frontmost() if self.discreto else None

        self._pw = sync_playwright().start()
        argumentos = ["--window-position=-3000,-3000"] if self.discreto else []
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(
                PERFIL,
                channel="chrome",          # Chrome de verdade, nao o Chromium empacotado
                headless=False,            # headless e detectado; nunca usar
                args=argumentos,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1440, "height": 900},
            )
        except Exception as e:
            self._pw.stop()
            raise NavegadorIndisponivel("Nao consegui abrir o Chrome: %s" % e)

        _reativar_rapido(self._pid_anterior)
        return self

    def __exit__(self, *_):
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()

    def _nova_pagina(self):
        """new_page(), reativando quem estava em primeiro plano em seguida.

        Medido em 30/07/2026: reativar so ao abrir o Chrome (em __enter__) nao
        basta - o Chrome rouba o foco de novo a CADA aba nova, e uma rodada
        abre uma aba por reserva checada. Sem isso aqui, a 1a reserva ficava
        certa e a 2a em diante devolvia o foco ao Chrome.

        Quem estava na frente AGORA, e nao o `_pid_anterior` congelado la no
        __enter__: se o operador trocou de app no meio da rodada, e para o app
        DELE que o foco tem de voltar. Comparando com o PID congelado, cada aba
        nova arrancava ele de volta para o Terminal - dezenas de vezes seguidas,
        o oposto do que este codigo existe para fazer.
        """
        antes = _pid_frontmost() if self.discreto else None
        pagina = self._ctx.new_page()
        _reativar_rapido(antes)
        return pagina

    def _respirar(self, url):
        """Espaca as consultas; rajada e o que dispara bloqueio.

        O controle vive no limitador, em arquivo, para valer tambem entre
        processos - foi exatamente por falta disso que a Azul limitou o IP.
        """
        bloqueado, faltam = limitador.esta_bloqueado(url)
        if bloqueado:
            raise limitador.LimiteExcedido(
                "%s esta em quarentena por mais %d min (bloqueio anterior)."
                % (limitador.dominio(url), faltam))
        limitador.aguardar(url)

    def _conferir_bloqueio(self, url, texto):
        """Detectou bloqueio? Poe o dominio de quarentena e interrompe."""
        if not texto:
            return
        baixo = texto[:1500].lower()
        if any(s in baixo for s in SINAIS_DE_BLOQUEIO):
            limitador.registrar_bloqueio(url)
            raise limitador.LimiteExcedido(
                "%s bloqueou o acesso. Rodada interrompida - nao insista hoje."
                % limitador.dominio(url))

    def abrir(self, url, capturar=None):
        """Abre a URL e devolve a pagina, para fluxos que exigem interacao.

        Passa pelo limitador igual aos demais metodos - e o caminho unico. Foi
        exatamente por ter fluxo fora daqui que a Azul limitou o IP.

        capturar: trecho de URL cujas respostas serao guardadas em
        pagina.capturado (dict url -> {"url", "status", "json"}), para ler a
        API que a pagina consome.

        O status vem junto de proposito: quando a API recusa a consulta, o
        motivo esta no corpo de uma resposta de ERRO. Guardar so o JSON das
        respostas que deram certo deixa a falha invisivel - foi o que fez a
        GOL parecer "pagina que nao carregou" durante dias.
        """
        self._respirar(url)
        pagina = self._nova_pagina()
        pagina.capturado = {}

        if capturar:
            def ao_responder(resposta):
                if capturar not in resposta.url:
                    return
                registro = {"url": resposta.url, "status": resposta.status,
                            "json": None}
                try:
                    registro["json"] = resposta.json()
                except Exception:
                    pass  # resposta sem JSON: o status ainda diz algo
                pagina.capturado[resposta.url] = registro
            pagina.on("response", ao_responder)

        pagina.goto(url, timeout=TEMPO_LIMITE, wait_until="domcontentloaded")
        return pagina

    def json_da_api(self, url, padrao_api, espera_ms=12000):
        """Abre a URL e devolve (json, erro) da primeira resposta que casar.

        Ler a API que a propria pagina consome e mais confiavel que raspar a
        tela: vem completo, estruturado e com os codigos de status do trecho.
        """
        self._respirar(url)
        pagina = self._nova_pagina()
        capturado = {}

        def ao_responder(resposta):
            if padrao_api in resposta.url and not capturado:
                try:
                    capturado["dados"] = resposta.json()
                except Exception:
                    pass

        pagina.on("response", ao_responder)
        try:
            pagina.goto(url, timeout=TEMPO_LIMITE, wait_until="domcontentloaded")
            limite = time.time() + espera_ms / 1000.0
            while not capturado and time.time() < limite:
                pagina.wait_for_timeout(500)
            if capturado:
                return capturado["dados"], None
            return None, "a API nao respondeu"
        except Exception as e:
            return None, str(e)[:200]
        finally:
            pagina.close()

    def texto_da_pagina(self, url, expandir=None, esperar=None):
        """Abre a URL e devolve (texto, erro).

        expandir: seletor CSS de acordeoes a abrir antes de ler - a LATAM
        entrega o trecho de volta recolhido, e sem abrir ele parece sumido.
        """
        self._respirar(url)
        pagina = self._nova_pagina()
        try:
            pagina.goto(url, timeout=TEMPO_LIMITE, wait_until="domcontentloaded")
            if esperar:
                try:
                    pagina.wait_for_selector(esperar, timeout=20000)
                except Exception:
                    pass
            pagina.wait_for_timeout(4000)   # SPA: deixa o conteudo assentar

            if expandir:
                for item in pagina.query_selector_all(expandir):
                    try:
                        item.click(timeout=3000)
                        pagina.wait_for_timeout(700)
                    except Exception:
                        pass  # acordeao ja aberto ou nao clicavel
                pagina.wait_for_timeout(1500)

            corpo = pagina.inner_text("body")
            self._conferir_bloqueio(url, corpo)
            return corpo, None
        except Exception as e:
            return None, str(e)[:200]
        finally:
            pagina.close()
