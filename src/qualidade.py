"""Regras de qualidade: um voo so pode ser checado se tiver o que o portal pede.

Requisitos levantados nos formularios reais (inspecao em 29/07/2026):

  GOL    b2c.voegol.com.br/minhas-viagens/encontrar-viagem
         localizador OU numero do bilhete + aeroporto de ORIGEM + sobrenome
  LATAM  latamairlines.com/br/pt/minhas-viagens
         localizador OU numero da compra + sobrenome

Nenhuma das duas pediu captcha na consulta.
"""

import re
import unicodedata

import fusos

PNR = re.compile(r"^[A-Z0-9]{6}$")
SO_NUMERO = re.compile(r"^\d{6,}$")

CIAS_SUPORTADAS = {
    "latam": "LATAM",
    "gol": "GOL",
    "azul": "AZUL",
    "copa": "COPA",
}

# O que cada portal exige. Cias sem conector caem no padrao.
REQUISITOS = {
    "GOL": {"localizador", "sobrenome", "origem"},
    "LATAM": {"localizador", "sobrenome"},
    "AZUL": {"localizador", "origem"},   # nao pede sobrenome
}
REQUISITO_PADRAO = {"localizador", "sobrenome"}

# Portais que aceitam numero de bilhete/compra no lugar do PNR
ACEITAM_NUMERO_BILHETE = ("GOL", "LATAM")


def normalizar_cia(cia):
    if not cia:
        return None
    texto = cia.strip().lower()
    for chave, nome in CIAS_SUPORTADAS.items():
        if chave in texto:
            return nome
    return cia.strip().upper()


def primeiro_passageiro(passageiros):
    """Nome do titular. O CRM separa os passageiros da reserva por ' / '."""
    return (passageiros or "").split(" / ")[0].strip()


def nomes_passageiros(passageiros, limite=4):
    """Todos os passageiros da reserva pra mensagem ("A, B e C" / "... +2").

    Pedido do proprietário (27/09/2026): toda mensagem de voo, no site e no
    Telegram, traz o nome do passageiro - nao so o titular.
    """
    nomes = []
    for n in (passageiros or "").split(" / "):
        n = " ".join(n.split())
        if n and n not in nomes:
            nomes.append(n)
    if not nomes:
        return ""
    if len(nomes) > limite:
        return "%s +%d" % (", ".join(nomes[:limite]), len(nomes) - limite)
    if len(nomes) == 1:
        return nomes[0]
    return "%s e %s" % (", ".join(nomes[:-1]), nomes[-1])


def sobrenome(passageiros):
    """Ultimo nome do primeiro passageiro - e o que os portais pedem."""
    partes = [p for p in primeiro_passageiro(passageiros).split() if len(p) > 1]
    return partes[-1] if partes else ""


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn")


def sobrenome_completo(passageiros):
    """Tudo depois do primeiro nome do titular, maiusculo, sem acento e sem
    espaco - "Rui Machado de Lima" -> "MACHADODELIMA". E o que a TAP compara
    no link /my-bookings/details/<PNR>/<SOBRENOME> (testado em 16/10/2026:
    so o ultimo nome, "LIRA", da "reserva nao encontrada").
    """
    partes = _sem_acento(primeiro_passageiro(passageiros)).upper().split()
    return re.sub(r"[^A-Z]", "", "".join(partes[1:]))


# Prefixo do numero do voo -> cia, para trecho que chega do CRM sem a cia
# preenchida (ex.: EF34GH, "TP58", cia vazia). Prefixo de 3 letras antes do de 2.
PREFIXO_CIA = (("TAP", "TAP"), ("TAM", "LATAM"), ("LA", "LATAM"), ("JJ", "LATAM"),
               ("TP", "TAP"), ("G3", "GOL"), ("AD", "AZUL"), ("CM", "COPA"),
               ("QR", "QATAR AIRWAYS"), ("AF", "AIR FRANCE"))


def cia_pelo_voo(cia, numero_voo):
    """A cia do CRM; se vier vazia, deduz pelo prefixo do numero do voo."""
    if cia and cia.strip():
        return cia.strip()
    numero = (numero_voo or "").strip().upper()
    for prefixo, nome in PREFIXO_CIA:
        if numero.startswith(prefixo):
            return nome
    return cia


def _avaliar_localizador(loc, cia):
    """Devolve (utilizavel: bool, observacao: str ou None)."""
    if not loc:
        return False, "sem localizador"
    if loc.startswith("CRM-"):
        return False, "referencia interna do CRM, nao e PNR"
    if PNR.match(loc):
        return True, None
    if SO_NUMERO.match(loc):
        if cia in ACEITAM_NUMERO_BILHETE:
            return True, "numero de bilhete (o portal da %s aceita)" % cia
        return False, "numero de bilhete e a %s so aceita PNR" % (cia or "cia")
    return False, "localizador fora do padrao PNR (6 caracteres)"


def avaliar(voo):
    """Devolve (checavel: bool, problemas: list[str])."""
    cia = (voo.get("cia") or "").strip()
    exigidos = REQUISITOS.get(cia, REQUISITO_PADRAO)

    problemas = []
    faltando = False

    # a base mistura trecho aereo com terrestre (rodoviaria, trem)
    if not fusos.e_aeroporto(voo.get("origem")) or not fusos.e_aeroporto(voo.get("destino")):
        return False, ["trecho terrestre, nao e voo"]

    loc_ok, obs = _avaliar_localizador((voo.get("localizador") or "").strip().upper(), cia)
    if obs:
        problemas.append(obs)
    if not loc_ok:
        faltando = True

    if not cia:
        problemas.append("sem companhia aerea")
        faltando = True
    elif cia not in REQUISITOS:
        problemas.append("sem conector para %s (checagem manual)" % cia)
        faltando = True

    if "sobrenome" in exigidos and not sobrenome(voo.get("passageiros")):
        problemas.append("sem nome do passageiro (o portal exige o sobrenome)")
        faltando = True

    if "origem" in exigidos and not (voo.get("origem") or "").strip():
        problemas.append("sem aeroporto de origem (%s exige)" % cia)
        faltando = True

    if not voo.get("embarque"):
        problemas.append("sem data de embarque")
        faltando = True

    # Sem o fuso do aeroporto o horario sai errado e a comparacao com a
    # companhia acusaria alteracao que nao existe. Melhor barrar do que mentir.
    for aeroporto in (voo.get("origem"), voo.get("destino")):
        if aeroporto and not fusos.tem_fuso(aeroporto):
            problemas.append("fuso de %s nao mapeado (incluir em fusos.py)" % aeroporto)
            faltando = True

    if not (voo.get("numero_voo") or "").strip():
        # nao impede a consulta; atrapalha so a conferencia do trecho
        problemas.append("sem numero do voo (nao impede a checagem)")

    return (not faltando), problemas


def dias_para_voo(embarque):
    horas = fusos.horas_ate(embarque)
    return None if horas is None else int(horas // 24)


def prioridade(embarque):
    """Cadencia de checagem conforme a proximidade do embarque."""
    horas = fusos.horas_ate(embarque)
    if horas is None:
        return "indefinida"
    if horas < 0:
        return "passado"
    if horas <= 48:
        return "critica"      # a cada 6h
    if horas <= 24 * 7:
        return "alta"         # 2x ao dia
    if horas <= 24 * 30:
        return "media"        # 1x ao dia
    return "baixa"            # 1x por semana
