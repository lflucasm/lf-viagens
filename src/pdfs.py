"""Indexa os PDFs das reservas e extrai os deep links das companhias.

Por que isso existe: o CRM guarda o PNR de 6 caracteres, mas a LATAM consulta
por "numero de compra" (orderId, ex. LA9500000TEST), que so aparece no PDF.
O PDF e a ponte entre os dois - e o deep link entra direto no portal, sem
formulario e sem o bloqueio de bot que barra a busca manual da LATAM.

Formatos encontrados nos PDFs da agencia:
  LATAM  /minhas-viagens/second-detail/?orderId=LA9500000TEST&lastname=Santana
  LATAM  /cartao-de-embarque?orderId=...&lastName=...
  AZUL   /home/minhas-viagens/confirmacao?pnr=IJ56KL&origin=BSB
  SMILES /minha-conta/meus-voos/selecionar-assentos?pnr=TSTALX
"""

import os
import re
import zlib

URL = re.compile(rb'https?://[^\s()<>"\'\]]{10,300}')
PNR = re.compile(r"\b[A-Z0-9]{6}\b")

# host + caminho -> companhia
PORTAIS = (
    ("latamairlines.com", "LATAM"),
    ("voeazul.com.br", "AZUL"),
    ("smiles.com.br", "GOL"),      # Smiles e o programa da GOL
    ("voegol.com.br", "GOL"),
)

PARAMS_UTEIS = re.compile(r"(orderId|lastName|lastname|pnr|origin)=([^&#]+)", re.I)


def _urls(caminho):
    """URLs do PDF, inclusive dentro de streams comprimidos."""
    with open(caminho, "rb") as f:
        dados = f.read()

    achados = set(URL.findall(dados))
    for m in re.finditer(rb"stream\r?\n", dados):
        inicio = m.end()
        fim = dados.find(b"endstream", inicio)
        if fim < 0:
            continue
        try:
            achados.update(URL.findall(zlib.decompress(dados[inicio:fim])))
        except zlib.error:
            pass  # stream nao comprimido ou com filtro diferente
    return {u.decode("utf-8", "replace").rstrip("\\") for u in achados}


def _texto(caminho):
    """Conteudo bruto + streams descomprimidos, para procurar o PNR."""
    with open(caminho, "rb") as f:
        dados = f.read()

    partes = [dados]
    for m in re.finditer(rb"stream\r?\n", dados):
        inicio = m.end()
        fim = dados.find(b"endstream", inicio)
        if fim < 0:
            continue
        try:
            partes.append(zlib.decompress(dados[inicio:fim]))
        except zlib.error:
            pass
    return b" ".join(partes).decode("latin-1", "replace").upper()


def _companhia(url):
    for host, cia in PORTAIS:
        if host in url:
            return cia
    return None


def indexar(pasta, pnrs_conhecidos):
    """Varre a pasta e devolve {PNR: {cia, url, params}}.

    O PNR sai do nome do arquivo ou do proprio conteudo - so aceitamos PNR que
    o CRM conhece, para nao inventar vinculo errado.
    """
    conhecidos = {p.upper() for p in pnrs_conhecidos if p}
    indice = {}

    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith(".pdf"):
            continue
        caminho = os.path.join(pasta, nome)

        try:
            urls = _urls(caminho)
        except (IOError, OSError):
            continue

        links = []
        for url in urls:
            cia = _companhia(url)
            params = dict((k.lower(), v) for k, v in PARAMS_UTEIS.findall(url))
            if cia and params:
                links.append((cia, url, params))
        if not links:
            continue

        # 1) PNR no proprio link (Azul e Smiles trazem pnr=)
        candidatos = []
        for _, _, params in links:
            if params.get("pnr"):
                candidatos.append(params["pnr"].upper())

        # 2) PNR no nome do arquivo
        base = os.path.splitext(nome)[0].upper()
        candidatos += [p for p in PNR.findall(base) if p in conhecidos]

        # 3) PNR no conteudo do PDF
        if not any(c in conhecidos for c in candidatos):
            try:
                candidatos += [p for p in set(PNR.findall(_texto(caminho)))
                               if p in conhecidos]
            except (IOError, OSError):
                pass

        pnr = next((c for c in candidatos if c in conhecidos), None)
        if not pnr:
            continue

        # um PDF pode ter varios links; o de gerenciamento vale mais que o
        # de cartao de embarque, que so funciona perto do voo
        links.sort(key=lambda l: ("cartao-de-embarque" in l[1], "check-in" in l[1]))
        cia, url, params = links[0]
        indice[pnr] = {"cia": cia, "url": url, "params": params, "arquivo": nome}

    return indice
