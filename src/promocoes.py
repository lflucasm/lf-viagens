"""Promocoes de milhas/pontos: a IA so EXTRAI, o codigo CALCULA.

Entrada: texto de uma mensagem dos grupos de promocao (Telegram). A IA devolve
um JSON (SCHEMA); daqui pra frente e tudo codigo: validade, custo final por
milheiro, resumo e alerta de oportunidade por teto. Decisao do proprietário
(07/11/2026): custo final = milheiro / (1 + bonus), ex.: R$ 31,50/k com 25% de
bonus = R$ 25,20/k.
"""

import hashlib
import html
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
MODELO = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
TIPOS = ["compra_pontos", "transferencia_bonificada", "clube", "resgate", "outro"]


def _nulo(*tipos):
    return {"type": list(tipos) + ["null"]}


_PLANO = {
    "type": "object", "additionalProperties": False,
    "required": ["nome", "bonus_pct", "milheiro_parcelado", "milheiro_pix"],
    "properties": {
        "nome": {"type": "string"},  # plano/clube/publico ("Clube Livelo", "Todos")
        "bonus_pct": _nulo("number"),  # bonus na transferencia, em % (25 = 25%)
        "milheiro_parcelado": _nulo("number"),  # R$ por 1.000 pontos JA com desconto
        "milheiro_pix": _nulo("number"),
    },
}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["e_promocao", "programa", "tipo", "titulo", "inicio", "fim", "planos",
                 "limites", "regulamento_url"],
    "properties": {
        "e_promocao": {"type": "boolean"},  # false: conversa, aviso sem oferta, etc.
        "programa": _nulo("string"),  # Livelo, Smiles, LATAM Pass, Azul, TAP, Esfera, Iberia...
        "tipo": {"type": "string", "enum": TIPOS},
        "titulo": _nulo("string"),  # uma linha: "Transferencia Livelo -> Smiles com 100%"
        "inicio": _nulo("string"),  # AAAA-MM-DDTHH:MM, horario de Brasilia
        "fim": _nulo("string"),
        "planos": {"type": "array", "items": _PLANO},
        "limites": _nulo("string"),
        "regulamento_url": _nulo("string"),
    },
}
PROMPT = (
    "Voce le mensagens de grupos de promocao de milhas e pontos do Brasil. "
    "Extraia a oferta no JSON do schema. NAO CALCULE nada: copie so os numeros "
    "que estao escritos. Datas em horario de Brasilia (AAAA-MM-DDTHH:MM); "
    "resolva 'hoje/amanha/ate domingo' pela data da mensagem. milheiro_* e o "
    "preco em R$ por 1.000 pontos ja com o desconto. Se a mensagem nao traz "
    "uma oferta de verdade (conversa, resultado de sorteio, duvida), e_promocao=false.")


def chamar_openai(texto, data_msg, chave=None):
    """Chat completions com saida estruturada. Devolve o dict do schema."""
    corpo = json.dumps({
        "model": MODELO,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": "Data da mensagem: %s\n\n%s" % (data_msg, texto[:6000])}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "promocao", "strict": True, "schema": SCHEMA}},
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=corpo,
        headers={"Authorization": "Bearer " + (chave or os.environ["OPENAI_API_KEY"]),
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(json.loads(r.read().decode())["choices"][0]["message"]["content"])


def instante(texto):
    """'2026-11-10T23:59' (ou so a data -> fim do dia) em Brasilia -> datetime UTC."""
    if not texto:
        return None
    try:
        t = datetime.fromisoformat(texto.strip())
    except ValueError:
        return None
    if len(texto.strip()) <= 10:
        t = t.replace(hour=23, minute=59)
    return t.replace(tzinfo=BRT).astimezone(timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def custo_final(milheiro, bonus_pct):
    """R$ por milheiro depois do bonus. None se nao ha milheiro."""
    if not milheiro:
        return None
    return round(milheiro / (1 + (bonus_pct or 0) / 100), 2)


def cenarios(extr):
    """Um cenario por plano com milheiro: custo parcelado/Pix apos o bonus."""
    saida = []
    for p in extr.get("planos") or []:
        parc, pix = custo_final(p.get("milheiro_parcelado"), p.get("bonus_pct")), \
            custo_final(p.get("milheiro_pix"), p.get("bonus_pct"))
        if parc is None and pix is None:
            continue
        saida.append({"plano": p["nome"], "bonus_pct": p.get("bonus_pct"),
                      "milheiro_parcelado": p.get("milheiro_parcelado"),
                      "milheiro_pix": p.get("milheiro_pix"),
                      "custo_parcelado": parc, "custo_pix": pix})
    return saida


def tetos_de_env(texto):
    """'livelo=26;smiles=24,5' -> {'livelo': 26.0, 'smiles': 24.5}."""
    tetos = {}
    for par in (texto or "").split(";"):
        if "=" in par:
            nome, valor = par.split("=", 1)
            try:
                tetos[nome.strip().lower()] = float(valor.replace(",", "."))
            except ValueError:
                pass
    return tetos


def oportunidade(programa, cens, tetos):
    """Teto (R$/k) do programa se algum custo final ficou abaixo dele, senao None."""
    teto = tetos.get((programa or "").lower())
    custos = [c for x in cens for c in (x["custo_parcelado"], x["custo_pix"]) if c is not None]
    return teto if teto is not None and custos and min(custos) < teto else None


def id_da_promocao(extr):
    """Mesma oferta repostada em outro grupo cai no mesmo id (programa+tipo+fim+bonus)."""
    bonus = max([p.get("bonus_pct") or 0 for p in extr.get("planos") or []] or [0])
    base = "|".join([(extr.get("programa") or "").lower(), extr["tipo"],
                     (extr.get("fim") or "")[:10], str(bonus)])
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _reais(v):
    return "R$ " + ("%.2f" % v).replace(".", ",")


def _fim_texto(fim_utc):
    return fim_utc.astimezone(BRT).strftime("%d/%m %H:%M") if fim_utc else None


def resumo(extr, cens, teto=None):
    """Texto pro Telegram (HTML) e pro site (tags tiradas la)."""
    e = html.escape
    linhas = ["🎯 <b>%s — %s</b>" % (e(extr.get("programa") or "?"),
                                     e(extr.get("titulo") or extr["tipo"].replace("_", " ")))]
    fim = _fim_texto(instante(extr.get("fim")))
    if fim:
        linhas.append("📅 até %s (Brasília)" % fim)
    for c in cens:
        partes = []
        if c["milheiro_parcelado"]:
            partes.append("%s/k parcelado" % _reais(c["milheiro_parcelado"]))
        if c["milheiro_pix"]:
            partes.append("%s/k Pix" % _reais(c["milheiro_pix"]))
        linhas.append("• %s: %s" % (e(c["plano"]), " · ".join(partes)))
        if c["bonus_pct"]:
            final = [_reais(v) + "/k" for v in (c["custo_parcelado"], c["custo_pix"]) if v]
            linhas.append("   com %g%% de bônus → %s" % (c["bonus_pct"], " · ".join(final)))
    bonus_sem_preco = [p for p in extr.get("planos") or [] if p.get("bonus_pct")
                       and not p.get("milheiro_parcelado") and not p.get("milheiro_pix")]
    for p in bonus_sem_preco:
        linhas.append("• %s: %g%% de bônus" % (e(p["nome"]), p["bonus_pct"]))
    if extr.get("limites"):
        linhas.append("⚠️ " + e(extr["limites"]))
    if teto is not None:
        linhas.append("🔥 <b>Abaixo do seu teto de %s/k</b>" % _reais(teto))
    if extr.get("regulamento_url"):
        linhas.append("📄 " + e(extr["regulamento_url"]))
    return "\n".join(linhas)


def montar(extr, tetos, fonte, mensagem_url):
    """Linha pronta pra tabela `promocoes`, ou None se nao for promocao."""
    if not extr.get("e_promocao") or not extr.get("programa"):
        return None
    cens = cenarios(extr)
    teto = oportunidade(extr["programa"], cens, tetos)
    ini, fim = instante(extr.get("inicio")), instante(extr.get("fim"))
    return {
        "id": id_da_promocao(extr), "programa": extr["programa"], "tipo": extr["tipo"],
        "inicio": ini.isoformat() if ini else None, "fim": fim.isoformat() if fim else None,
        "dados": extr, "cenarios": cens, "resumo": resumo(extr, cens, teto),
        "oportunidade": teto is not None, "fonte": fonte, "mensagem_url": mensagem_url}
