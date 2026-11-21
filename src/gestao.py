"""KPIs de gestao da LF Viagens - calculo puro em Python sobre as listas
cruas que `volly.py` devolve. Sem rede, sem estado.

Substitui o que o MCP pago da Volly calculava no servidor (emissions_summary,
financial_dre, clients_segment, nfse_compliance_check, team_ranking...).

Os valores de enum ('income'/'expense', 'pago', status de NFS-e) foram
confirmados por amostragem em 2026-09-10. Onde ainda ha duvida, a constante
fica no topo pra ajuste rapido.
"""

import datetime as _dt
from collections import defaultdict

# --- enums observados (confirmados por amostragem 2026-09-10) ----------
TIPO_RECEITA = "income"
TIPO_DESPESA = "expense"
# nfse_emissoes.status real: AUTORIZADA / REJEITADA / CANCELADA / PROCESSANDO
NFSE_OK = ("autorizada", "authorized", "concluido", "concluida", "success")
# crm_followups.status real: completed / pending / dismissed
FOLLOWUP_FEITO = ("completed", "dismissed", "done", "concluido", "concluida",
                  "cancelado", "canceled", "cancelled")
TAREFA_FEITA = ("concluida", "done", "completed", "concluído")


# --- helpers ---------------------------------------------------------

def _d(s):
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _venda_real(e):
    """Emissao que conta pro resultado.

    `is_miles_purchase` NAO exclui: sao 87 emissoes reais de bilhete emitido
    com milhas compradas (confirmado 2026-09-10 - excluir derrubava o total
    de 284 pra 197 e os clientes de 87 pra 30). So dropa rascunho.
    Cancelamento nao e detectavel sem o pivot de tags (sumiu do schema);
    a diferenca vs o MCP fica < 1%."""
    loc = (e.get("localizador") or "")
    return not loc.startswith("DRAFT_")


def _no_periodo(data, ini, fim):
    if not data:
        return False
    return (not ini or data >= ini) and (not fim or data <= fim)


# --- emissoes -------------------------------------------------------

def resumo_emissoes(emissoes):
    v = [e for e in emissoes if _venda_real(e)]
    vendas = sum(_n(e.get("sale_value")) for e in v)
    custo = sum(_n(e.get("total_cost")) for e in v)
    lucro = sum(_n(e.get("profit")) for e in v)
    q = len(v)
    return {
        "quantidade": q,
        "vendas_total": vendas,
        "custo_total": custo,
        "lucro_total": lucro,
        "ticket_medio": vendas / q if q else 0.0,
        "margem_pct": 100 * lucro / vendas if vendas else 0.0,
    }


def emissoes_por_mes(emissoes):
    b = defaultdict(lambda: {"qtd": 0, "vendas": 0.0, "lucro": 0.0})
    for e in emissoes:
        if not _venda_real(e):
            continue
        d = _d(e.get("emission_date"))
        if not d:
            continue
        k = "%04d-%02d" % (d.year, d.month)
        b[k]["qtd"] += 1
        b[k]["vendas"] += _n(e.get("sale_value"))
        b[k]["lucro"] += _n(e.get("profit"))
    for k in b:
        b[k]["margem_pct"] = (100 * b[k]["lucro"] / b[k]["vendas"]
                              if b[k]["vendas"] else 0.0)
    return dict(sorted(b.items()))


def ranking_emissores(emissoes, perfis):
    nome = {p["id"]: p.get("full_name") for p in perfis}
    b = defaultdict(lambda: {"qtd": 0, "vendas": 0.0, "lucro": 0.0})
    for e in emissoes:
        if not _venda_real(e):
            continue
        k = e.get("emissor_id")
        b[k]["qtd"] += 1
        b[k]["vendas"] += _n(e.get("sale_value"))
        b[k]["lucro"] += _n(e.get("profit"))
    saida = [dict(emissor=nome.get(k, k), **val) for k, val in b.items()]
    return sorted(saida, key=lambda x: -x["lucro"])


def comissoes_a_pagar(emissoes, perfis):
    nome = {p["id"]: p.get("full_name") for p in perfis}
    b = defaultdict(lambda: {"total": 0.0, "pago": 0.0, "aberto": 0.0})
    for e in emissoes:
        val = _n(e.get("emissor_commission_value"))
        if not val:
            continue
        k = nome.get(e.get("emissor_id"), e.get("emissor_id"))
        b[k]["total"] += val
        if e.get("commission_payment_date"):
            b[k]["pago"] += val
        else:
            b[k]["aberto"] += val
    return dict(b)


# --- financeiro -----------------------------------------------------

def _fin_validas(transacoes):
    """Fora: transferencia entre contas, type != receita/despesa, rascunho.
    Dedup por id (chamadas diferentes trazem a mesma linha - ex: 'todas' +
    'em aberto')."""
    vistos = set()
    out = []
    for t in transacoes:
        tid = t.get("id")
        if tid in vistos:
            continue
        vistos.add(tid)
        if t.get("type") not in (TIPO_RECEITA, TIPO_DESPESA):
            continue
        if t.get("destination_account_id"):
            continue
        if (t.get("description") or "").startswith("DRAFT_"):
            continue
        out.append(t)
    return out


def _venc(t):
    """Data de vencimento de uma transacao: invoice_due_date quando existe
    (raro), senao transaction_date (o padrao na Volly)."""
    return _d(t.get("invoice_due_date") or t.get("transaction_date"))


def financeiro_resumo(transacoes, inicio=None, fim=None, campo="transaction_date"):
    """A receber/pagar (nao pago) e recebido/pago. Com `inicio`/`fim`,
    restringe pelo `campo` de data (default transaction_date, igual ao
    financial_summary do MCP)."""
    v = _fin_validas(transacoes)
    ini, fmp = _d(inicio), _d(fim)
    if ini or fmp:
        v = [t for t in v if _no_periodo(_d(t.get(campo)), ini, fmp)]

    def soma(pred):
        return sum(_n(t.get("amount")) for t in v if pred(t))

    receber = soma(lambda t: t["type"] == TIPO_RECEITA and not t.get("is_paid"))
    pagar = soma(lambda t: t["type"] == TIPO_DESPESA and not t.get("is_paid"))
    recebido = soma(lambda t: t["type"] == TIPO_RECEITA and t.get("is_paid"))
    pago = soma(lambda t: t["type"] == TIPO_DESPESA and t.get("is_paid"))
    return {
        "a_receber": receber, "a_pagar": pagar,
        "recebido": recebido, "pago": pago,
        "saldo_realizado": recebido - pago,
        "saldo_projetado": (recebido + receber) - (pago + pagar),
    }


def dre(transacoes, categorias, inicio, fim, regime="competencia"):
    v = _fin_validas(transacoes)
    campo = "competence_date" if regime == "competencia" else "payment_date"
    ini, fmp = _d(inicio), _d(fim)
    catnome = {c["id"]: c.get("name") for c in categorias}
    receita, despesa = defaultdict(float), defaultdict(float)
    for t in v:
        if regime == "caixa" and not t.get("is_paid"):
            continue
        d = _d(t.get(campo) or t.get("transaction_date"))
        if not _no_periodo(d, ini, fmp):
            continue
        nome = catnome.get(t.get("category_id")) or "Sem categoria"
        alvo = receita if t["type"] == TIPO_RECEITA else despesa
        alvo[nome] += _n(t.get("amount"))
    tr, td = sum(receita.values()), sum(despesa.values())
    return {
        "receita_total": tr, "despesa_total": td, "resultado": tr - td,
        "margem_pct": 100 * (tr - td) / tr if tr else 0.0,
        "receitas": dict(sorted(receita.items(), key=lambda x: -x[1])),
        "despesas": dict(sorted(despesa.items(), key=lambda x: -x[1])),
    }


def vencidos(transacoes_aberto, hoje=None):
    hoje = hoje or _dt.date.today()
    out = []
    for t in _fin_validas(transacoes_aberto):
        if t.get("is_paid"):
            continue
        d = _venc(t)
        if d and d < hoje:
            out.append({
                "tipo": t["type"], "valor": _n(t.get("amount")),
                "vencimento": d.isoformat(), "dias_atraso": (hoje - d).days,
                "descricao": t.get("description"),
            })
    return sorted(out, key=lambda x: -x["dias_atraso"])


def a_vencer(transacoes_aberto, dias=30, hoje=None):
    hoje = hoje or _dt.date.today()
    lim = hoje + _dt.timedelta(days=dias)
    out = []
    for t in _fin_validas(transacoes_aberto):
        if t.get("is_paid"):
            continue
        d = _venc(t)
        if d and hoje <= d <= lim:
            out.append({
                "tipo": t["type"], "valor": _n(t.get("amount")),
                "vencimento": d.isoformat(), "descricao": t.get("description"),
            })
    return sorted(out, key=lambda x: x["vencimento"])


def fornecedores_saldo(transacoes_aberto, fornecedores):
    nome = {f["id"]: f.get("name") for f in fornecedores}
    b = defaultdict(float)
    for t in transacoes_aberto:
        if (t.get("type") == TIPO_DESPESA and not t.get("is_paid")
                and t.get("supplier_id")):
            b[t["supplier_id"]] += _n(t.get("amount"))
    return sorted(
        [{"fornecedor": nome.get(k, k), "saldo_aberto": v} for k, v in b.items()],
        key=lambda x: -x["saldo_aberto"])


def contas_saldo(contas):
    return [{"nome": c.get("name"), "tipo": c.get("type"),
             "saldo": _n(c.get("current_balance"))}
            for c in contas]


# --- clientes ------------------------------------------------------

def clientes_agregado(clientes, emissoes, hoje=None):
    hoje = hoje or _dt.date.today()
    lim12 = hoje - _dt.timedelta(days=365)
    ag = defaultdict(lambda: {"qtd": 0, "receita": 0.0, "lucro": 0.0,
                              "primeira": None, "ultima": None, "qtd_12m": 0})
    for e in emissoes:
        if not _venda_real(e):
            continue
        cid = e.get("client_id")
        if not cid:
            continue
        d = _d(e.get("emission_date"))
        a = ag[cid]
        a["qtd"] += 1
        a["receita"] += _n(e.get("sale_value"))
        a["lucro"] += _n(e.get("profit"))
        if d:
            if not a["primeira"] or d < a["primeira"]:
                a["primeira"] = d
            if not a["ultima"] or d > a["ultima"]:
                a["ultima"] = d
            if d >= lim12:
                a["qtd_12m"] += 1
    out = []
    for c in clientes:
        a = ag.get(c["id"])
        if not a:
            continue
        out.append({
            "client_id": c["id"], "cliente": c.get("name"),
            "telefone": c.get("phone"), "lead_source": c.get("lead_source"),
            "qtd_emissoes": a["qtd"], "qtd_12m": a["qtd_12m"],
            "total_comprado": a["receita"], "lucro_gerado": a["lucro"],
            "ticket_medio": a["receita"] / a["qtd"] if a["qtd"] else 0.0,
            "primeira_emissao": a["primeira"].isoformat() if a["primeira"] else None,
            "ultima_emissao": a["ultima"].isoformat() if a["ultima"] else None,
            "dias_desde_ultima": (hoje - a["ultima"]).days if a["ultima"] else None,
            "dias_desde_primeira": (hoje - a["primeira"]).days if a["primeira"] else None,
        })
    return out


def ltv(agregado, ordenar_por="lucro_gerado", limite=20):
    return sorted(agregado, key=lambda x: -x.get(ordenar_por, 0))[:limite]


def segmentar_clientes(agregado):
    ativos = [a for a in agregado if a["dias_desde_ultima"] is not None]
    if not ativos:
        return {}
    receitas = sorted((a["total_comprado"] for a in ativos), reverse=True)
    corte_vip = receitas[max(0, len(receitas) // 10 - 1)]
    seg = {"vip": [], "frequent": [], "new": [], "at_risk": [],
           "lost": [], "high_potential": [], "inativos": []}
    for a in ativos:
        d = a["dias_desde_ultima"]
        if a["total_comprado"] >= corte_vip:
            seg["vip"].append(a)
        if a["qtd_12m"] >= 3:
            seg["frequent"].append(a)
        if (a["dias_desde_primeira"] or 999) < 90:
            seg["new"].append(a)
        if 60 <= d <= 180:
            seg["at_risk"].append(a)
        if d > 180:
            seg["lost"].append(a)
        if d >= 90:
            seg["inativos"].append(a)
        if a["qtd_emissoes"] <= 2 and a["ticket_medio"] >= 5000 and d <= 180:
            seg["high_potential"].append(a)
    return {k: sorted(v, key=lambda x: -x["total_comprado"])
            for k, v in seg.items()}


def aniversariantes(clientes, agregado, dias=30, hoje=None):
    hoje = hoje or _dt.date.today()
    porid = {a["client_id"]: a for a in agregado}
    out = []
    for c in clientes:
        d = _d(c.get("birth_date"))
        if not d:
            continue
        try:
            prox = d.replace(year=hoje.year)
        except ValueError:
            continue
        if prox < hoje:
            try:
                prox = d.replace(year=hoje.year + 1)
            except ValueError:
                continue
        delta = (prox - hoje).days
        if 0 <= delta <= dias:
            a = porid.get(c["id"], {})
            out.append({
                "cliente": c.get("name"), "dias_ate": delta,
                "aniversario": d.isoformat(), "telefone": c.get("phone"),
                "ltv": a.get("total_comprado", 0),
                "qtd_emissoes": a.get("qtd_emissoes", 0),
                "ultima_emissao": a.get("ultima_emissao"),
            })
    return sorted(out, key=lambda x: (x["dias_ate"], -x["ltv"]))


# --- milhas -------------------------------------------------------

def milhas_resumo(contas):
    b = defaultdict(lambda: {"saldo": 0.0, "contas": 0, "cpf_livres": 0,
                             "investido": 0.0, "_num": 0.0, "_den": 0.0})
    for c in contas:
        p = b[c.get("program") or "?"]
        saldo = _n(c.get("balance"))
        p["saldo"] += saldo
        p["contas"] += 1
        p["cpf_livres"] += int(max(0, _n(c.get("cpf_limit")) - _n(c.get("cpf_used"))))
        p["investido"] += _n(c.get("total_invested"))
        if _n(c.get("cpm")) and saldo:
            p["_num"] += _n(c.get("cpm")) * saldo
            p["_den"] += saldo
    out = {}
    for prog, p in b.items():
        out[prog] = {
            "saldo": p["saldo"], "contas": p["contas"],
            "cpf_livres": p["cpf_livres"], "investido": p["investido"],
            "cpm_medio": p["_num"] / p["_den"] if p["_den"] else 0.0,
        }
    return dict(sorted(out.items(), key=lambda x: -x[1]["saldo"]))


def clubes_ativos(contas):
    out = []
    for c in contas:
        if not c.get("club_active"):
            continue
        out.append({
            "conta": c.get("name"), "programa": c.get("program"),
            "custo_mensal": _n(c.get("club_monthly_cost")),
            "pontos_mes": _n(c.get("club_points_monthly")),
            "meses_ativo": _n(c.get("club_months_active")),
            "renovacao": (_d(c.get("club_annual_renewal_date")).isoformat()
                          if _d(c.get("club_annual_renewal_date")) else None),
            "renovacao_pendente": bool(c.get("club_renewal_pending")),
        })
    return out


def clubes_alerta(contas, dias=45, hoje=None):
    hoje = hoje or _dt.date.today()
    out = []
    for c in clubes_ativos(contas):
        d = _d(c["renovacao"])
        if c["renovacao_pendente"] or (d and 0 <= (d - hoje).days <= dias):
            out.append(c)
    return out


def milhas_ociosas(contas, cpm_max=6):
    """Contas com saldo + CPFs livres a CPM baixo = capacidade parada barata."""
    out = []
    for c in contas:
        cpm = _n(c.get("cpm"))
        livres = max(0, _n(c.get("cpf_limit")) - _n(c.get("cpf_used")))
        if _n(c.get("balance")) > 0 and livres >= 5 and 0 < cpm <= cpm_max:
            out.append({"conta": c.get("name"), "programa": c.get("program"),
                        "saldo": _n(c.get("balance")), "cpf_livres": int(livres),
                        "cpm": cpm})
    return sorted(out, key=lambda x: x["cpm"])


# --- CRM ---------------------------------------------------------

def _pos_atual(placements):
    """quote_id -> (funnel_id, column_key) da colocacao primaria."""
    pos = {}
    for p in placements:
        if p.get("is_primary") or p["quote_id"] not in pos:
            pos[p["quote_id"]] = (p.get("funnel_id"), p.get("column_key"))
    return pos


def crm_conversao(cotacoes, colunas, placements, funis):
    fnome = {f["id"]: f.get("name") for f in funis}
    stype = {(c.get("funnel_id"), c.get("column_key")): c.get("stage_type")
             for c in colunas}
    qval = {q["id"]: _n(q.get("total_value")) for q in cotacoes}
    pos = _pos_atual(placements)
    b = defaultdict(lambda: {"total": 0, "ganho": 0, "perdido": 0,
                             "andamento": 0, "valor_ganho": 0.0,
                             "valor_perdido": 0.0})
    for qid, (fid, ck) in pos.items():
        r = b[fid]
        r["total"] += 1
        st = stype.get((fid, ck))
        if st == "won":
            r["ganho"] += 1
            r["valor_ganho"] += qval.get(qid, 0)
        elif st == "lost":
            r["perdido"] += 1
            r["valor_perdido"] += qval.get(qid, 0)
        else:
            r["andamento"] += 1
    saida = {}
    for fid, r in b.items():
        fechados = r["ganho"] + r["perdido"]
        r["conversao_pct"] = 100 * r["ganho"] / fechados if fechados else 0.0
        saida[fnome.get(fid, fid)] = r
    return saida


def crm_valor_por_etapa(colunas, placements, cotacoes, funis):
    fnome = {f["id"]: f.get("name") for f in funis}
    titulo = {(c.get("funnel_id"), c.get("column_key")): c.get("title")
              for c in colunas}
    stype = {(c.get("funnel_id"), c.get("column_key")): c.get("stage_type")
             for c in colunas}
    qval = {q["id"]: _n(q.get("total_value")) for q in cotacoes}
    pos = _pos_atual(placements)
    b = defaultdict(lambda: {"qtd": 0, "valor": 0.0})
    for qid, key in pos.items():
        b[key]["qtd"] += 1
        b[key]["valor"] += qval.get(qid, 0)
    return [{
        "funil": fnome.get(k[0], k[0]),
        "etapa": titulo.get(k, k[1]), "tipo": stype.get(k),
        "qtd": v["qtd"], "valor": v["valor"],
    } for k, v in b.items()]


def crm_followups_atrasados(followups, cotacoes, hoje=None):
    hoje = hoje or _dt.date.today()
    qinfo = {q["id"]: q for q in cotacoes}
    out = []
    for f in followups:
        if (f.get("status") or "").lower() in FOLLOWUP_FEITO:
            continue
        d = _d(f.get("followup_date"))
        if not d or d >= hoje:
            continue
        q = qinfo.get(f.get("quote_id"), {})
        out.append({
            "cotacao": q.get("title"), "cliente": q.get("client_name"),
            "valor": _n(q.get("total_value")), "coluna": f.get("column_key"),
            "previsto": d.isoformat(), "dias_atraso": (hoje - d).days,
        })
    return sorted(out, key=lambda x: -x["dias_atraso"])


def crm_perdidos(cotacoes, colunas, placements, funis, limite=15):
    stype = {(c.get("funnel_id"), c.get("column_key")): c.get("stage_type")
             for c in colunas}
    qinfo = {q["id"]: q for q in cotacoes}
    pos = _pos_atual(placements)
    out = []
    for qid, key in pos.items():
        if stype.get(key) == "lost":
            q = qinfo.get(qid, {})
            out.append({"cotacao": q.get("title"), "cliente": q.get("client_name"),
                        "valor": _n(q.get("total_value"))})
    return sorted(out, key=lambda x: -x["valor"])[:limite]


# --- NFS-e -----------------------------------------------------

def nfse_conformidade(emissoes, notas, inicio, fim):
    ini, fmp = _d(inicio), _d(fim)
    alvo = [e for e in emissoes if _venda_real(e)
            and _no_periodo(_d(e.get("emission_date")), ini, fmp)]
    ok = {n.get("emission_id") for n in notas
          if (n.get("status") or "").lower() in NFSE_OK}
    faltantes = [e for e in alvo if e["id"] not in ok]
    total = len(alvo)
    return {
        "total": total, "com_nota": total - len(faltantes),
        "faltantes": len(faltantes),
        "conformidade_pct": 100 * (total - len(faltantes)) / total if total else 100.0,
        "lista_faltantes": sorted(
            [{"localizador": e.get("localizador"),
              "valor": _n(e.get("sale_value")),
              "data": e.get("emission_date")} for e in faltantes],
            key=lambda x: x["data"] or ""),
    }


# --- equipe ----------------------------------------------------

def tarefas_atrasadas(tarefas, perfis, hoje=None):
    hoje = hoje or _dt.date.today()
    nome = {p["id"]: p.get("full_name") for p in perfis}
    out = []
    for t in tarefas:
        if (t.get("status") or "").lower() in TAREFA_FEITA:
            continue
        d = _d(t.get("due_date"))
        if not d or d >= hoje:
            continue
        out.append({
            "titulo": t.get("title"),
            "responsavel": nome.get(t.get("assigned_to"), "—"),
            "prioridade": t.get("priority"),
            "venceu": d.isoformat(), "dias_atraso": (hoje - d).days,
        })
    return sorted(out, key=lambda x: -x["dias_atraso"])
