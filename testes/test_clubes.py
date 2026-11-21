"""Teste rapido do espelho de clubes (dados sinteticos). Uso: python3 testes/test_clubes.py"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import clubes_cloud as c


def conta(i, ativo=True, custo=356.8, dia=25):
    return c.linha_do_painel({"id": i, "name": "Ana", "program": "LATAM Pass", "club_active": ativo,
                              "club_monthly_cost": custo, "club_points_monthly": 10000,
                              "club_due_day": dia, "club_member_since": "2026-08-24T00:00:00"})


a, b = conta("1"), conta("2")
assert c.eventos_novos({}, [a, b]) == []  # 1a carga so grava a base
base = {"1": a, "2": b}
ev = c.eventos_novos(base, [conta("1", ativo=False), conta("2", custo=400), conta("3")])
assert [(e["conta_id"], e["tipo"]) for e in ev] == [("1", "desativou"), ("2", "custo"), ("3", "ativou")]
assert (ev[1]["de"], ev[1]["para"]) == ("356.8", "400")
assert c.eventos_novos(base, [a, b]) == []  # sem mudanca, sem evento
assert c.vence_em(31, datetime.date(2026, 11, 30)) and not c.vence_em(31, datetime.date(2026, 11, 29))
assert not c.vence_em(None, datetime.date(2026, 11, 30))
amanha = datetime.date(2026, 11, 25)
texto, v = c.aviso_de_vencimento([a, conta("9", dia=26)], amanha)
assert len(v) == 1 and "Ana" in texto and "356,80" in texto
a["avisado_venc"] = "2026-11-25"
assert c.aviso_de_vencimento([a], amanha) == (None, [])  # ja avisado
print("ok")
