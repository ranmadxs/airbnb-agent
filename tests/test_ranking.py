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


def test_api_ranking_global_todos_los_anios(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"start": "2025-01-05", "end": "2025-01-06", "estado": "reservado", "precio": 900000, "extra_valor": 0, "calendario_id": "casa_costa"},
        {"start": "2026-05-10", "end": "2026-05-11", "estado": "reservado", "precio": 100000, "extra_valor": 0, "calendario_id": "depto_centro"},
    ]
    def gastos(year):
        return {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    app_module.db_service.obtener_gastos_agregados_anio.side_effect = gastos
    r = logged_in_flask_client.get("/api/ranking-global")
    assert r.status_code == 200
    assert r.get_json()["meses_top"][0]["anio"] == 2025


def test_pagina_ranking_solo_admin(logged_in_flask_client, flask_client):
    assert logged_in_flask_client.get("/ranking").status_code == 200
    r = flask_client.get("/ranking", follow_redirects=False)
    assert r.status_code in (302, 401)
    assert "/login" in r.headers.get("Location", "") or r.status_code == 401


def test_ranking_css_copas_existe():
    from pathlib import Path
    css = Path("airbnb_agent/static/css/style.css").read_text(encoding="utf-8")
    assert ".copa-oro" in css and ".copa-plata" in css and ".copa-bronce" in css


def test_ranking_prorrateo_corte_mes():
    from airbnb_agent.app import _ranking_anual
    gastos = {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    ev = [{"start": "2026-01-31", "end": "2026-02-01", "estado": "reservado", "precio": 100000, "extra_valor": 0, "calendario_id": "c1", "nombre_huesped": "X"}]
    d = _ranking_anual(2026, ev, gastos)
    por_mes = {m["mes"]: m["ingresos"] for m in d["meses_top"]}
    assert por_mes.get(1) == 50000 and por_mes.get(2) == 50000


def test_ranking_legacy_y_huesped():
    from airbnb_agent.app import _ranking_anual
    gastos = {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    ev = [{"start": "2026-03-05", "end": "2026-03-06", "estado": "reservado", "precio": 200000, "extra_valor": 0}]
    d = _ranking_anual(2026, ev, gastos)
    assert any(c["calendario_id"] == "__legacy__" for c in d["calendarios_top"])
    assert any(c["cliente"] == "Huésped" for c in d["clientes_top"])


def test_clientes_excluye_pagos_arriendo():
    from airbnb_agent.app import _ranking_anual
    gastos = {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    ev = [{"start": "2026-04-01", "end": "2026-04-01", "estado": "reservado", "precio": 400000, "extra_valor": 0,
           "calendario_id": "c1", "source": "arriendo", "tipo": "pago_arriendo", "summary": "Pago arriendo X"}]
    d = _ranking_anual(2026, ev, gastos)
    assert all("Pago arriendo" not in c["cliente"] for c in d["clientes_top"])
    assert sum(m["ingresos"] for m in d["meses_top"]) == 400000


def test_api_ranking_year_invalido_no_500(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = []
    app_module.db_service.obtener_gastos_agregados_anio.return_value = {m: {"agua": 0} for m in range(1, 13)}
    for bad in ("0", "-1", "10000"):
        r = logged_in_flask_client.get(f"/api/ranking?year={bad}")
        assert r.status_code in (400, 200)
        assert r.status_code != 500


def test_api_ranking_global_requiere_login(flask_client, app_module):
    assert flask_client.get("/api/ranking-global").status_code == 401


def test_ranking_html_escapa_nombres():
    from pathlib import Path
    html = Path("airbnb_agent/templates/ranking.html").read_text(encoding="utf-8")
    assert "function esc(" in html or "escapeHtml" in html
