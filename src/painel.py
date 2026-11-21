"""Painel de conferencia manual para as companhias sem conector automatico.

Por que existe: a consulta automatizada da GOL completa em cerca de metade das
tentativas. A causa agora esta identificada - a API exige score de reCAPTCHA e
navegador automatizado tira score baixo, que varia por sessao. Era a hipotese
de reCAPTCHA, que antes eu tinha descartado por engano: a tela so diz "Houve um
erro" e o motivo real esta na resposta da API (ver gol.motivo_da_falha).

TAP, COPA, AIR FRANCE e QATAR nao tem conector nenhum.

A AZUL saiu daqui em 30/07/2026, quando ganhou conector - mas volta reserva a
reserva quando a checagem automatica falha, via dados/pendencias_azul.json.
Conector nao e garantia: se a consulta nao completa, a reserva tem de reaparecer
aqui, senao fica fora do automatico e fora do painel ao mesmo tempo.

No navegador normal os links funcionam. Entao o sistema monta os links ja
preenchidos e a conferencia vira clicar, em vez de redigitar localizador,
origem e sobrenome de cada reserva.

Uso:  python3 src/painel.py
"""

import csv
import html
import json
import os
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alertas
import qualidade
from config import config

# Como montar o link de cada companhia. None = sem link conhecido.
def link_gol(v):
    return "https://b2c.voegol.com.br/minhas-viagens/encontrar-viagem?" + \
        urllib.parse.urlencode({"codigoReserva": v["localizador"],
                                "origem": v["origem"],
                                "sobrenome": v["sobrenome"]})


def link_azul(v):
    return "https://www.voeazul.com.br/br/pt/home/minhas-viagens/confirmacao?" + \
        urllib.parse.urlencode({"pnr": v["localizador"], "origin": v["origem"]})


def link_tap(v):
    """PNR + sobrenome COMPLETO colado (ver qualidade.sobrenome_completo) -
    padrao do proprio MilhasFlow (myb.flytap.com/my-bookings/details/EF34GH/
    HERRERACHERREZ), validado no portal em 16/10/2026 com YZ34AB."""
    if not v.get("sobrenome_completo"):
        return None
    return "https://myb.flytap.com/my-bookings/details/%s/%s" % (
        urllib.parse.quote(v["localizador"]), urllib.parse.quote(v["sobrenome_completo"]))


def link_copa(v):
    """Rota trip-detail/:pnr/:surname/:language? do app mytrips.copaair.com
    (lida no bundle em 16/10/2026). Sem reserva Copa futura para validar: se
    o sobrenome nao bater, o proprio site cai no formulario de busca."""
    if not v.get("sobrenome_completo"):
        return None
    return "https://mytrips.copaair.com/trip-detail/%s/%s/pt" % (
        urllib.parse.quote(v["localizador"]), urllib.parse.quote(v["sobrenome_completo"]))


def link_generico(v):
    return None




_VINCULOS_LATAM = None      # cache: le o arquivo uma vez por processo


def vinculos_latam():
    """{PNR: numero de compra} descoberto por checar_latam.py.

    A LATAM nao tem link que se monte so com localizador+sobrenome, ao
    contrario da GOL/Azul: o parametro que o portal exige e o "numero de
    compra" (orderId, ex. LA9500000TEST), que so aparece no PDF - nao ha como
    derivar isso do PNR de 6 caracteres que o CRM guarda. Uma vez que
    checar_latam.py abre um PDF e casa o pedido com a reserva certa
    (comparacao.identificar), o vinculo fica salvo aqui (gravar_vinculos) e
    passa a valer para sempre, mesmo sem reabrir o PDF.
    """
    global _VINCULOS_LATAM
    if _VINCULOS_LATAM is None:
        caminho = os.path.join(config.pasta_dados, "vinculos_latam.json")
        try:
            with open(caminho, encoding="utf-8") as f:
                _VINCULOS_LATAM = json.load(f)
        except (IOError, OSError, ValueError):
            _VINCULOS_LATAM = {}
    return _VINCULOS_LATAM


def link_latam(v):
    """So monta quando ja se sabe o numero de compra desta reserva (ver
    vinculos_latam). Localizador nunca visto num PDF fica sem link - nao ha
    atalho: adivinhar o numero de compra manda o operador para uma pagina
    de erro no lugar da reserva.
    """
    pedido = vinculos_latam().get((v.get("localizador") or "").upper())
    if not pedido or not v.get("sobrenome"):
        return None
    return "https://www.latamairlines.com/br/pt/minhas-viagens/second-detail/?" + \
        urllib.parse.urlencode({"orderId": pedido, "lastname": v["sobrenome"]})


# Parametro de origem em cada portal
PARAM_ORIGEM = {"GOL": "origem", "AZUL": "origin"}


def corrigir_origem(url, voo):
    """Reescreve a origem do link para o primeiro trecho AINDA NAO VOADO.

    O link do PDF e gerado na emissao e congela a origem da ida. Numa reserva
    de ida e volta consultada depois da ida, ele aponta para um trecho que ja
    aconteceu - e a consulta falha. `voo` ja e a linha do primeiro trecho
    futuro (ver carregar()), entao a origem dele e a correta hoje.
    """
    chave = PARAM_ORIGEM.get(voo["cia"])
    if not chave or not voo.get("origem"):
        return url, False

    partes = urllib.parse.urlsplit(url)
    params = dict(urllib.parse.parse_qsl(partes.query))
    atual = (params.get(chave) or "").upper()
    if not atual or atual == voo["origem"].upper():
        return url, False

    params[chave] = voo["origem"]
    novo = urllib.parse.urlunsplit(
        partes[:3] + (urllib.parse.urlencode(params), partes[4]))
    return novo, True


MONTADORES = {"GOL": link_gol, "AZUL": link_azul, "LATAM": link_latam,
              "TAP": link_tap, "COPA": link_copa}


def links_dos_pdfs():
    """{PNR ou pedido: url} vindo do indice gerado por indexar_links.py.

    Fonte unica: o indice ja descarta o link do Smiles (exige login e nao mostra
    status) e as paginas de bagagem/assento. Se o indice nao existir, seguimos
    so com os links montados.
    """
    caminho = os.path.join(config.pasta_dados, "links_reservas.json")
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            indice = json.load(f)
    except (IOError, ValueError):
        return {}
    return {chave.upper(): reg["url"] for chave, reg in indice.items()
            if reg.get("url")}


CORES = {"critica": "#dc2626", "alta": "#ea580c",
         "media": "#ca8a04", "baixa": "#65a30d"}

# Companhias sem conector nenhum: entram sempre, por inteiro.
SEM_CONECTOR = ("TAP", "COPA", "AIR FRANCE", "QATAR AIRWAYS")

# Companhias cujo conector diz, a cada rodada, o que NAO conseguiu conferir.
# Elas saem do painel - repetir aqui o que a maquina ja conferiu faz o operador
# trabalhar duas vezes - e voltam reserva a reserva pelo arquivo de pendencias.
#
# A LATAM fica de fora desta lista de proposito: o conector dela nao publica
# pendencias, e sim `sem_pdf_latam.csv`, com outra semantica.
COM_PENDENCIAS = ("AZUL", "GOL")


def arquivo_de_pendencias(pasta_dados, cia):
    return os.path.join(pasta_dados, "pendencias_%s.json" % cia.lower())


def gravar_pendencias(pasta_dados, cia, pendentes, parcial=False):
    """Diz ao painel o que a checagem desta companhia NAO conferiu.

    `parcial` marca rodada que nao varreu a carteira toda (--loc, --limite,
    --capturar): as pendencias anteriores sao preservadas, porque quem nao foi
    consultado nesta rodada nao virou "conferido".
    """
    caminho = arquivo_de_pendencias(pasta_dados, cia)
    pendentes = [c.upper() for c in pendentes]
    if parcial:
        pendentes = sorted(set(pendentes) | ler_pendencias(pasta_dados, cia))
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"localizadores": sorted(set(pendentes))}, f,
                      ensure_ascii=False, indent=1)
    except IOError:
        pass
    return sorted(set(pendentes))


def ler_pendencias(pasta_dados, cia):
    """Localizadores que a checagem desta companhia nao conferiu."""
    try:
        with open(arquivo_de_pendencias(pasta_dados, cia), encoding="utf-8") as f:
            return {c.upper() for c in (json.load(f).get("localizadores") or [])}
    except (IOError, ValueError):
        return set()


def pendencias_com_conector(pasta_dados):
    """(localizadores a incluir, cias que entram inteiras).

    Conector automatico nao e garantia: a consulta pode falhar (API lenta, site
    fora) e a reserva precisa cair no painel, ou fica sem ninguem olhando - fora
    do automatico E fora da conferencia manual.

    Cia SEM arquivo de pendencia entra inteira: ou o conector nunca rodou, ou
    quebrou antes de publicar o resultado. Nos dois casos nao ha base para dizer
    que a carteira dela esta conferida. Na duvida o painel mostra a mais.
    """
    localizadores, cias_inteiras = set(), []
    for cia in COM_PENDENCIAS:
        if os.path.exists(arquivo_de_pendencias(pasta_dados, cia)):
            localizadores |= ler_pendencias(pasta_dados, cia)
        else:
            cias_inteiras.append(cia)
    return localizadores, cias_inteiras


def carregar():
    caminho = os.path.join(config.pasta_dados, "voos_atual.csv")
    if not os.path.exists(caminho):
        print("Rode ./rodar.sh antes — falta %s" % caminho)
        sys.exit(1)
    with open(caminho, encoding="utf-8-sig") as f:
        linhas = [l for l in csv.DictReader(f) if l["prioridade"] != "passado"]

    pendentes, cias_inteiras = pendencias_com_conector(config.pasta_dados)

    # uma linha por localizador: o portal mostra a reserva inteira de uma vez
    por_localizador = {}
    for l in linhas:
        se_encaixa = (l["cia"] in SEM_CONECTOR
                      or l["cia"] in cias_inteiras
                      or l["localizador"].upper() in pendentes)
        if not se_encaixa or not l["localizador"]:
            continue
        chave = (l["cia"], l["localizador"])
        if chave not in por_localizador or l["embarque_local"] < por_localizador[chave]["embarque_local"]:
            por_localizador[chave] = l
    ordem = {"critica": 0, "alta": 1, "media": 2, "baixa": 3, "indefinida": 4}
    return sorted(por_localizador.values(),
                  key=lambda l: (ordem.get(l["prioridade"], 9), l["embarque_local"]))


def link_para(v, do_pdf):
    """(url, origem_do_link) para uma reserva, ou (None, None) se nao ha como montar.

    1o o link do proprio bilhete (PDF); so depois o que montamos com o que o
    CRM tem. Mesma regra usada na tabela de conferencia e nos links prontos
    que vao no alerta.
    """
    url = do_pdf.get((v.get("localizador") or "").upper())
    origem_link = "PDF"
    if url:
        url, ajustada = corrigir_origem(url, v)
        if ajustada:
            origem_link = "PDF (origem ajustada)"
    if not url:
        v = dict(v, cia=qualidade.cia_pelo_voo(v.get("cia"), v.get("numero_voo")))
        montador = MONTADORES.get(v.get("cia"), link_generico)
        url = montador(v) if v.get("sobrenome") or v.get("cia") == "AZUL" else None
        origem_link = "montado"
    return (url, origem_link) if url else (None, None)


ESTILO = """
body{font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:24px;background:#f6f7f9;color:#111}
h1{font-size:20px;margin:0 0 4px} p.sub{color:#666;margin:0 0 20px;font-size:13px}
table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px #0001;border-radius:8px;overflow:hidden}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#666;padding:10px 12px;border-bottom:2px solid #eee}
td{padding:10px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
tr:hover td{background:#fafbfc}
.pri{display:inline-block;padding:2px 8px;border-radius:99px;color:#fff;font-size:11px;font-weight:600}
.loc{font-family:ui-monospace,Menlo,monospace;font-weight:600}
a.btn{display:inline-block;padding:6px 14px;background:#111;color:#fff;text-decoration:none;border-radius:6px;font-size:13px}
a.btn:hover{background:#333}
.na{color:#999;font-size:12px}
.fonte{font-size:10px;color:#999;margin-top:3px;text-align:center}
.bal{background:#eef2ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:11px;margin-left:6px}
.abas{display:flex;gap:8px;margin-bottom:16px}
.aba-btn{border:none;background:#e5e7eb;color:#333;padding:8px 16px;border-radius:8px 8px 0 0;font-size:13px;font-weight:600;cursor:pointer}
.aba-btn.ativa{background:#fff;box-shadow:0 1px 3px #0001}
.aba-btn.urg{background:#fee2e2;color:#991b1b}
.aba-btn.urg.ativa{background:#dc2626;color:#fff}
.vazio{background:#fff;border-radius:8px;padding:24px;text-align:center;color:#666;font-size:13px}
"""


def botao_abrir(url, origem_link):
    """Celula do botao Abrir, ou o aviso de que nao ha link. Usado nas duas abas."""
    if not url:
        return '<span class="na">sem link</span>'
    return ('<a class="btn" href="%s" target="_blank" rel="noopener">Abrir</a>'
            '<div class="fonte">%s</div>' % (html.escape(url), origem_link or ""))


def _tabela_urgente(urgentes):
    linhas = ["""<table><tr><th></th><th>Cia</th><th>Localizador</th><th>O que mudou</th>
<th>Passageiro</th><th></th></tr>"""]
    for u in urgentes:
        # mesmo mapa de cores do Telegram: um tipo novo aparece igual nos dois
        icone = alertas.ICONE.get(u.get("tipo"), "⚪")
        botao = botao_abrir(u.get("link"), u.get("fonte_link"))
        linhas.append(
            '<tr><td style="font-size:18px">%s</td><td>%s</td><td class="loc">%s</td>'
            '<td>%s</td><td>%s</td><td>%s</td></tr>' % (
                icone, html.escape(u.get("cia") or "?"), html.escape(u.get("localizador") or "?"),
                html.escape(u.get("detalhe") or ""), html.escape(u.get("passageiro") or ""), botao))
    linhas.append("</table>")
    return "\n".join(linhas)


def _arquivo_urgentes():
    return os.path.join(config.pasta_dados, "urgentes.json")


def _guardar_urgentes(urgentes):
    try:
        with open(_arquivo_urgentes(), "w", encoding="utf-8") as f:
            json.dump(urgentes, f, ensure_ascii=False)
    except IOError:
        pass


def _urgentes_guardados():
    try:
        with open(_arquivo_urgentes(), encoding="utf-8") as f:
            return json.load(f) or []
    except (IOError, ValueError):
        return []


def gerar(voos, caminho, do_pdf=None, urgentes=None):
    """Escreve o painel. `urgentes=None` significa "nao sei quais sao".

    Quem sabe e a rodada, que acabou de apurar os alertas - ela passa a lista,
    inclusive vazia para limpar a aba. Rodado a mao (`python3 src/painel.py
    --abrir`, que e o comando que o proprio resumo do Telegram manda usar), o
    painel nao tem como saber, entao reaproveita os da ultima rodada. Antes ele
    regerava com a aba vazia e apagava os alertas que o operador tinha acabado
    de ser mandado conferir - e eles nao voltam, porque ja estao notificados.
    """
    do_pdf = do_pdf or {}
    if urgentes is None:
        urgentes = _urgentes_guardados()
    else:
        _guardar_urgentes(urgentes)
    # a aba que abre primeiro e a que tem o que olhar
    urgente_ativa = bool(urgentes)
    partes = ["""<meta charset="utf-8"><title>Conferência de voos</title>
<style>%(estilo)s</style>
<h1>Conferência de voos</h1>
<div class="abas">
<button id="btn-urgente" class="aba-btn urg%(ativa_urgente)s" onclick="mostrarAba('urgente')">🚨 Urgente (%(n_urgentes)d)</button>
<button id="btn-conferir" class="aba-btn%(ativa_conferir)s" onclick="mostrarAba('conferir')">📋 Conferência manual (%(n_voos)d)</button>
</div>
<div id="aba-urgente" style="display:%(mostra_urgente)s">
<p class="sub">Reservas com alteração detectada nesta rodada. Clique em <b>Abrir</b> — o link já vai preenchido.</p>
%(tabela_urgente)s
</div>
<div id="aba-conferir" style="display:%(mostra_conferir)s">
<p class="sub">Companhias sem checagem automática, ou que a checagem automática não conseguiu confirmar. Clique em <b>Abrir</b> — o link já vai preenchido.
A LATAM não aparece aqui: é conferida sozinha pelo sistema.</p>
<table><tr><th>Prioridade</th><th>Cia</th><th>Localizador</th><th>Trecho</th>
<th>Embarque</th><th>Passageiro</th><th></th></tr>""" % {
        "estilo": ESTILO,
        "ativa_urgente": " ativa" if urgente_ativa else "",
        "ativa_conferir": "" if urgente_ativa else " ativa",
        "n_urgentes": len(urgentes),
        "n_voos": len(voos),
        "mostra_urgente": "" if urgente_ativa else "none",
        "mostra_conferir": "none" if urgente_ativa else "",
        "tabela_urgente": (_tabela_urgente(urgentes) if urgentes
                           else '<div class="vazio">Nenhuma alteração pendente.</div>'),
    }]

    for v in voos:
        url, origem_link = link_para(v, do_pdf)
        cor = CORES.get(v["prioridade"], "#666")
        balcao = '<span class="bal">balcão</span>' if v.get("balcao") == "1" else ""
        botao = botao_abrir(url, origem_link)
        partes.append(
            '<tr><td><span class="pri" style="background:%s">%s</span></td>'
            '<td>%s%s</td><td class="loc">%s</td><td>%s → %s</td><td>%s</td>'
            '<td>%s</td><td>%s</td></tr>' % (
                cor, v["prioridade"], html.escape(v["cia"]), balcao,
                html.escape(v["localizador"]), html.escape(v["origem"]),
                html.escape(v["destino"]), html.escape(v["embarque_local"]),
                html.escape((v.get("passageiros") or "")[:34]), botao))

    partes.append("""</table>
</div>
<script>
function mostrarAba(nome) {
  document.getElementById('aba-urgente').style.display = nome === 'urgente' ? '' : 'none';
  document.getElementById('aba-conferir').style.display = nome === 'conferir' ? '' : 'none';
  document.getElementById('btn-urgente').classList.toggle('ativa', nome === 'urgente');
  document.getElementById('btn-conferir').classList.toggle('ativa', nome === 'conferir');
}
</script>""")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))


def main():
    voos = carregar()
    do_pdf = links_dos_pdfs()
    caminho = os.path.join(config.pasta_dados, "conferencia.html")
    gerar(voos, caminho, do_pdf)

    print("%d reserva(s) para conferir:" % len(voos))
    contagem = {}
    for v in voos:
        contagem[v["cia"]] = contagem.get(v["cia"], 0) + 1
    for cia, n in sorted(contagem.items(), key=lambda i: -i[1]):
        print("  %-16s %d" % (cia, n))
    com_pdf = len([v for v in voos if v["localizador"].upper() in do_pdf])
    print("\n  com link do proprio bilhete: %d de %d" % (com_pdf, len(voos)))
    print("\n  %s" % caminho)

    if "--abrir" in sys.argv:
        abrir_sem_ativar(caminho)


def abrir_sem_ativar(caminho):
    """Abre o arquivo no Chrome sem trazer a janela para frente.

    "open -g" NAO basta: ele manda o evento padrao "Open URL" para o Chrome, e
    o proprio Chrome se ativa ao receber esse evento especifico, ignorando a
    flag. Contornar isso exige falar com o dicionario AppleScript do Chrome
    (criar a aba direto), que nao dispara essa ativacao.

    Se o Chrome nao estiver instalado ou o AppleScript falhar, cai para
    webbrowser.open() - abrir com foco e melhor que nao abrir nada.
    """
    url = "file://" + caminho
    escapada = url.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Google Chrome"\n'
        '  if (count of windows) = 0 then make new window\n'
        '  tell window 1 to make new tab with properties {URL:"%s"}\n'
        'end tell' % escapada
    )
    r = subprocess.run(["osascript", "-e", script], capture_output=True)
    if r.returncode != 0:
        import webbrowser
        webbrowser.open(url)


if __name__ == "__main__":
    main()
