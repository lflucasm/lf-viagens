"""Nome do passageiro lido do voucher (PDF) anexado na venda da Volly.

Por que existe: em 07/10/2026, 37 dos 180 trechos futuros chegavam ao painel
sem nome de passageiro - a venda tem `passengers_data` com `name` vazio (ou
nem tem venda vinculada) e a busca por passageiro do site nao os achava
(caso TSTAGX, Matheus Botton). O `passenger_name` do trecho cobre parte, mas
as vezes e so sobrenome ("De Miranda"). O voucher anexado na venda
(`emission_attachments`, file_type 'ticket') traz o nome completo de todos.

Formatos encontrados nos 64 bilhetes da Volly em 07/10/2026:
  bilhete gerado pela Volly   "PASSAGEIROS 1 passageiro" + "01 NOME"
  bilhete GOL antigo da Volly "PASSAGEIRO 1" + nome em 1-3 linhas
  comprovante LATAM (-cuv)    "Nome do Passageiro ..." + "NOME Adulto 0488..."
  reserva da consolidadora    tabela "Adulto" / SOBRENOME / NOME MR
Formato desconhecido devolve [] e o trecho cai pro passenger_name.

So LE da Volly. O PDF so e baixado pra trecho futuro cuja venda veio sem
nome - poucos por rodada (2 em 07/10/2026), nada de baixar os 64 sempre.
"""

import io
import re
from datetime import datetime, timezone

import sync

# PDF de bilhete tem 1-3 paginas; o nome sempre esta na primeira ou segunda
PAGINAS_LIDAS = 4
# teto de downloads por rodada da ingestao (cada PDF tem ate ~2 MB)
MAXIMO_DOWNLOADS = 30

TIPOS_PASSAGEIRO = ("ADULTO", "CRIANCA", "CRIANÇA", "BEBE", "BEBÊ", "INFANTE")
PARTICULAS = {"de", "da", "do", "das", "dos", "e", "di", "del"}

_LINHA_NOME = re.compile(r"^[A-ZÀ-Ý][A-ZÀ-Ý' .-]*$")
_TRATAMENTO = re.compile(r"\s+(MR|MRS|MS|MSTR|MISS|CHD|INF|SR|SRA)\.?$")
_CABECALHO_VOLLY = re.compile(r"^PASSAGEIROS\s+\d+\s+passageiros?$", re.I)
_ITEM_VOLLY = re.compile(r"^\d{2}\s+(.+)$")
_CABECALHO_GOL = re.compile(r"^PASSAGEIRO\s+\d+$")
_LINHA_LATAM = re.compile(r"^(.+?)\s+(Adulto|Criança|Crianca|Bebê|Bebe|Infante)\b")
# localizador no nome do arquivo: bilhete_tap_MN78OP_179...pdf, reserva_TSTAJX.pdf
_LOCALIZADOR_ARQUIVO = re.compile(r"(?<![A-Z0-9])[A-Z0-9]{6}(?![A-Z0-9])")


def formatar_nome(bruto):
    """'DE ALMEIDA PRADO  MARIANA MS' -> 'De Almeida Prado Mariana' (sem o
    tratamento, particulas em minuscula). None se nao parece nome."""
    nome = _TRATAMENTO.sub("", re.sub(r"\s+", " ", (bruto or "").strip().upper()))
    if not nome or not _LINHA_NOME.match(nome) or len(nome) < 3:
        return None
    palavras = [p.lower() if p.lower() in PARTICULAS else p.capitalize()
                for p in nome.split(" ")]
    if palavras[0] in PARTICULAS:  # "DE MIRANDA ..." no comeco
        palavras[0] = palavras[0].capitalize()
    return " ".join(palavras)


def _volly(linhas):
    for i, linha in enumerate(linhas):
        if _CABECALHO_VOLLY.match(linha):
            nomes = []
            for seguinte in linhas[i + 1:]:
                item = _ITEM_VOLLY.match(seguinte)
                if not item:
                    break
                nomes.append(item.group(1))
            return nomes
    return []


def _gol_antigo(linhas):
    nomes = []
    for i, linha in enumerate(linhas):
        if _CABECALHO_GOL.match(linha):
            partes = []
            for seguinte in linhas[i + 1:i + 4]:
                if not _LINHA_NOME.match(seguinte) or _CABECALHO_GOL.match(seguinte):
                    break
                partes.append(seguinte)
            if partes:
                nomes.append(" ".join(partes))
    return nomes


def _latam_cuv(linhas):
    for i, linha in enumerate(linhas):
        if linha.startswith("Nome do Passageiro"):
            nomes = []
            for seguinte in linhas[i + 1:]:
                item = _LINHA_LATAM.match(seguinte)
                if not item:
                    break
                nomes.append(item.group(1))
            return nomes
    return []


def _consolidadora(linhas):
    """Tabela da reserva: tipo / SOBRENOME / NOME MR, um passageiro por bloco."""
    nomes = []
    for i in range(len(linhas) - 2):
        if linhas[i].upper() not in TIPOS_PASSAGEIRO:
            continue
        sobrenome, nome = linhas[i + 1], linhas[i + 2]
        if _LINHA_NOME.match(sobrenome) and _LINHA_NOME.match(nome):
            nomes.append("%s %s" % (_TRATAMENTO.sub("", nome), sobrenome))
    return nomes


def nomes_do_texto(texto):
    """Nomes dos passageiros no texto do voucher, ja formatados e sem
    repeticao. Primeiro formato que achar alguem ganha."""
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    for leitor in (_volly, _latam_cuv, _consolidadora, _gol_antigo):
        nomes = []
        for bruto in leitor(linhas):
            nome = formatar_nome(bruto)
            if nome and nome not in nomes:
                nomes.append(nome)
        if nomes:
            return nomes
    return []


def nomes_do_pdf(dados):
    """Le o PDF (bytes) com pypdf. Import aqui dentro: so a ingestao da
    nuvem instala pypdf; o resto do sistema nao precisa dele."""
    import pypdf
    leitor = pypdf.PdfReader(io.BytesIO(dados))
    texto = "\n".join((p.extract_text() or "") for p in leitor.pages[:PAGINAS_LIDAS])
    return nomes_do_texto(texto)


def localizadores_no_arquivo(nome_arquivo):
    return set(_LOCALIZADOR_ARQUIVO.findall((nome_arquivo or "").upper()))


def _futuro(trecho, agora):
    try:
        momento = datetime.fromisoformat((trecho.get("departure_datetime") or "")
                                         .replace("Z", "+00:00"))
    except ValueError:
        return False
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento > agora


def chaves_sem_nome(voos_api, emissoes_api, agora=None):
    """{emission_id e localizador} dos trechos futuros cuja venda nao tem
    nome de passageiro - so pra esses vale baixar voucher."""
    agora = agora or datetime.now(timezone.utc)
    nomes_venda = {e["id"]: sync._nomes_passageiros(e.get("passengers_data"))
                   for e in emissoes_api}
    chaves = set()
    for v in voos_api:
        if not _futuro(v, agora) or nomes_venda.get(v.get("emission_id")):
            continue
        if v.get("emission_id"):
            chaves.add(v["emission_id"])
        localizador = (v.get("locator") or "").strip().upper()
        if localizador:
            chaves.add(localizador)
    return chaves


def anexos_relevantes(anexos, emissoes_api, procuradas):
    """[(anexo, chaves)] dos bilhetes que servem a algum trecho procurado.
    Um bilhete vale pela venda onde esta anexado, pelo localizador dessa
    venda e pelo localizador no nome do arquivo - trecho sem venda vinculada
    (TSTAJX, MN78OP) so e achado por esses dois ultimos."""
    localizador_venda = {e["id"]: (e.get("localizador") or "").strip().upper()
                         for e in emissoes_api}
    relevantes = []
    for anexo in anexos:
        if not (anexo.get("file_name") or "").lower().endswith(".pdf"):
            continue
        chaves = {anexo.get("emission_id"), localizador_venda.get(anexo.get("emission_id"))}
        chaves |= localizadores_no_arquivo(anexo.get("file_name"))
        chaves.discard(None)
        chaves.discard("")
        if chaves & procuradas:
            relevantes.append((anexo, chaves))
    return relevantes


def nomes_por_reserva(mf, voos_api, emissoes_api, agora=None):
    """{emission_id ou localizador: "Nome A / Nome B"} lido dos vouchers.

    Erro num PDF (download, formato) so pula aquele PDF; quem chama ainda
    protege a rodada inteira - nome de voucher e enfeite, nao pode derrubar
    a ingestao.
    """
    procuradas = chaves_sem_nome(voos_api, emissoes_api, agora)
    if not procuradas:
        return {}
    relevantes = anexos_relevantes(mf.buscar_bilhetes_anexados(), emissoes_api, procuradas)
    achados = {}
    for anexo, chaves in relevantes[:MAXIMO_DOWNLOADS]:
        try:
            nomes = nomes_do_pdf(mf.baixar_anexo(anexo["file_url"]))
        except ImportError:
            print("AVISO: pypdf nao instalado - nomes de voucher desligados nesta rodada")
            return {}
        except Exception as erro:
            print("AVISO: voucher %s ilegivel (%s)" % (anexo.get("file_name"), erro))
            continue
        for chave in chaves:
            lista = achados.setdefault(chave, [])
            lista.extend(n for n in nomes if n not in lista)
    if len(relevantes) > MAXIMO_DOWNLOADS:
        print("AVISO: %d vouchers a ler, so %d nesta rodada"
              % (len(relevantes), MAXIMO_DOWNLOADS))
    return {chave: " / ".join(nomes) for chave, nomes in achados.items() if nomes}
