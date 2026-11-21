"""Teste rapido da coleta da revisao mensal da Luna (dados sinteticos). Uso: python3 testes/test_revisao_luna.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import revisao_luna as r


def msg(i, d, corpo, nota=False, t="2026-11-01T10:00:00.1+00:00"):
    return {"id": i, "conversation_id": "c1", "direction": d, "body": corpo, "is_internal_note": nota,
            "created_at": t, "media_type": None}


m = [msg(1, "in", "oi", t="2026-11-01T10:00:00.12+00:00"),
     msg(2, "out", "*Luna*\nOi!", t="2026-11-01T10:00:20+00:00"),
     msg(3, "in", "isso é um robô?", t="2026-11-01T10:05:00+00:00"),
     msg(4, "out", "🤖 Luna: transferi para um atendente. Motivo: cotação", True, "2026-11-01T10:06:00+00:00"),
     msg(5, "out", "🤖 Luna registrou na pré-qualificação: Datas, Trecho; adicionou a etiqueta \"X\".", True,
         "2026-11-01T10:07:00+00:00")]
met, por, luna = r.metricas([], m, [], [], [], "Luna")
assert luna == {"c1"} and met["primeira_resposta_luna_seg"]["mediana"]
assert abs(met["primeira_resposta_luna_seg"]["mediana"] - 19.88) < 0.01
assert met["campos_qualificacao_registrados"] == {"Datas": 1, "Trecho": 1}
assert list(met["motivos_de_transferencia"]) == ["cotação"]
assert "cliente_reclama_ou_pede_humano" in r.sinalizar(por["c1"])
print("ok")
