"""Teste rapido do espelho do Turbo (dados sinteticos). Uso: python3 testes/test_turbo.py"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import turbo_cloud as t

hoje = datetime.date(2026, 11, 20)
contas = [
    {"id": "L1", "name": "Ana Souza ", "program": "LATAM Pass", "club_active": True, "balance": 1000,
     "cpf_used": 5, "cpf_limit": None, "club_monthly_cost": 356.8, "club_points_monthly": 10000,
     "club_due_day": 25},
    {"id": "V1", "name": "ANA SOUZA", "program": "Livelo", "balance": 120000, "cpm": 30.5, "club_active": True},
    {"id": "L2", "name": "Bia", "program": "LATAM Pass", "club_active": False},  # sem clube nem transf.: fora
    {"id": "S1", "name": "Ana Souza", "program": "Smiles"},
]
trans = [
    {"source_account_id": "V1", "destination_account_id": "L1", "transfer_date": "2026-10-03",
     "source_total_points": 100000, "destination_miles": 130000, "bonus_percentage": 30},
    {"source_account_id": "V1", "destination_account_id": "L1", "transfer_date": "2026-11-03",
     "source_total_points": 100000, "destination_miles": 130000, "bonus_percentage": 30},
    {"source_account_id": "V1", "destination_account_id": "L1", "transfer_date": "2026-11-04", "is_draft": True},
    {"source_account_id": "S1", "destination_account_id": "L1", "transfer_date": "2026-11-05"},  # nao e Livelo
]
emis = [
    {"miles_account_id": "L1", "emission_date": "2026-08-10",
     "passengers_data": {"flightGroups": [[{"name": "A"}, {"name": "B"}]]}},
    {"miles_account_id": "L1", "emission_date": "2026-08-10", "passengers_data": [{"name": "C"}]},
    {"miles_account_id": "L1", "emission_date": "2026-09-01", "passengers_data": [], "refund_status": "total"},
    {"miles_account_id": "L1", "emission_date": "2025-11-01", "passengers_data": [{"name": "D"}]},  # ja voltou
]
linhas = t.montar(contas, trans, emis, hoje)
assert [l["conta_id"] for l in linhas] == ["L1"]
l = linhas[0]
assert l["titular"] == "Ana Souza" and l["saldo_livelo"] == 120000 and l["livelo_conta_id"] == "V1"
assert l["cpf_limite"] == 25
assert [x["data"] for x in l["transferencias"]] == ["2026-11-03", "2026-10-03"]
assert l["liberacoes"] == [{"data": "2027-08-10", "qtd": 3}]
assert t._mais_um_ano("2028-02-29") == datetime.date(2029, 2, 28)

cs = [
    {"id": "L1", "name": "Ana ", "program": "LATAM Pass", "balance": 50000, "cpf_used": 5, "cpf_limit": None},
    {"id": "S1", "name": "Ana", "program": "Smiles", "balance": 0, "cpf_used": 3, "cpf_limit": 25},
    {"id": "S2", "name": "Bia", "program": "Smiles", "balance": 9000, "cpf_used": 0},
    {"id": "V1", "name": "Ana", "program": "Livelo", "balance": 1},
]
ce = {x["conta_id"]: x for x in t.montar_contas(cs, emis, hoje)}
assert set(ce) == {"L1", "S1", "S2"}  # so LATAM e Smiles, inclusive zeradas
assert ce["L1"]["cpf_limite"] == 25 and ce["L1"]["liberacoes"] == [{"data": "2027-08-10", "qtd": 3}]
assert ce["S1"]["liberacoes"] == [{"data": "2027-01-01", "qtd": 3}] and ce["S2"]["liberacoes"] == []
print("ok")
