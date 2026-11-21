"""Espelho dos clubes da Volly no painel (tabelas `clubes` e `clubes_eventos`).

A Volly so guarda o estado atual de cada conta (club_active, custo, dia de
vencimento). Aqui a gente copia isso pro painel e grava um evento a cada
mudanca (ativou, desativou, custo, pontos, vencimento) - o historico comeca na
1a rodada (que nao gera evento: so grava a base). Tambem avisa no Telegram, 1
dia antes, os clubes que vencem amanha. So LE da Volly.
"""

import datetime
import html
import calendar

import alertas
import supabase_rest


def linha_do_painel(conta):
    """Conta da Volly (volly.milhas_clubes) -> linha da tabela `clubes`."""
    return {
        "conta_id": conta["id"],
        "titular": (conta.get("name") or "").strip(),
        "programa": conta.get("program") or "",
        "ativo": bool(conta.get("club_active")),
        "dia_venc": conta.get("club_due_day"),
        "custo_mensal": conta.get("club_monthly_cost"),
        "pontos_mes": conta.get("club_points_monthly"),
        "membro_desde": (conta.get("club_member_since") or None) and str(conta["club_member_since"])[:10],
        "meses_ativo": conta.get("club_months_active"),
    }


def _num(v):
    return None if v is None else float(v)


def eventos_novos(antigas, novas):
    """Eventos das mudancas entre o espelho (dict conta_id -> linha) e a Volly.

    Primeira carga (espelho vazio) nao gera evento: seria um "ativou" falso
    por conta. Conta que ainda nao existia no espelho depois disso: "ativou"
    se ja chegou ativa.
    """
    if not antigas:
        return []
    eventos = []

    def ev(n, tipo, de, para):
        eventos.append({"conta_id": n["conta_id"], "titular": n["titular"],
                        "programa": n["programa"], "tipo": tipo,
                        "de": None if de is None else str(de),
                        "para": None if para is None else str(para)})

    for n in novas:
        a = antigas.get(n["conta_id"])
        if a is None:
            if n["ativo"]:
                ev(n, "ativou", None, None)
            continue
        if a["ativo"] != n["ativo"]:
            ev(n, "ativou" if n["ativo"] else "desativou", None, None)
        if _num(a.get("custo_mensal")) != _num(n["custo_mensal"]):
            ev(n, "custo", a.get("custo_mensal"), n["custo_mensal"])
        if a.get("pontos_mes") != n["pontos_mes"]:
            ev(n, "pontos", a.get("pontos_mes"), n["pontos_mes"])
        if a.get("dia_venc") != n["dia_venc"]:
            ev(n, "vencimento", a.get("dia_venc"), n["dia_venc"])
    return eventos


def vence_em(dia_venc, data):
    """True se o clube de dia `dia_venc` vence em `data` (dia 31 num mes de 30
    dias vence no ultimo dia)."""
    if not dia_venc:
        return False
    ultimo = calendar.monthrange(data.year, data.month)[1]
    return min(int(dia_venc), ultimo) == data.day


def aviso_de_vencimento(linhas, amanha):
    """Texto HTML do aviso de amanha, ou None. Pula quem ja foi avisado."""
    vencendo = [l for l in linhas
                if l["ativo"] and vence_em(l["dia_venc"], amanha)
                and l.get("avisado_venc") != amanha.isoformat()]
    if not vencendo:
        return None, []
    vencendo.sort(key=lambda l: (l["programa"], l["titular"]))
    corpo = "\n".join("• %s — %s (R$ %s)" % (html.escape(l["titular"]), html.escape(l["programa"]),
                                              ("%.2f" % float(l["custo_mensal"] or 0)).replace(".", ","))
                      for l in vencendo)
    return "<b>Clubes vencem amanhã (%s)</b>\n%s" % (amanha.strftime("%d/%m"), corpo), vencendo


def sincronizar(volly, supabase_url, service_key, telegram_token=None, telegram_chat=None,
                plano=False, hoje=None):
    """Espelha, grava eventos e avisa vencimento. Devolve contagens."""
    contas = volly.milhas_clubes()
    novas = [linha_do_painel(c) for c in contas]
    antigas = {l["conta_id"]: l for l in
               supabase_rest.select(supabase_url, service_key, "clubes", {"select": "*", "limit": 5000})}
    eventos = eventos_novos(antigas, novas)
    # preserva o aviso ja feito: o upsert nao pode zerar avisado_venc
    for n in novas:
        n["avisado_venc"] = (antigas.get(n["conta_id"]) or {}).get("avisado_venc")
    hoje = hoje or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).date()
    amanha = hoje + datetime.timedelta(days=1)
    texto, vencendo = aviso_de_vencimento(novas, amanha)
    avisados = 0
    if not plano:
        supabase_rest.upsert(supabase_url, service_key, "clubes", novas, "conta_id")
        for e in eventos:
            supabase_rest.inserir(supabase_url, service_key, "clubes_eventos", e)
        if texto:
            ok, _ = alertas.enviar_telegram(telegram_token, telegram_chat, texto)
            if ok:
                for l in vencendo:
                    supabase_rest.atualizar(supabase_url, service_key, "clubes",
                                            {"conta_id": "eq." + l["conta_id"]},
                                            {"avisado_venc": amanha.isoformat()})
                avisados = len(vencendo)
    return {"contas": len(novas), "eventos": len(eventos), "avisados": avisados,
            "vencendo_amanha": len(vencendo)}
