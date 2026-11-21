"""Acesso a API de malha. Unica parte que fala com a rede.

Fica separada de proposito: `malha.py` e leitor puro e `checar_malha.py` e
orquestrador, entao trocar de fornecedor de dados nao encosta em nenhum dos
dois. E o mesmo desenho de navegador.py x latam.py x checar_latam.py.

O fornecedor de referencia e a AeroDataBox, distribuida por tres canais com
BASE e nome de cabecalho diferentes - por isso os dois vem do .env em vez de
ficarem cravados aqui:

    API.market (canal do OpenAPI oficial)
        MALHA_API_URL     https://prod.api.market/api/v1/aedbx/aerodatabox
        MALHA_API_HEADER  x-api-market-key

    RapidAPI
        MALHA_API_URL     https://aerodatabox.p.rapidapi.com
        MALHA_API_HEADER  x-rapidapi-key

O RapidAPI exige DOIS cabecalhos: a chave e o `x-rapidapi-host`. O host nao
precisa de configuracao - sai do proprio MALHA_API_URL (ver _cabecalhos()).

Diferente dos sites das companhias, aqui nao existe anti-bot: e API paga, com
chave, e chamar e o uso previsto. O que se protege e a COTA - por isso o teto
por rodada vive no orquestrador.
"""

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

TEMPO_LIMITE = 30          # s

# O plano BASIC do RapidAPI limita por SEGUNDO, nao so por mes: com 0.3s a
# resposta era 429 "rate limit per second". Com 1.2s ainda escapava um 429 a
# cada tantas chamadas (a retentativa salvava, mas atrasava); 1.5s passa limpo.
PAUSA = 1.5

# Identificacao honesta do cliente. NAO e disfarce de navegador: a origem da
# AeroDataBox fica atras de Cloudflare, que bloqueia o User-Agent padrao do
# Python ("Python-urllib/3.x") com erro 1010 browser_signature_banned - e
# devolvia 403 mesmo com a assinatura em ordem e a chave certa. Dizer quem
# somos resolve; mentir seria desnecessario e errado.
USER_AGENT = "LFViagens-ChecagemVoos/1.0 (monitoramento de reservas da agencia)"

# 429 tem dois sentidos bem diferentes e a mensagem os separa: excesso por
# SEGUNDO se resolve esperando; cota do periodo esgotada nao, e ai a rodada
# tem de parar em vez de insistir.
MARCA_POR_SEGUNDO = "per second"
TENTATIVAS_429 = 2
ESPERA_429 = 3.0           # s

# Erros que valem como falha de UM voo, nao da rodada inteira.
FALHA_DO_VOO = (urllib.error.URLError, socket.timeout, ValueError)


class MalhaIndisponivel(Exception):
    """Falha que interrompe a rodada: chave errada, cota estourada, fora do ar."""


class ProvedorMalha(object):
    def __init__(self, base, cabecalho, chave):
        self.base = (base or "").rstrip("/")
        self.cabecalho = cabecalho or ""
        self.chave = chave or ""
        self.chamadas = 0
        self.unidades_restantes = None
        self.unidades_limite = None
        self.segundos_para_reset = None
        self._ultima = 0.0

    def dias_para_reset(self):
        """Quantos dias faltam para a cota renovar. None se ainda nao se sabe."""
        if self.segundos_para_reset is None:
            return None
        return max(1, int(round(self.segundos_para_reset / 86400.0)))

    def configurado(self):
        return bool(self.base and self.cabecalho and self.chave)

    def _cabecalhos(self):
        """Cabecalhos da chamada.

        O RapidAPI recusa a chamada sem `x-rapidapi-host`. Em vez de virar mais
        uma linha no .env para o operador errar, o host e deduzido da propria
        URL - que ja tem que estar certa de qualquer forma.
        """
        cabecalhos = {self.cabecalho: self.chave,
                      "Accept": "application/json",
                      "User-Agent": USER_AGENT}
        host = urllib.parse.urlsplit(self.base).netloc
        if host.endswith(".rapidapi.com"):
            cabecalhos["x-rapidapi-host"] = host
        return cabecalhos

    def _anotar_cota(self, cabecalhos):
        """Guarda o saldo que o RapidAPI devolve em cada resposta.

        Vale mais que contar chamadas por fora: e o numero do fornecedor, e no
        plano BASIC a cota (600 unidades) e o que limita a cadencia - o
        endpoint de voo custa 2 unidades por consulta, nao 1.
        """
        try:
            restante = cabecalhos.get("X-RateLimit-API-Units-Remaining")
            limite = cabecalhos.get("X-RateLimit-API-Units-Limit")
            reset = cabecalhos.get("X-RateLimit-API-Units-Reset")
            if restante is not None:
                self.unidades_restantes = int(restante)
            if limite is not None:
                self.unidades_limite = int(limite)
            if reset is not None:
                # o cabecalho traz SEGUNDOS ate a renovacao, nao uma data
                self.segundos_para_reset = int(reset)
        except (TypeError, ValueError):
            pass

    def _pausar(self):
        espera = PAUSA - (time.time() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.time()

    def voo(self, numero, data):
        """Busca um voo por numero + data local de PARTIDA.

        Devolve (lista_de_contratos, erro). Lista vazia = a malha nao tem esse
        voo nessa data; NAO significa cancelado (pode ser data fora da
        cobertura do plano), e quem trata isso e malha.ler_resposta().

        dateLocalRole=Departure e deliberado: sem isso a API tambem devolve voo
        que apenas CHEGA nessa data, tendo partido no dia anterior, e a
        comparacao contra embarque_local acusaria data alterada sem motivo.
        """
        if not self.configurado():
            raise MalhaIndisponivel(
                "falta configurar MALHA_API_URL, MALHA_API_HEADER e MALHA_API_KEY no .env")

        caminho = "%s/flights/number/%s/%s" % (
            self.base, urllib.parse.quote(numero.replace(" ", "")),
            urllib.parse.quote(data))
        url = caminho + "?" + urllib.parse.urlencode({
            "dateLocalRole": "Departure",
            "withAircraftImage": "false",
            "withLocation": "false",
        })

        return self._pedir(url, tentativa=1)

    def _pedir(self, url, tentativa):
        self._pausar()
        pedido = urllib.request.Request(url, headers=self._cabecalhos())

        try:
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
                self.chamadas += 1
                self._anotar_cota(resposta.headers)
                if resposta.status == 204:
                    return [], None
                corpo = resposta.read().decode("utf-8", "replace")
                if not corpo.strip():
                    return [], None
                dados = json.loads(corpo)
                # o contrato diz array; um objeto solto ainda e aproveitavel
                return (dados if isinstance(dados, list) else [dados]), None
        except urllib.error.HTTPError as e:
            self.chamadas += 1
            self._anotar_cota(e.headers)
            corpo = ""
            try:
                corpo = e.read().decode("utf-8", "replace")
            except Exception:
                pass

            if e.code == 204:
                return [], None
            if e.code == 429:
                if MARCA_POR_SEGUNDO in corpo.lower() and tentativa <= TENTATIVAS_429:
                    # excesso por segundo: esperar resolve, e a cota nao acabou
                    time.sleep(ESPERA_429 * tentativa)
                    return self._pedir(url, tentativa + 1)
                raise MalhaIndisponivel(
                    "cota da API esgotada ou limite insistente (HTTP 429): %s"
                    % (_mensagem(corpo) or "sem detalhe"))
            if e.code in (401, 403):
                raise MalhaIndisponivel(_diagnostico_403(e.code, corpo))
            if e.code == 400:
                # dado ruim de UM voo nao derruba a rodada
                return None, "a API recusou a consulta (HTTP 400)"
            return None, "HTTP %d" % e.code
        except FALHA_DO_VOO as e:
            return None, str(e)[:120]


def _mensagem(corpo):
    """Extrai a mensagem de erro do JSON, se houver."""
    try:
        dados = json.loads(corpo)
    except (ValueError, TypeError):
        return (corpo or "").strip()[:160]
    if isinstance(dados, dict):
        for campo in ("message", "detail", "title"):
            if dados.get(campo):
                return str(dados[campo])[:160]
    return (corpo or "").strip()[:160]


def _diagnostico_403(codigo, corpo):
    """403 aqui tem duas causas muito diferentes - dizer qual poupa horas.

    O bloqueio de User-Agent pela Cloudflare da origem (erro 1010) devolve 403
    identico ao de chave invalida, mas o problema nao e a chave: a assinatura
    esta em ordem e a cota nem e consumida. Foi o que aconteceu em 29/07/2026.
    """
    if "1010" in corpo or "browser_signature" in corpo:
        return ("a origem da API bloqueou o User-Agent (Cloudflare 1010), nao a "
                "chave. Confira provedor_malha.USER_AGENT.")
    return ("a API recusou a chave (HTTP %d): %s. Confira MALHA_API_KEY e se "
            "MALHA_API_HEADER combina com o canal assinado."
            % (codigo, _mensagem(corpo) or "sem detalhe"))
