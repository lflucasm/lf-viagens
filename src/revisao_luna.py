"""Coleta mensal para a revisao critica da Luna (IA de atendimento da Volly).

Uso: python3 src/revisao_luna.py [--dias 30]
Somente leitura. Grava em dados/atendimento/revisoes/AAAA-MM/ (fora do git, tem
dados de clientes): config.json (configuracao ao vivo da Luna), config_diff.txt
(o que mudou desde a revisao anterior), metricas.json, indice.md e conversas/*.md.
O guia de analise esta em .claude/skills/revisao-mensal-luna/SKILL.md.
"""
import argparse
import collections
import datetime as dt
import difflib
import json
import os
import re
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config
from volly_chat import VollyChat

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = os.path.join(RAIZ, "dados", "atendimento", "revisoes")
CONEXAO = "4ab575e4-37f9-496e-b7f2-4d09f3c33e1a"  # LF Viagens Comercial
SINAIS_RUIM = re.compile(
    r"\b(rob[oô]|bot|humano|pessoa de verdade|atendente|n[aã]o entendi|j[aá] falei|"
    r"j[aá] disse|de novo|repetindo|n[aã]o era isso|para de)\b", re.I)


def ts(s):
    # python < 3.11 so aceita 3 ou 6 casas de fracao de segundo
    s = re.sub(r"\.(\d+)", lambda r: "." + r.group(1)[:6].ljust(6, "0"), s.replace("Z", "+00:00"))
    return dt.datetime.fromisoformat(s)


def papel(m, nome_ia):
    """CLIENTE | LUNA | NOTA_IA | NOTA | EQUIPE_OU_AUTO (celular, painel ou CRM)."""
    corpo = m.get("body") or ""
    if m["direction"] == "in":
        return "CLIENTE"
    if m.get("is_internal_note"):
        return "NOTA_IA" if corpo.startswith("🤖") else "NOTA"
    return "LUNA" if corpo.startswith("*%s*" % nome_ia) else "EQUIPE_OU_AUTO"


def metricas(convs, msgs, eventos, leads, lead_ev, nome_ia):
    por_conv = collections.defaultdict(list)
    for m in msgs:
        m["_p"] = papel(m, nome_ia)
        por_conv[m["conversation_id"]].append(m)
    c = collections.Counter(m["_p"] for m in msgs)
    luna_convs = {k for k, v in por_conv.items() if any(x["_p"] == "LUNA" for x in v)}
    notas = [m["body"] for m in msgs if m["_p"] == "NOTA_IA"]
    motivos = collections.Counter(
        re.sub(r"\s+", " ", x.split("Motivo:", 1)[1]).strip()[:90]
        for x in notas if "transferi para um atendente" in x and "Motivo:" in x)
    campos = collections.Counter()
    for x in notas:
        r = re.search(r"pré-qualificação: (.*?)\.?$", x.split("\n")[0])
        if r:
            campos.update(p.strip() for p in r.group(1).split(";")[0].split(","))
    # tempo ate a primeira resposta da Luna a cada rajada de mensagens do cliente
    tempos, sem_resposta = [], 0
    for v in (por_conv[k] for k in luna_convs):
        v.sort(key=lambda m: m["created_at"])
        for i, m in enumerate(v):
            if m["_p"] != "CLIENTE" or (i and v[i - 1]["_p"] == "CLIENTE"):
                continue
            prox = next((x for x in v[i + 1:] if x["_p"] in ("LUNA", "EQUIPE_OU_AUTO")), None)
            if prox and prox["_p"] == "LUNA":
                tempos.append((ts(prox["created_at"]) - ts(m["created_at"])).total_seconds())
            elif not prox:
                sem_resposta += 1
    # follow-up: tentativa enviada -> cliente respondeu em ate 48h?
    resp = collections.defaultdict(lambda: [0, 0])
    inb = collections.defaultdict(list)
    for m in msgs:
        if m["_p"] == "CLIENTE":
            inb[m["conversation_id"]].append(ts(m["created_at"]))
    for e in lead_ev:
        if e["kind"] == "sent":
            t = ts(e["occurred_at"])
            ok = any(t < x <= t + dt.timedelta(hours=48) for x in inb.get(e["conversation_id"], []))
            resp[e.get("attempt") or 0][0] += 1
            resp[e.get("attempt") or 0][1] += ok
    repetidas = collections.Counter(m["body"].strip() for m in msgs if m["_p"] == "LUNA")
    ev = collections.Counter(e["kind"] for e in eventos)
    notas_audio = sum(1 for m in msgs if m["_p"] == "CLIENTE" and "audio" in (m.get("media_type") or ""))
    return {
        "mensagens_por_papel": dict(c),
        "conversas_no_periodo": len(por_conv),
        "conversas_com_luna": len(luna_convs),
        "eventos": dict(ev),
        "temperatura_leads": dict(collections.Counter(
            (e["detail"] or {}).get("temperature") for e in eventos if e["kind"] == "lead_scored")),
        "motivos_de_transferencia": dict(motivos.most_common(15)),
        "pausas_por_humano": sum("pausei nesta conversa" in x for x in notas),
        "cotacoes_criadas": sum("Cotação criada" in x for x in notas),
        "campos_qualificacao_registrados": dict(campos.most_common()),
        "primeira_resposta_luna_seg": {
            "mediana": statistics.median(tempos) if tempos else None, "n": len(tempos)},
        "rajadas_cliente_sem_nenhuma_resposta": sem_resposta,
        "audios_do_cliente": notas_audio,
        "followup_leads_por_estagio_status": dict(collections.Counter(
            "%s/%s" % (x["stage"], x["status"]) for x in leads)),
        "followup_tentativas_enviadas_e_respondidas_48h": {
            str(k): {"enviadas": v[0], "respondidas": v[1]} for k, v in sorted(resp.items())},
        "followup_eventos": dict(collections.Counter(e["kind"] for e in lead_ev)),
        "mensagens_luna_repetidas_3x": {k[:100]: n for k, n in repetidas.items() if n >= 3},
    }, por_conv, luna_convs


def sinalizar(v):
    """Marca conversas onde a Luna merece leitura critica."""
    f = []
    for i, m in enumerate(v):
        if m["_p"] == "CLIENTE" and SINAIS_RUIM.search(m.get("body") or "") \
                and any(x["_p"] == "LUNA" for x in v[:i]):
            f.append("cliente_reclama_ou_pede_humano")
            break
    if any("transferi para um atendente" in (m.get("body") or "") for m in v if m["_p"] == "NOTA_IA"):
        f.append("transferiu")
    if any("pausei" in (m.get("body") or "") for m in v if m["_p"] == "NOTA_IA"):
        f.append("humano_assumiu")
    if v and v[-1]["_p"] == "LUNA":
        f.append("ultima_msg_foi_da_luna")
    if v and v[-1]["_p"] == "CLIENTE":
        f.append("cliente_ficou_sem_resposta")
    return f


def transcrever(v, nome):
    linhas = ["# %s\n" % nome]
    for m in v:
        corpo = (m.get("body") or "").strip() or "[%s]" % (m.get("media_type") or "sem texto")
        hora = (ts(m["created_at"]) - dt.timedelta(hours=3)).strftime("%d/%m %H:%M")  # horario de Brasilia
        linhas.append("**%s** %s (%s): %s" % (m["_p"], hora,
                                              "int" if m.get("is_internal_note") else m["direction"], corpo))
    return "\n\n".join(linhas) + "\n"


def baixar_config(vc):
    req = urllib.request.Request(
        "https://chat.volly.com.br/api/v1/ai/config/" + CONEXAO,
        headers={"Authorization": "Bearer " + vc._token(), "X-Org-Id": config.chat_organization_id,
                 "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def texto_config(cfg):
    q = cfg.get("qualifier") or {}
    return "\n".join([
        "## CONTEXTO (aba Conhecimento)", cfg.get("context") or "",
        "## LEAD IDEAL (aba Qualificação)", q.get("leadCriteria") or "",
        "## CAMPOS DE QUALIFICAÇÃO"] + ["- %s: %s" % (f["label"], f["hint"]) for f in q.get("qualifyFields", [])] + [
        "## INSTRUÇÕES PROATIVAS (Follow-up)", (cfg.get("proactive") or {}).get("instructions") or "",
        "## AJUSTES DO FOLLOW-UP", json.dumps({k: v for k, v in (cfg.get("proactive") or {}).items()
                                              if k != "instructions"}, ensure_ascii=False),
        "## DEMAIS AJUSTES", json.dumps({k: cfg.get(k) for k in (
            "model", "toggles", "hours", "replyDelaySeconds", "replyPace", "quotePolicy", "upsellProducts")},
            ensure_ascii=False)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    a = ap.parse_args()
    hoje = dt.date.today()
    desde = (hoje - dt.timedelta(days=a.dias)).isoformat()
    pasta = os.path.join(BASE, hoje.strftime("%Y-%m"))
    os.makedirs(os.path.join(pasta, "conversas"), exist_ok=True)

    vc = VollyChat(config)
    cfg = baixar_config(vc)
    nome_ia = cfg.get("aiName") or "Luna"
    anterior = sorted(p for p in os.listdir(BASE) if p != hoje.strftime("%Y-%m")
                      and os.path.exists(os.path.join(BASE, p, "config.json")))
    json.dump(cfg, open(os.path.join(pasta, "config.json"), "w"), ensure_ascii=False, indent=1)
    if anterior:
        velho = texto_config(json.load(open(os.path.join(BASE, anterior[-1], "config.json"))))
        dif = "\n".join(difflib.unified_diff(velho.splitlines(), texto_config(cfg).splitlines(),
                                             "revisao " + anterior[-1], "agora", lineterm="", n=1))
    else:
        dif = "(primeira revisao: sem versao anterior para comparar)"
    open(os.path.join(pasta, "config_diff.txt"), "w").write(dif or "(configuracao sem mudancas)")

    convs = [c for c in vc.conversas(so_abertas=False, desde=desde)
             if not (c.get("contacts") or {}).get("is_group")]
    ids = [c["id"] for c in convs]
    msgs = vc.mensagens_das_conversas(ids, desde=desde)
    org = {"organization_id": "eq." + config.chat_organization_id}
    eventos = [e for e in vc._buscar_tabela("conversation_events", {"select": "*", **org,
               "created_at": "gte." + desde}) if e["conversation_id"] in set(ids)]
    leads = vc._buscar_tabela("proactive_leads", {"select": "*", **org})
    lead_ev = [e for e in vc._buscar_tabela("proactive_lead_events", {"select": "*", **org})
               if e["occurred_at"] >= desde]

    met, por_conv, luna = metricas(convs, msgs, eventos, leads, lead_ev, nome_ia)
    met.update({"periodo": [desde, hoje.isoformat()], "modelo": cfg.get("model"),
                "tamanho_contexto": len(cfg.get("context") or ""),
                "creditos_ia_restantes": cfg.get("tokenBalance")})
    json.dump(met, open(os.path.join(pasta, "metricas.json"), "w"), ensure_ascii=False, indent=1)

    score = {}
    for e in eventos:
        if e["kind"] == "lead_scored":
            score[e["conversation_id"]] = e["detail"] or {}
    lead_por_conv = {x["conversation_id"]: x for x in leads}
    nomes = {c["id"]: ((c.get("contacts") or {}).get("custom_name") or (c.get("contacts") or {}).get("name")
                       or "sem nome") for c in convs}
    linhas = ["# Índice de conversas com a %s (%s a %s)\n" % (nome_ia, desde, hoje),
              "Conversas com sinal de problema primeiro. Abra `conversas/<id>.md` para ler.\n",
              "| id | contato | msgs Luna | msgs cliente | sinais | score | follow-up |", "|---|---|---|---|---|---|---|"]
    linhas_ord = []
    for k in luna:
        v = sorted(por_conv[k], key=lambda m: m["created_at"])
        f = sinalizar(v)
        open(os.path.join(pasta, "conversas", k[:8] + ".md"), "w").write(transcrever(v, nomes[k]))
        s = score.get(k, {})
        lp = lead_por_conv.get(k)
        linhas_ord.append((-len([x for x in f if x in ("cliente_reclama_ou_pede_humano", "cliente_ficou_sem_resposta")]),
                           "| %s | %s | %d | %d | %s | %s | %s |" % (
                               k[:8], nomes[k], sum(m["_p"] == "LUNA" for m in v),
                               sum(m["_p"] == "CLIENTE" for m in v), ", ".join(f) or "-",
                               "%s/%s" % (s.get("score"), s.get("temperature")) if s else "-",
                               "%s/%s t=%s" % (lp["stage"], lp["status"], lp["attempts"]) if lp else "-")))
    linhas += [l for _, l in sorted(linhas_ord, key=lambda x: x[0])]
    open(os.path.join(pasta, "indice.md"), "w").write("\n".join(linhas) + "\n")
    print("Pasta:", os.path.abspath(pasta))
    print(json.dumps(met, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
