"""Faxina automatica: log, CSV diario, backups e historico antigo.

Roda no fim de cada rodada. Sem isso o projeto acumula um arquivo por dia para
sempre - hoje sao KB, em um ano vira lixo que esconde o que importa.

Nada aqui apaga dado vivo: o banco `voos.db` e o `voos_atual.csv` nunca sao
tocados, e o historico so perde registros ja notificados e antigos.
"""

import os
import time

# quanto tempo cada coisa fica
DIAS_CSV = 45          # fotos diarias: suficiente para auditar uma temporada
DIAS_BACKUP = 7        # backups do banco
DIAS_HISTORICO = 365   # eventos ja notificados
LOG_MAXIMO = 2 * 1024 * 1024   # 2 MB por arquivo de log

# nunca apagar, mesmo que casem com os padroes
PROTEGIDOS = ("voos_atual.csv", "conferencia.html",
              "links_reservas.csv", "links_reservas.json")


def _antigos(pasta, padrao_inicio, dias, agora):
    if not os.path.isdir(pasta):
        return []
    limite = agora - dias * 86400
    achados = []
    for nome in os.listdir(pasta):
        if nome in PROTEGIDOS or not nome.startswith(padrao_inicio):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            if os.path.isfile(caminho) and os.path.getmtime(caminho) < limite:
                achados.append(caminho)
        except OSError:
            pass
    return achados


def limpar_arquivos(pasta_dados, raiz):
    """Remove CSVs e backups vencidos. Devolve (removidos, bytes liberados)."""
    agora = time.time()
    alvos = []
    for inicio, dias in (("voos_", DIAS_CSV), ("pendencias_", DIAS_CSV),
                         ("sem_pdf_", DIAS_CSV)):
        alvos += _antigos(pasta_dados, inicio, dias, agora)
    alvos += _antigos(raiz, "voos.db.backup", DIAS_BACKUP, agora)

    removidos = liberados = 0
    for caminho in alvos:
        try:
            liberados += os.path.getsize(caminho)
            os.remove(caminho)
            removidos += 1
        except OSError:
            pass
    return removidos, liberados


def rotacionar_logs(pasta_dados):
    """Log grande vira .1 e recomeca. Mantem so uma geracao anterior."""
    if not os.path.isdir(pasta_dados):
        return []
    rotacionados = []
    for nome in os.listdir(pasta_dados):
        if not nome.endswith(".log"):
            continue
        caminho = os.path.join(pasta_dados, nome)
        try:
            if os.path.getsize(caminho) <= LOG_MAXIMO:
                continue
            anterior = caminho + ".1"
            if os.path.exists(anterior):
                os.remove(anterior)
            os.rename(caminho, anterior)
            rotacionados.append(nome)
        except OSError:
            pass
    return rotacionados


def podar_historico(con):
    """Apaga eventos ja notificados e velhos. Devolve quantos saíram.

    Preserva o que nunca foi avisado, aconteca o que acontecer: alerta pendente
    nao pode sumir na faxina.
    """
    cur = con.execute(
        "DELETE FROM historico WHERE notificado = 1"
        " AND detectado_em < datetime('now', 'localtime', ?)",
        ("-%d days" % DIAS_HISTORICO,))
    con.commit()
    return cur.rowcount or 0


def executar(pasta_dados, raiz, con=None):
    """Faxina completa. Devolve um resumo em texto, ou None se nada mudou."""
    removidos, liberados = limpar_arquivos(pasta_dados, raiz)
    logs = rotacionar_logs(pasta_dados)
    podados = podar_historico(con) if con is not None else 0

    partes = []
    if removidos:
        partes.append("%d arquivo(s), %.1f MB" % (removidos, liberados / 1048576.0))
    if logs:
        partes.append("%d log(s) rotacionado(s)" % len(logs))
    if podados:
        partes.append("%d evento(s) antigos do historico" % podados)
    return "; ".join(partes) if partes else None
