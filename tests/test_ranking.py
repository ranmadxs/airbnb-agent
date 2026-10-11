"""Ranking admin top10 por ingresos brutos."""
from __future__ import annotations


def test_api_ranking_anual_top10_por_ingresos_brutos(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"start": "2026-01-05", "end": "2026-01-07", "estado": "reservado", "precio": 300000, "extra_valor": 50000, "calendario_id": "casa_costa", "nombre_huesped": "Juan"},
        {"start": "2026-05-10", "end": "2026-05-12", "estado": "reservado", "precio": 500000, "extra_valor": 0, "calendario_id": "depto_centro", "nombre_huesped": "Ana"},
    ]
    app_module.db_service.obtener_gastos_agregados_anio.return_value = {m: {"agua": 10000, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    r = logged_in_flask_client.get("/api/ranking?year=2026")
    assert r.status_code == 200
    j = r.get_json()
    assert j["meses_top"][0]["mes"] == 5
    assert j["meses_top"][0]["ingresos"] == 500000
    assert j["clientes_top"][0]["ingresos"] == 500000


def test_api_ranking_requiere_login(flask_client, app_module):
    r = flask_client.get("/api/ranking?year=2026")
    assert r.status_code == 401


def test_ranking_anual_vacio_y_legacy():
    from airbnb_agent.app import _ranking_anual
    vacio = _ranking_anual(2026, [], {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)})
    assert vacio["meses_top"] == [] and vacio["calendarios_top"] == [] and vacio["clientes_top"] == []
