"""Rodada completa: sincroniza, checa, avisa.

E o comando que o agendador chama. Junta as pecas:
  1. sincroniza os voos do MilhasFlow (sempre - e barato e local)
  2. checa nos portais o que a cadencia mandar
  3. manda no Telegram o que ainda nao foi avisado

A cadencia evita consulta inutil: voo de outubro nao precisa de checagem de 6
em 6 horas, e voo de amanha nao pode esperar um dia.

Uso:  .venv/bin/python src/rodada.py [--sem-portal] [--resumo]
"""

import html
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agenda
import alertas
import db
import fusos
import manutencao
import painel
import qualidade
import sincronizar_web
from config import config

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Acima disso a rodada segura tudo e pede revisao (ver comentario no main).
TETO_DE_ALERTAS = 15

# Tipos que justificam repetir o aviso no fim do dia. Sao os que exigem acao
# (remissao, nova rota) e nao podem se perder numa mensagem da manha.
TIPOS_CRITICOS = ("trecho_cancelado", "cancelamento", "reserva_perdida",
                  "ausente_na_companhia", "acao_necessaria")

# Conectores por companhia, na ordem em que a rodada os chama. Quem entra aqui
# passa a ser conferido sozinho, na cadencia de CADENCIA_HORAS.
CONECTORES = (
    ("LATAM", "src/checar_latam.py", ["--invisivel"]),
    ("GOL", "src/checar_gol.py", []),
    ("AZUL", "src/checar_azul.py", []),
)

# Codigo de saida que NAO e falha. checar_azul.py usa 2 para "companhia em
# quarentena": e o limitador funcionando, e alertar sobre isso a cada rodada
# transformaria a protecao em ruido.
SAIDA_NAO_E_FALHA = {2}

# Quantas horas entre checagens de portal, conforme a proximidade do embarque
CADENCIA_HORAS = (
    (48, 6),          # embarque em ate 2 dias -> a cada 6h
    (24 * 7, 12),     # ate 7 dias -> 2x ao dia
    (24 * 30, 24),    # ate 30 dias -> 1x ao dia
    (None, 24 * 7),   # mais longe -> 1x por semana
)


def cadencia(horas_ate_voo):
    for limite, intervalo in CADENCIA_HORAS:
        if limite is None or horas_ate_voo <= limite:
            return intervalo
    return 24 * 7


def ultima_checagem(con, cia):
    """Quando esta companhia foi olhada pela ultima vez.

    Sai de `observacoes` antes do historico de alertas, e a diferenca importa:
    conector que roda e nao encontra nada NAO gera alerta nenhum. Medindo pelo
    historico, uma companhia sem novidade fica para sempre em "nunca checado" e
    e reconsultada em toda rodada - gasto a toa na LATAM e na GOL, e risco real
    na Azul, que ja limitou o IP da agencia uma vez.

    O historico continua entrando no calculo por causa das checagens antigas,
    anteriores a existencia da tabela de observacoes.
    """
    origem = "portal-%s" % cia.lower()
    marcas = [
        con.execute("SELECT MAX(visto_em) FROM observacoes WHERE origem=?",
                    (origem,)).fetchone()[0],
        con.execute("SELECT MAX(detectado_em) FROM historico WHERE origem=?",
                    (origem,)).fetchone()[0],
    ]
    validas = [m for m in marcas if m]
    return max(validas) if validas else None


def precisa_checar_portal(con, cia):
    """Algum voo dessa companhia esta vencido de checagem?"""
    ultima = ultima_checagem(con, cia)

    for linha in con.execute("SELECT embarque FROM voos WHERE ativo=1 AND cia=?",
                             (cia,)):
        horas = fusos.horas_ate(linha["embarque"])
        if horas is None or horas < 0:
            continue
        if ultima is None:
            return True, "nunca checado"
        try:
            passou = (datetime.now() - datetime.fromisoformat(ultima)).total_seconds() / 3600
        except ValueError:
            return True, "sem registro valido"
        if passou >= cadencia(horas):
            return True, "ultima checagem ha %.0fh" % passou
    return False, "em dia"


# Como chamar cada fonte na mensagem. A origem crua ("portal-azul") e nome de
# codigo; quem le o Telegram quer saber de onde veio a informacao.
NOME_DA_FONTE = {
    "malha": "malha da companhia",
    "portal-latam": "portal LATAM",
    "portal-gol": "portal GOL",
    "portal-azul": "portal Azul",
    "cruzamento": "cruzamento de fontes",
}


def origens_de_partida(con):
    """{localizador: origem do primeiro trecho AINDA NAO VOADO}.

    E essa a origem que os portais pedem, e nao a do trecho que mudou. Numa ida
    e volta GRU→NAT / NAT→GRU em que a companhia remarca a VOLTA, usar a origem
    do trecho alterado monta o link com NAT enquanto a ida nem aconteceu: a
    consulta nao abre, e se a reserva tinha link do PDF o corrigir_origem ainda
    reescreve para NAT um link que estava certo. O painel acerta porque
    painel.carregar() ja escolhe a linha do primeiro trecho futuro; aqui a
    linha em maos e a do trecho alterado, entao a origem vem daqui.
    """
    return {l["localizador"]: l["origem"] for l in con.execute("""
        SELECT localizador, origem, MIN(embarque)
        FROM voos
        WHERE localizador IS NOT NULL AND embarque >= datetime('now')
        GROUP BY localizador
    """)}


def enriquecer_com_link(item, cia, origem, passageiros, do_pdf, voo_id=None):
    """Acrescenta cia, nome do passageiro e os dois links prontos ao item:
    o da reserva na companhia e o da mesma reserva no nosso painel.

    O link da companhia usa a mesma logica do painel (PDF > montado por cia):
    se a cia nao tem conector (TAP, Copa...) ou falta sobrenome, fica sem link
    mesmo - o Telegram e o painel so mostram o que da para montar de verdade.
    O do painel so sai se PAINEL_WEB_URL estiver configurado.

    `origem` tem de ser a do primeiro trecho ainda nao voado da reserva, nao a
    do trecho que mudou (ver origens_de_partida).
    """
    voo = {"cia": cia, "localizador": item["localizador"], "origem": origem,
           "sobrenome": qualidade.sobrenome(passageiros),
           "sobrenome_completo": qualidade.sobrenome_completo(passageiros)}
    link, fonte_link = painel.link_para(voo, do_pdf)
    item["cia"] = cia
    item["passageiro"] = qualidade.primeiro_passageiro(passageiros)
    item["link"] = link
    item["fonte_link"] = fonte_link
    item["link_painel"] = alertas.link_painel(config.painel_web_url, voo_id)
    return item


def alertas_pendentes(con, do_pdf=None):
    """O que ainda nao foi notificado. Nunca repete alerta ja enviado.

    Junta num alerta so o mesmo achado visto por fontes diferentes. As fontes
    sao complementares de proposito - a malha olha por numero de voo + data e
    os conectores olham por reserva - entao o mesmo voo alterado aparece nas
    duas. Em 30/07/2026 o `AD 2660` da TSTAAX gerou dois registros identicos
    (malha e portal-azul) e iria para o Telegram duas vezes.

    Duas fontes concordando nao e ruido, e confirmacao: em vez de esconder a
    segunda, a mensagem passa a dizer quem confirmou. O que nao pode e o
    operador receber a mesma coisa duas vezes e achar que sao dois problemas.
    """
    linhas = con.execute("""
        SELECT h.id, h.voo_id, h.campo, h.valor_novo, h.origem, h.detectado_em,
               v.localizador, v.cia, v.numero_voo, v.origem AS de, v.destino AS para,
               v.embarque, v.cliente, v.passageiros
        FROM historico h
        JOIN voos v ON v.id = h.voo_id
        WHERE h.notificado = 0
          AND h.evento = 'alterado'
          AND h.origem <> 'milhasflow'
        ORDER BY h.detectado_em
    """).fetchall()

    do_pdf = painel.links_dos_pdfs() if do_pdf is None else do_pdf
    origens = origens_de_partida(con)

    pendentes = []
    por_achado = {}
    for l in linhas:
        # mesmo voo + mesmo campo + mesmo valor = mesmo achado, venha de onde vier
        chave = (l["voo_id"], l["campo"], l["valor_novo"])
        ja_visto = por_achado.get(chave)
        if ja_visto is not None:
            # TODOS os ids entram: se so o representante for marcado como
            # notificado, o duplicado fica pendente e volta na proxima rodada
            ja_visto["historico_ids"].append(l["id"])
            if l["origem"] not in ja_visto["fontes"]:
                ja_visto["fontes"].append(l["origem"])
            continue

        item = {
            "historico_ids": [l["id"]],
            "fontes": [l["origem"]],
            "localizador": l["localizador"],
            "tipo": l["campo"] or "alteracao",
            "detalhe": "%s %s→%s · %s · %s" % (
                l["numero_voo"] or "?", l["de"] or "?", l["para"] or "?",
                fusos.texto_local(l["embarque"], l["de"]) or "?",
                l["valor_novo"] or ""),
            "cliente": l["cliente"],
        }
        enriquecer_com_link(item, l["cia"],
                            origens.get(l["localizador"]) or l["de"],
                            l["passageiros"], do_pdf, voo_id=l["voo_id"])
        por_achado[chave] = item
        pendentes.append(item)

    for item in pendentes:
        if len(item["fontes"]) > 1:
            item["detalhe"] += " · confirmado por %s" % " e ".join(
                NOME_DA_FONTE.get(f, f) for f in item["fontes"])
    return pendentes


def criticos_do_dia(con, horas=24, do_pdf=None):
    """Criticos ja avisados nas ultimas horas, para recapitular a noite.

    O sistema nao repete alerta - vira ruido e a equipe aprende a ignorar. A
    excecao sao os criticos: se um voo caiu de manha, tem que estar na frente
    do usuario de novo a noite, ate ser resolvido.
    """
    marcadores = ",".join("?" * len(TIPOS_CRITICOS))
    linhas = con.execute("""
        SELECT h.voo_id, h.campo, h.valor_novo, v.localizador, v.numero_voo, v.cia,
               v.origem AS de, v.destino AS para, v.embarque, v.cliente,
               v.passageiros
        FROM historico h JOIN voos v ON v.id = h.voo_id
        WHERE h.notificado = 1 AND h.evento = 'alterado'
          AND h.campo IN (%s)
          AND h.detectado_em >= datetime('now', 'localtime', ?)
        ORDER BY h.detectado_em
    """ % marcadores, tuple(TIPOS_CRITICOS) + ("-%d hours" % horas,)).fetchall()

    do_pdf = painel.links_dos_pdfs() if do_pdf is None else do_pdf
    origens = origens_de_partida(con)
    itens = []
    for l in linhas:
        item = {"localizador": l["localizador"], "tipo": l["campo"],
                "detalhe": "%s %s→%s · %s" % (
                    l["numero_voo"] or "?", l["de"] or "?", l["para"] or "?",
                    fusos.texto_local(l["embarque"], l["de"]) or "?"),
                "cliente": l["cliente"]}
        enriquecer_com_link(item, l["cia"],
                            origens.get(l["localizador"]) or l["de"],
                            l["passageiros"], do_pdf, voo_id=l["voo_id"])
        itens.append(item)
    return itens


def marcar_notificados(con, ids):
    if not ids:
        return
    con.executemany("UPDATE historico SET notificado=1 WHERE id=?",
                    [(i,) for i in ids])
    con.commit()


# Acima disso a rodada avisa que o sistema ficou cego no intervalo. As rodadas
# sao 7h e 19h, entao 12h e o normal; 30h ja significa que pelo menos uma
# rodada nao aconteceu - Mac desligado, cron quebrado, erro nao capturado.
HORAS_SEM_RODAR = 30


def registrar_divergencias(con):
    """Fontes que discordam viram alerta explicito, com os dois valores.

    Malha e conectores sao complementares: a malha olha por numero de voo +
    data, o conector olha a reserva do cliente. Quando as duas concordam, o
    alerta sai unificado (ver alertas_pendentes). Quando DISCORDAM, nenhuma das
    duas pode ser tratada como verdade em silencio - quem decide e o operador,
    e para isso ele precisa ver os dois numeros.

    Nao repete: so registra divergencia que ainda nao esta pendente para o
    mesmo voo e campo.
    """
    achados = db.divergencias(con)
    novos = 0
    for achado in achados:
        detalhe = " · ".join(
            "%s %s" % (NOME_DA_FONTE.get(origem, origem), valor)
            for origem, valor in sorted(achado["valores"].items()))
        detalhe = "%s — confira" % detalhe

        ja = con.execute(
            "SELECT 1 FROM historico WHERE voo_id=? AND campo=? AND evento='alterado'"
            " AND notificado=0 AND valor_novo=?",
            (achado["voo_id"], "fontes_divergem", detalhe)).fetchone()
        if ja:
            continue
        db._registrar(con, achado["voo_id"], "alterado", "cruzamento",
                      "fontes_divergem", None, detalhe)
        novos += 1
    if novos:
        con.commit()
    return novos


def avisar_etapa_falhou(cia, detalhe):
    """Portal que quebrou nao pode passar como 'nada mudou'.

    Ate 30/07/2026 o retorno de rodar() era descartado aqui: a checagem da
    LATAM morreu com PermissionError na pasta do iCloud e a rodada seguiu
    mandando o resumo normal, como se as 16 reservas tivessem sido conferidas.
    Ausencia de alerta e indistinguivel de "esta tudo bem" - e essa e a
    confusao que o sistema inteiro existe para evitar.
    """
    aviso = ("⚠️ <b>Checagem da %s não rodou</b>\n\n"
             "As reservas dessa companhia <b>não</b> foram verificadas. Isso "
             "não quer dizer que está tudo certo — quer dizer que o sistema "
             "não conseguiu olhar.\n\n<pre>%s</pre>\n"
             "Confira à mão:  <code>python3 src/painel.py --abrir</code>"
             % (html.escape(cia), html.escape("\n".join(detalhe or [])[:400])))
    alertas.enviar_telegram(config.telegram_token, config.telegram_chat, aviso)


def checar_portais(con):
    """Roda os conectores vencidos de checagem. Devolve a conexao (reaberta).

    A conexao vai e volta porque cada conector abre o banco no proprio
    processo - manter a nossa aberta durante a checagem daria lock no SQLite.

    Uma companhia que falha NAO aborta a rodada: portal fora do ar deixa a
    checagem parcial, e as outras companhias e os alertas ja apurados
    continuam valendo. So o sync aborta, porque sem ele nao ha o que comparar.
    """
    for cia, script, argumentos in CONECTORES:
        precisa, motivo = precisa_checar_portal(con, cia)
        if not precisa:
            print("\n>>> %s: %s, pulando." % (cia, motivo))
            continue

        con.close()
        ok, detalhe, codigo = rodar(
            [os.path.join(RAIZ, ".venv/bin/python"), script] + argumentos,
            "Checando %s (%s)" % (cia, motivo))
        con = db.conectar(config.caminho_banco)

        if not ok and codigo in SAIDA_NAO_E_FALHA:
            print("    (%s: parada prevista, sem alerta)" % cia)
        elif not ok:
            print("    FALHOU -> avisando no Telegram")
            avisar_etapa_falhou(cia, detalhe)
    return con


def horas_desde_a_ultima(con):
    """Quantas horas desde a ultima rodada bem-sucedida. None se e a primeira.

    Existe porque ausencia de mensagem e indistinguivel de "nada mudou". Sem
    isso, o sistema pode ficar dias parado e o usuario conclui que esta tudo
    em ordem justamente porque nao recebeu nada.
    """
    ultima = con.execute(
        "SELECT MAX(executado_em) FROM execucoes WHERE erro IS NULL").fetchone()[0]
    if not ultima:
        return None
    try:
        return (datetime.now() - datetime.fromisoformat(ultima)).total_seconds() / 3600
    except ValueError:
        return None


def estatisticas(con):
    total = con.execute("SELECT COUNT(*) FROM voos WHERE ativo=1").fetchone()[0]
    futuros = criticos = 0
    for l in con.execute("SELECT embarque FROM voos WHERE ativo=1"):
        h = fusos.horas_ate(l["embarque"])
        if h is not None and h >= 0:
            futuros += 1
            if h <= 48:
                criticos += 1
    return [("voos ativos", total), ("voos futuros", futuros),
            ("embarque em ate 48h", criticos)]


def linha_pendencias_manuais(voos_painel):
    """Aviso no resumo diario: nada te empurrava a abrir o painel antes disso.

    Uma reserva barrada pelo reCAPTCHA em toda tentativa fica no painel manual
    sem gerar alerta nenhum - so aparece se o operador lembrar de abrir o
    conferencia.html. Essa linha existe para que o resumo diario (que ja vai
    por Telegram de qualquer jeito) cutuque.
    """
    if not voos_painel:
        return "✅ Nada pendente de conferência manual."
    mais_proxima = voos_painel[0]        # ja vem ordenado por prioridade/embarque
    horas = fusos.horas_ate(mais_proxima.get("embarque_utc"))
    if horas is None:
        prazo = "sem data de embarque"
    elif horas < 24:
        prazo = "embarca em %.0fh" % max(horas, 0)
    else:
        prazo = "embarca em %.0f dia(s)" % (horas / 24)
    return ("🕘 <b>%d reserva(s)</b> aguardando conferência manual — mais próxima: "
            "%s (%s), %s.\n<code>python3 src/painel.py --abrir</code>" % (
                len(voos_painel), mais_proxima["localizador"], mais_proxima["cia"], prazo))


def cumprir_agenda(quer_resumo, quer_recap):
    """Marca que o horario de hoje foi cumprido - ainda que o Telegram falhe.

    O vigia existe para recuperar horario perdido com o Mac DESLIGADO, nao para
    reentregar mensagem. Amarrar a marcacao ao sucesso do Telegram fazia ele
    relancar a rodada INTEIRA (sync, Chrome, tres portais) a cada 30 min ate a
    meia-noite quando o token estava errado ou a rodada tinha sido segurada
    pelo teto - martelando os portais, que e o que o limitador existe para
    evitar. Alerta que nao saiu ja volta sozinho na proxima rodada, porque
    continua com notificado = 0.
    """
    if quer_resumo:
        agenda.marcar(agenda.RESUMO)
    if quer_recap:
        agenda.marcar(agenda.RECAP)


def rodar(comando, descricao):
    """Executa uma etapa. Devolve (ok, ultimas linhas da saida, codigo).

    O codigo de saida vem junto porque nem todo retorno diferente de zero e
    falha: checar_azul.py sai com 2 quando a Azul esta em quarentena, e isso e
    o sistema se protegendo, nao erro (ver SAIDA_NAO_E_FALHA).
    """
    print("\n>>> %s" % descricao)
    try:
        r = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True,
                           timeout=45 * 60)
    except subprocess.TimeoutExpired:
        print("    TRAVOU (mais de 45 min)")
        # lista, nao string: quem consome faz "\n".join(...), e com string isso
        # separaria caractere por caractere
        return False, ["etapa travou (timeout de 45 min)"], None
    saida = (r.stdout or "") + (r.stderr or "")
    for linha in saida.strip().splitlines()[-14:]:
        print("    " + linha)
    return r.returncode == 0, saida.strip().splitlines()[-3:], r.returncode


def main():
    sem_portal = "--sem-portal" in sys.argv
    quer_resumo = "--resumo" in sys.argv
    quer_recap = "--recapitular" in sys.argv

    print("=" * 62)
    print("  RODADA — %s" % datetime.now().strftime("%d/%m/%Y %H:%M"))
    print("=" * 62)

    # Uma rodada de cada vez. O vigia acorda a cada 30 min e a rodada da manha
    # demora mais que isso: sem esta trava ele sobe uma segunda por cima da que
    # o launchd comecou, e as duas mandam o mesmo alerta (ver agenda.travar).
    if not agenda.travar("rodada"):
        print("\n>>> Ja tem uma rodada em andamento. Saindo sem fazer nada.")
        return

    # Sem sincronizar nao ha o que comparar. Seguir daqui produziria um
    # "0 alteracoes" que o usuario leria como "esta tudo bem", quando na
    # verdade e "nao consegui olhar". Falhar em silencio e o pior resultado.
    ok, detalhe, _ = rodar([sys.executable, "src/sync.py"], "Sincronizando MilhasFlow")
    if not ok:
        aviso = ("🚨 <b>Checagem NÃO rodou</b>\n\nA sincronização com o MilhasFlow "
                 "falhou, então nada foi verificado.\n\n<pre>%s</pre>\n"
                 "Isso <b>não</b> significa que está tudo certo — significa que "
                 "o sistema está cego." % html.escape("\n".join(detalhe or [])[:400]))
        alertas.enviar_telegram(config.telegram_token, config.telegram_chat, aviso)
        print("\n!!! sync falhou - rodada abortada e alerta enviado")
        sys.exit(1)

    # atualiza o indice de links dos PDFs (local, barato). O painel so e gerado
    # depois das checagens: aqui ele ainda nao saberia o que vai para a aba
    # Urgente, e o arquivo seria reescrito de qualquer jeito la embaixo.
    rodar([sys.executable, "src/indexar_links.py"], "Indexando links dos PDFs")

    con = db.conectar(config.caminho_banco)

    lacuna = horas_desde_a_ultima(con)
    if lacuna is not None and lacuna > HORAS_SEM_RODAR:
        print("\n>>> ATENCAO: %.0fh desde a ultima rodada" % lacuna)
        alertas.enviar_telegram(
            config.telegram_token, config.telegram_chat,
            "⏰ <b>O sistema ficou %.0f horas sem rodar</b>\n\n"
            "Nesse intervalo nenhuma reserva foi verificada. Se o Mac ficou "
            "desligado, é só isso. Se não, vale conferir o agendamento."
            % lacuna)

    if not sem_portal:
        con = checar_portais(con)

    # Malha (AeroDataBox) entra na mesma rodada da manhã, em vez de um
    # LaunchAgent separado às 8h — assim a checagem inteira (portais + malha)
    # acontece uma vez só por dia, no mesmo horário, e não em dois disparos
    # (ver decisão com o proprietário: economiza consulta e simplifica o agendamento).
    # checar_malha.py cuida do próprio orçamento/rotação; não precisa do
    # gate de cadência que os portais usam.
    con.close()
    ok_malha, detalhe_malha, _ = rodar(
        [os.path.join(RAIZ, ".venv/bin/python"), "src/checar_malha.py"],
        "Checando a malha (AeroDataBox)")
    if not ok_malha:
        print("    FALHOU -> avisando no Telegram")
        avisar_etapa_falhou("Malha", detalhe_malha)
    con = db.conectar(config.caminho_banco)

    # Depois das checagens: as fontes acabaram de registrar o que viram, entao
    # e agora que da para cruzar.
    divergentes = registrar_divergencias(con)
    if divergentes:
        print("\n>>> Fontes divergentes: %d voo(s)" % divergentes)

    # o indice de links ja foi regerado no inicio da rodada; ler uma vez so
    do_pdf = painel.links_dos_pdfs()

    pendentes = alertas_pendentes(con, do_pdf)
    print("\n>>> Alertas novos: %d" % len(pendentes))

    # Enxurrada de alerta e sintoma de bug, nao de 40 voos cancelados no mesmo
    # dia. Em 29/07/2026 uma comparacao errada gerou 68 alertas falsos de uma
    # vez. Acima do teto o sistema segura, avisa que segurou, e espera revisao.
    if len(pendentes) > TETO_DE_ALERTAS:
        print("    SEGURANDO: %d alertas numa rodada so passa do teto de %d."
              % (len(pendentes), TETO_DE_ALERTAS))
        print("    Isso quase sempre e bug de comparacao, nao voo cancelado.")
        print("    Revise com:  sqlite3 voos.db 'SELECT * FROM historico WHERE notificado=0'")
        aviso = ("⚠️ <b>Rodada segurada</b>\n\n%d alertas de uma vez — acima do teto "
                 "de %d.\nNada foi disparado; isso costuma ser erro de comparação.\n"
                 "Confira antes de liberar." % (len(pendentes), TETO_DE_ALERTAS))
        alertas.enviar_telegram(config.telegram_token, config.telegram_chat, aviso)
        con.close()
        # o horario do dia rodou - o que falta e revisao humana, nao repeticao.
        # Sem isto o vigia relanca a rodada inteira de meia em meia hora, e ela
        # bate no mesmo teto toda vez.
        cumprir_agenda(quer_resumo, quer_recap)
        print("\n" + "=" * 62)
        return

    if pendentes:
        texto = alertas.montar_mensagem(
            pendentes, "⚠️ Voos com alteração — %s" % datetime.now().strftime("%d/%m %H:%M"))
        ok, erro = alertas.enviar_telegram(config.telegram_token,
                                           config.telegram_chat, texto)
        if ok:
            marcar_notificados(
                con, [i for p in pendentes for i in p["historico_ids"]])
            print("    Telegram enviado; %d marcados como avisados." % len(pendentes))
        else:
            # nao marca como notificado: tenta de novo na proxima rodada
            print("    Telegram NAO enviado (%s). Serao reenviados." % erro)
        for p in pendentes[:10]:
            print("    [%s] %s — %s" % (p["tipo"], p["localizador"], p["detalhe"][:60]))

    # Gera o painel ja com a aba Urgente refletindo os alertas desta rodada. Se
    # nao ha pendente novo, a aba fica vazia - o que ja foi avisado nao volta
    # aqui, mesmo que o operador nao tenha clicado ainda.
    voos_painel = painel.carregar()
    painel.gerar(voos_painel, os.path.join(config.pasta_dados, "conferencia.html"),
                 do_pdf, urgentes=pendentes)
    print("\n>>> Painel atualizado: %d urgente(s), %d para conferencia manual"
          % (len(pendentes), len(voos_painel)))

    if quer_recap:
        pendencias = criticos_do_dia(con, do_pdf=do_pdf)
        if pendencias:
            texto = alertas.montar_mensagem(
                pendencias, "🔁 Recapitulando os críticos de hoje")
            ok, erro = alertas.enviar_telegram(config.telegram_token,
                                               config.telegram_chat, texto)
            print("\n>>> Recap de criticos: %d (%s)"
                  % (len(pendencias), "enviado" if ok else erro))
        else:
            print("\n>>> Recap: nenhum critico hoje.")

    if quer_resumo:
        stats = estatisticas(con)
        corpo = "\n".join("  %-24s %s" % (r, v) for r, v in stats)
        texto = "<b>Resumo diário — %s</b>\n\n<pre>%s</pre>\n%s\n%s" % (
            datetime.now().strftime("%d/%m"), corpo,
            "Nenhuma alteração." if not pendentes else "%d alteração(oes) acima." % len(pendentes),
            linha_pendencias_manuais(voos_painel))
        ok, erro = alertas.enviar_telegram(config.telegram_token,
                                           config.telegram_chat, texto)
        print("\n>>> Resumo diario: %s" % ("enviado" if ok else "falhou (%s)" % erro))

    cumprir_agenda(quer_resumo, quer_recap)

    resumo_faxina = manutencao.executar(config.pasta_dados, RAIZ, con)
    if resumo_faxina:
        print("\n>>> Faxina: %s" % resumo_faxina)

    # Espelha o resultado desta rodada pro painel web. So o bot fala com a
    # malha/portais - isto so copia; falha aqui nunca derruba a rodada, o
    # monitoramento em si nao depende do site (ver sincronizar_web.py).
    resultado_web = sincronizar_web.sincronizar_se_configurado(con, config)
    if resultado_web is not None:
        ok_web, msg_web = resultado_web
        print("\n>>> Painel web: %s" % (msg_web if ok_web else "FALHOU (%s)" % msg_web))

    con.close()
    print("\n" + "=" * 62)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:
        # Rodada que morre calada e indistinguivel de rodada que nao achou
        # nada. Melhor avisar que quebrou do que deixar o usuario supondo.
        import traceback
        traceback.print_exc()
        alertas.enviar_telegram(
            config.telegram_token, config.telegram_chat,
            "🚨 <b>A checagem quebrou</b>\n\n<pre>%s</pre>\n"
            "Nada foi verificado nesta rodada."
            % html.escape(str(erro)[:300]))
        sys.exit(1)
