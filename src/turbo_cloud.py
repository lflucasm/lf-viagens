"""Espelho da gestao do Turbo (Clube LATAM Pass + Turbo, Livelo -> LATAM) no painel.

Tudo vem da Volly, so leitura: conta LATAM (clube, saldo, CPFs usados/limite),
conta Livelo do mesmo titular (saldo, CPM) e as transferencias Livelo -> LATAM
dos ultimos 12 meses. A tela /turbo monta o ciclo mensal a partir dessas
transferencias - ninguem precisa marcar "transferido" a mao.

Liberacao de CPF (LATAM: limite de beneficiarios em 12 meses moveis): cada
passageiro emitido pela conta volta a contar 12 meses depois da emissao. So
enxerga emissoes lancadas na Volly (desde ~07/2026), entao o CPFs usados oficial
continua sendo o cpf_used que a equipe mantem na Volly.
"""

import datetime
import unicodedata

import supabase_rest

LIMITE_CPF_PADRAO = 25  # Volly usa 25 nas contas que tem limite preenchido


def _nome(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _passageiros(passengers_data):
    """passengers_data: lista [{name}] (antigo) ou {"flightGroups": [[...]]} (CRM)."""
    if isinstance(passengers_data, dict):
        return [p for g in passengers_data.get("flightGroups") or [] if isinstance(g, list) for p in g]
    return passengers_data or []


def _mais_um_ano(iso):
    d = datetime.date.fromisoformat(iso[:10])
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 29/02
        return d.replace(year=d.year + 1, day=28)


def liberacoes(emissoes, hoje):
    """Emissoes de UMA conta -> [{data, qtd}] das liberacoes futuras, em ordem."""
    por_data = {}
    for e in emissoes:
        if e.get("refund_status"):
            continue
        qtd = len(_passageiros(e.get("passengers_data"))) or 1
        volta = _mais_um_ano(e["emission_date"])
        if volta > hoje:
            por_data[volta] = por_data.get(volta, 0) + qtd
    return [{"data": d.isoformat(), "qtd": q} for d, q in sorted(por_data.items())]


def montar(contas, transferencias, emissoes, hoje):
    """Linhas da tabela `turbo`: uma por conta LATAM com clube (atual ou passado)
    ou com transferencia Livelo -> LATAM no periodo."""
    por_id = {c["id"]: c for c in contas}
    livelo = [c for c in contas if c.get("program") == "Livelo"]

    def livelo_de(lat):
        cpf = lat.get("holder_cpf")
        for c in livelo:
            if cpf and c.get("holder_cpf") == cpf:
                return c
        nome = _nome(lat.get("name"))
        return next((c for c in livelo if _nome(c.get("name")) == nome), None)

    trans_por_conta = {}
    for t in transferencias:
        if t.get("is_draft"):
            continue
        origem = por_id.get(t.get("source_account_id")) or {}
        if origem.get("program") != "Livelo":
            continue
        trans_por_conta.setdefault(t.get("destination_account_id"), []).append({
            "data": t["transfer_date"][:10],
            "pontos": t.get("source_total_points") or 0,
            "milhas": t.get("destination_miles") or 0,
            "bonus": t.get("bonus_percentage") or 0,
            "comprados": t.get("source_points_purchased") or 0,
            "valor_compra": float(t.get("source_purchase_amount") or 0),
            "cpm_livelo": t.get("source_cpm"),
            "cpm_latam": t.get("destination_cpm"),
        })

    emis_por_conta = {}
    for e in emissoes:
        emis_por_conta.setdefault(e.get("miles_account_id"), []).append(e)

    linhas = []
    for c in contas:
        if c.get("program") != "LATAM Pass":
            continue
        trans = sorted(trans_por_conta.get(c["id"], []), key=lambda t: t["data"], reverse=True)
        if not (c.get("club_active") or c.get("club_member_since") or trans):
            continue
        liv = livelo_de(c) or {}
        linhas.append({
            "conta_id": c["id"],
            "titular": (c.get("name") or "").strip(),
            "status": c.get("status"),
            "clube_ativo": bool(c.get("club_active")),
            "custo_mensal": c.get("club_monthly_cost"),
            "milhas_mes": c.get("club_points_monthly"),
            "dia_venc": c.get("club_due_day"),
            "saldo_latam": c.get("balance") or 0,
            "cpm_latam": c.get("cpm"),
            "livelo_conta_id": liv.get("id"),
            "saldo_livelo": liv.get("balance") or 0,
            "cpm_livelo": liv.get("cpm"),
            "livelo_clube_ativo": bool(liv.get("club_active")),
            "livelo_custo_mensal": liv.get("club_monthly_cost"),
            "livelo_pontos_mes": liv.get("club_points_monthly"),
            "cpf_usados": c.get("cpf_used") or 0,
            "cpf_limite": c.get("cpf_limit") or LIMITE_CPF_PADRAO,
            "liberacoes": liberacoes(emis_por_conta.get(c["id"], []), hoje),
            "transferencias": trans,
        })
    return linhas


PROGRAMAS_EMISSAO = ("LATAM Pass", "Smiles")


def montar_contas(contas, emissoes, hoje):
    """Linhas da tabela `contas_emissao`: toda conta LATAM Pass e Smiles, pra tela
    de sugestao de conta. Inclui as zeradas pra elas se atualizarem quando recebem saldo."""
    emis_por_conta = {}
    for e in emissoes:
        emis_por_conta.setdefault(e.get("miles_account_id"), []).append(e)
    linhas = []
    for c in contas:
        programa = c.get("program")
        if programa not in PROGRAMAS_EMISSAO:
            continue
        usados = c.get("cpf_used") or 0
        if programa == "Smiles":
            # Smiles conta por ano civil: tudo volta em 01/01 do ano seguinte.
            lib = [{"data": "%d-01-01" % (hoje.year + 1), "qtd": usados}] if usados else []
        else:
            lib = liberacoes(emis_por_conta.get(c["id"], []), hoje)
        linhas.append({
            "conta_id": c["id"],
            "titular": (c.get("name") or "").strip(),
            "programa": programa,
            "saldo": c.get("balance") or 0,
            "cpm": c.get("cpm"),
            "clube_ativo": bool(c.get("club_active")),
            "cpf_usados": usados,
            "cpf_limite": c.get("cpf_limit") or LIMITE_CPF_PADRAO,
            "liberacoes": lib,
        })
    return linhas


def sincronizar(volly, supabase_url, service_key, plano=False, hoje=None):
    """Le a Volly e regrava a tabela `turbo`. Devolve contagens."""
    hoje = hoje or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).date()
    inicio = (hoje - datetime.timedelta(days=366)).isoformat()
    contas = volly.milhas_contas()
    transferencias = volly.milhas_transferencias(inicio)
    emissoes = volly.emissoes_passageiros(inicio)
    linhas = montar(contas, transferencias, emissoes, hoje)
    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for l in linhas:
        l["atualizado_em"] = agora
    contas_emissao = montar_contas(contas, emissoes, hoje)
    for l in contas_emissao:
        l["atualizado_em"] = agora
    if not plano and linhas:
        supabase_rest.upsert(supabase_url, service_key, "turbo", linhas, "conta_id")
    if not plano and contas_emissao:
        supabase_rest.upsert(supabase_url, service_key, "contas_emissao", contas_emissao, "conta_id")
    return {"titulares": len(linhas), "com_clube": sum(l["clube_ativo"] for l in linhas),
            "contas_emissao": len(contas_emissao)}
