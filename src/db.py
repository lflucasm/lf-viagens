"""Banco local (SQLite): estado atual dos voos + historico de mudancas.

O CSV mostra a foto de hoje. O banco guarda a foto de ontem, e e a comparacao
entre as duas que gera alerta. Sem historico nao existe checagem.
"""

import sqlite3
from datetime import datetime, timedelta

# Campos cuja alteracao interessa. Mudou algum -> vira evento no historico.
CAMPOS_MONITORADOS = (
    "localizador", "cia", "numero_voo", "origem", "destino",
    "embarque", "chegada", "classe", "status",
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS voos (
    id              TEXT PRIMARY KEY,
    emissao_id      TEXT,
    localizador     TEXT,
    cia             TEXT,
    numero_voo      TEXT,
    origem          TEXT,
    destino         TEXT,
    embarque        TEXT,
    chegada         TEXT,
    classe          TEXT,
    sentido         TEXT,
    status          TEXT,
    cliente         TEXT,
    passageiros     TEXT,
    tags            TEXT,
    balcao          INTEGER NOT NULL DEFAULT 0,
    valor_venda     REAL,
    ativo           INTEGER NOT NULL DEFAULT 1,
    visto_em        TEXT,
    criado_em       TEXT
);

CREATE TABLE IF NOT EXISTS historico (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    voo_id        TEXT NOT NULL,
    evento        TEXT NOT NULL,     -- novo | alterado | sumiu | reapareceu
    campo         TEXT,
    valor_antigo  TEXT,
    valor_novo    TEXT,
    origem        TEXT NOT NULL,     -- milhasflow | portal | email
    detectado_em  TEXT NOT NULL,
    notificado    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS execucoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    executado_em  TEXT NOT NULL,
    voos_lidos    INTEGER,
    novos         INTEGER,
    alterados     INTEGER,
    sumiram       INTEGER,
    erro          TEXT
);

-- Quando cada voo foi conferido na malha da companhia. E o que permite a
-- rotacao: a cota nao paga conferir todo voo todo dia, entao a rodada gasta o
-- orcamento nos mais atrasados (ver malha.priorizar).
CREATE TABLE IF NOT EXISTS malha_checagens (
    chave         TEXT PRIMARY KEY,   -- "numero_voo|AAAA-MM-DD"
    ultima        TEXT NOT NULL,      -- data da ultima consulta
    vezes         INTEGER NOT NULL DEFAULT 1
);

-- Ultimo saldo de cota informado pela API de malha. E ele que permite o
-- orcamento do dia sair do NUMERO DO FORNECEDOR em vez de uma constante: o
-- saldo real ja desconta o que foi gasto a mao, em teste, ou por outra maquina.
CREATE TABLE IF NOT EXISTS malha_cota (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    restantes     INTEGER,
    limite        INTEGER,
    reset_em      TEXT,               -- quando a cota renova (ISO)
    visto_em      TEXT NOT NULL
);

-- O que cada fonte viu por ultimo em cada voo. Uma linha por voo+fonte
-- (UPSERT), nao historico: interessa a leitura ATUAL de cada uma, para saber
-- quando duas discordam. Tamanho fica fixo - 48 voos x 3 fontes = ~144 linhas.
--
-- Existe porque conector so gravava quando DISCORDAVA do CRM. Quando ele
-- concorda e a malha diverge, o alerta da malha ia sozinho e nada sinalizava a
-- contradicao: foi o caso do AD 4626 em 30/07/2026, malha 20:20 x Azul 20:40.
CREATE TABLE IF NOT EXISTS observacoes (
    voo_id    TEXT NOT NULL,
    origem    TEXT NOT NULL,      -- portal-latam | portal-gol | portal-azul | malha
    partida   TEXT,               -- "AAAA-MM-DD HH:MM", hora LOCAL do aeroporto
    rota      TEXT,               -- "REC-GRU"
    situacao  TEXT,               -- confirmado | cancelado | ...
    visto_em  TEXT NOT NULL,
    PRIMARY KEY (voo_id, origem)
);

CREATE INDEX IF NOT EXISTS ix_hist_voo  ON historico(voo_id);
CREATE INDEX IF NOT EXISTS ix_hist_data ON historico(detectado_em);
CREATE INDEX IF NOT EXISTS ix_voos_emb  ON voos(embarque);
"""


def conectar(caminho):
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    _migrar(con)
    return con


def _migrar(con):
    """Colunas novas em banco que ja existia."""
    existentes = {l["name"] for l in con.execute("PRAGMA table_info(voos)")}
    for coluna, tipo in (("tags", "TEXT"), ("balcao", "INTEGER NOT NULL DEFAULT 0")):
        if coluna not in existentes:
            con.execute("ALTER TABLE voos ADD COLUMN %s %s" % (coluna, tipo))
    con.commit()


def _registrar(con, voo_id, evento, origem, campo=None, antigo=None, novo=None):
    con.execute(
        "INSERT INTO historico (voo_id, evento, campo, valor_antigo, valor_novo,"
        " origem, detectado_em) VALUES (?,?,?,?,?,?,?)",
        (voo_id, evento, campo,
         None if antigo is None else str(antigo),
         None if novo is None else str(novo),
         origem, datetime.now().isoformat(timespec="seconds")),
    )


def sincronizar(con, voos, origem="milhasflow", ignorados=None):
    """Grava a leitura de hoje e devolve as mudancas em relacao a ultima.

    `ignorados`: localizadores que saíram do monitoramento de proposito. Eles
    ficam inativos sem virar evento "sumiu" - reserva que a agencia decidiu
    nao acompanhar nao e o mesmo que reserva que desapareceu do CRM.

    Retorna (novos, alterados, sumiram) - cada um uma lista de dicts.
    """
    ignorados = {c.upper() for c in (ignorados or set())}
    agora = datetime.now().isoformat(timespec="seconds")
    anteriores = {l["id"]: dict(l) for l in con.execute("SELECT * FROM voos")}

    novos, alterados, sumiram = [], [], []

    for voo in voos:
        antigo = anteriores.get(voo["id"])

        if antigo is None:
            colunas = list(voo.keys())
            con.execute(
                "INSERT INTO voos (%s, ativo, visto_em, criado_em) VALUES (%s,1,?,?)"
                % (",".join(colunas), ",".join("?" * len(colunas))),
                [voo[c] for c in colunas] + [agora, agora],
            )
            _registrar(con, voo["id"], "novo", origem)
            novos.append(voo)
            continue

        mudancas = []
        for campo in CAMPOS_MONITORADOS:
            de, para = antigo.get(campo), voo.get(campo)
            if (de or None) != (para or None):
                mudancas.append((campo, de, para))
                _registrar(con, voo["id"], "alterado", origem, campo, de, para)

        if not antigo.get("ativo"):
            _registrar(con, voo["id"], "reapareceu", origem)

        colunas = list(voo.keys())
        con.execute(
            "UPDATE voos SET %s, ativo=1, visto_em=? WHERE id=?"
            % ",".join(c + "=?" for c in colunas),
            [voo[c] for c in colunas] + [agora, voo["id"]],
        )

        if mudancas:
            registro = dict(voo)
            registro["mudancas"] = mudancas
            alterados.append(registro)

    # presente ontem, ausente hoje: reserva apagada ou cancelada no CRM
    ids_hoje = set(v["id"] for v in voos)
    for voo_id, antigo in anteriores.items():
        if voo_id not in ids_hoje and antigo.get("ativo"):
            con.execute("UPDATE voos SET ativo=0, visto_em=? WHERE id=?", (agora, voo_id))
            if (antigo.get("localizador") or "").upper() in ignorados:
                continue     # saiu por escolha nossa, nao sumiu
            _registrar(con, voo_id, "sumiu", origem)
            sumiram.append(antigo)

    con.commit()
    return novos, alterados, sumiram


# ------------------------------------------- observacoes por fonte
# Campos que valem comparar entre fontes. `situacao` fica de fora: cada portal
# tem vocabulario proprio ("Confirmed", "Confirmada", "HK") e comparar texto
# cru acusaria divergencia em reserva intacta.
CAMPOS_COMPARAVEIS = ("partida", "rota")


def registrar_observacao(con, voo_id, origem, partida=None, rota=None,
                         situacao=None):
    """Anota o que ESTA fonte viu neste voo, mesmo que bata com o CRM.

    Gravar tambem quando esta tudo certo e o ponto: e a leitura que concorda
    com o CRM que permite dizer que a OUTRA fonte e que esta fora da linha.
    """
    con.execute(
        "INSERT INTO observacoes (voo_id, origem, partida, rota, situacao, visto_em)"
        " VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(voo_id, origem) DO UPDATE SET partida=excluded.partida,"
        " rota=excluded.rota, situacao=excluded.situacao,"
        " visto_em=excluded.visto_em",
        (voo_id, origem, partida, rota, situacao,
         datetime.now().isoformat(timespec="seconds")),
    )


def observacoes_por_fonte(con, origem):
    """{voo_id: {"partida", "rota", "situacao"}} - a ULTIMA leitura desta fonte,
    ANTES da rodada de hoje sobrescrever.

    E a baseline que comparacao.comparar() usa para horario_alterado e
    rota_alterada, no lugar do CRM (ver o motivo no docstring de comparar()).
    Por isso quem chama tem de buscar isto ANTES de registrar_observacao(s) -
    depois a leitura de hoje ja teria sobrescrito a de ontem.
    """
    return {l["voo_id"]: dict(l) for l in con.execute(
        "SELECT voo_id, partida, rota, situacao FROM observacoes WHERE origem=?",
        (origem,))}


def registrar_observacoes(con, origem, observacoes):
    """Grava de uma vez as leituras de uma reserva e confirma.

    Existe porque cada conector repetia o mesmo laco + commit: o que essa
    fonte viu so vale para o cruzamento se a leitura inteira for confiavel,
    entao quem chama decide isso ANTES e passa a lista pronta.
    """
    for voo_id, partida, rota, situacao in observacoes:
        registrar_observacao(con, voo_id, origem, partida, rota, situacao)
    con.commit()


def divergencias(con, horas=48):
    """Voos em que duas fontes recentes discordam.

    Devolve [{voo_id, campo, valores: {origem: valor}}].

    So entram observacoes das ultimas `horas`: leitura velha comparada com
    leitura nova acusaria divergencia onde houve, na verdade, uma mudanca que
    as duas fontes ja registraram em momentos diferentes.
    """
    corte = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
    por_voo = {}
    for linha in con.execute(
            "SELECT * FROM observacoes WHERE visto_em >= ? ORDER BY voo_id, origem",
            (corte,)):
        por_voo.setdefault(linha["voo_id"], []).append(dict(linha))

    achados = []
    for voo_id, observacoes in sorted(por_voo.items()):
        if len(observacoes) < 2:
            continue          # uma fonte sozinha nao diverge de ninguem
        for campo in CAMPOS_COMPARAVEIS:
            valores = {o["origem"]: o[campo] for o in observacoes if o.get(campo)}
            if len(set(valores.values())) > 1:
                achados.append({"voo_id": voo_id, "campo": campo,
                                "valores": valores})
    return achados


def registrar_execucao(con, lidos, novos, alterados, sumiram, erro=None):
    con.execute(
        "INSERT INTO execucoes (executado_em, voos_lidos, novos, alterados, sumiram, erro)"
        " VALUES (?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), lidos, novos, alterados, sumiram, erro),
    )
    con.commit()


def voos_ativos(con):
    return [dict(l) for l in con.execute(
        "SELECT * FROM voos WHERE ativo=1 ORDER BY embarque")]


# ------------------------------------------------- rotacao da malha
def _chave_malha(numero_voo, data):
    return "%s|%s" % (numero_voo, data)


def checagens_de_malha(con):
    """{(numero_voo, data): "AAAA-MM-DD"} com a ultima consulta de cada voo."""
    resultado = {}
    for linha in con.execute("SELECT chave, ultima FROM malha_checagens"):
        numero, _, data = linha["chave"].partition("|")
        resultado[(numero, data)] = linha["ultima"]
    return resultado


def marcar_checagem_malha(con, numero_voo, data, quando=None):
    """Anota que este voo foi conferido hoje, para a rotacao nao repeti-lo."""
    quando = quando or datetime.now().strftime("%Y-%m-%d")
    con.execute(
        "INSERT INTO malha_checagens (chave, ultima, vezes) VALUES (?,?,1)"
        " ON CONFLICT(chave) DO UPDATE SET ultima=excluded.ultima, vezes=vezes+1",
        (_chave_malha(numero_voo, data), quando),
    )


def unidades_malha_hoje(con, unidades_por_consulta=2, quando=None):
    """Quanto da cota ja foi gasto hoje nesta fonte.

    Existe para o orcamento valer POR DIA, e nao por invocacao: rodar o script
    tres vezes numa tarde nao pode gastar tres vezes o teto diario e esvaziar o
    mes. Um voo nao e reconsultado no mesmo dia (o intervalo minimo e 3 dias),
    entao contar linhas com `ultima` de hoje mede as consultas do dia.
    """
    quando = quando or datetime.now().strftime("%Y-%m-%d")
    linha = con.execute(
        "SELECT COUNT(*) AS n FROM malha_checagens WHERE ultima=?", (quando,)
    ).fetchone()
    return (linha["n"] if linha else 0) * unidades_por_consulta


def salvar_cota_malha(con, restantes, limite, reset_em=None):
    """Guarda o saldo que a API informou, para planejar a proxima rodada."""
    con.execute(
        "INSERT INTO malha_cota (id, restantes, limite, reset_em, visto_em)"
        " VALUES (1,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET restantes=excluded.restantes,"
        " limite=excluded.limite, reset_em=excluded.reset_em,"
        " visto_em=excluded.visto_em",
        (restantes, limite, reset_em, datetime.now().isoformat(timespec="seconds")),
    )


def cota_malha(con):
    """Ultimo saldo conhecido, ou None se a fonte nunca rodou."""
    linha = con.execute("SELECT * FROM malha_cota WHERE id=1").fetchone()
    return dict(linha) if linha else None
