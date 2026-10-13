"""Ranking admin top10 por ingresos brutos."""
from __future__ import annotations


def _gastos_mensuales(total_mes: int):
    return {m: {"agua": total_mes, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}


def test_gastos_por_calendario_reales_no_prorrateo(logged_in_flask_client, app_module):
    """Todos los gastos son de Paraíso: Villa y Santiago deben mostrar $0, no prorrateo."""
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"start": "2026-01-05", "end": "2026-01-07", "estado": "reservado", "precio": 600000, "extra_valor": 0,
         "calendario_id": "paraiso_los_quinquelles_1", "nombre_huesped": "A"},
        {"start": "2026-01-10", "end": "2026-01-12", "estado": "reservado", "precio": 300000, "extra_valor": 0,
         "calendario_id": "villa_futuro", "nombre_huesped": "B"},
    ]

    def gastos_por_filtro(year, calendario_ids=None):
        if calendario_ids is None:
            return _gastos_mensuales(90000)
        if "paraiso_los_quinquelles_1" in calendario_ids:
            return _gastos_mensuales(90000)
        return _gastos_mensuales(0)

    app_module.db_service.obtener_gastos_agregados_anio.side_effect = gastos_por_filtro
    r = logged_in_flask_client.get("/api/ranking?year=2026")
    assert r.status_code == 200
    por_cal = {c["calendario_id"]: c for c in r.get_json()["calendarios_top"]}
    assert por_cal["paraiso_los_quinquelles_1"]["gastos"] == 90000 * 12
    assert por_cal["villa_futuro"]["gastos"] == 0


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


def test_clientes_incluyen_reservas_con_fechas():
    from airbnb_agent.app import _ranking_anual
    gastos = {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    ev = [
        {"start": "2026-01-10", "end": "2026-01-12", "estado": "reservado", "precio": 100000, "extra_valor": 0,
         "calendario_id": "c1", "nombre_huesped": "Juan"},
        {"start": "2026-03-05", "end": "2026-03-07", "estado": "reservado", "precio": 200000, "extra_valor": 0,
         "calendario_id": "c1", "nombre_huesped": "Juan"},
    ]
    d = _ranking_anual(2026, ev, gastos)
    juan = next(c for c in d["clientes_top"] if c["cliente"] == "Juan")
    assert len(juan["reservas"]) == 2
    assert juan["reservas"][0] == {"inicio": "2026-01-10", "fin": "2026-01-12", "mes": "Enero", "calendario_id": "c1"}


def test_ranking_top15_clientes():
    from airbnb_agent.app import _ranking_anual
    gastos = {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    ev = [{"start": "2026-06-01", "end": "2026-06-02", "estado": "reservado", "precio": 10000 * (i + 1),
           "extra_valor": 0, "calendario_id": "c1", "nombre_huesped": f"Cli{i:02d}"} for i in range(16)]
    d = _ranking_anual(2026, ev, gastos)
    assert len(d["clientes_top"]) == 15
    assert d["clientes_top"][0]["cliente"] == "Cli15"


def test_ranking_filas_formato_colores():
    from pathlib import Path
    html = Path("airbnb_agent/templates/ranking.html").read_text(encoding="utf-8")
    assert "v-ing" in html and "v-gas" in html and "v-neto" in html
    assert "ranking-spinner" in html or "ranking-loading" in html
    assert "ranking-copa" in html and "copa-emoji" in html and "copa-num" in html
    assert "fecha-widget" in html and "fw-mes" in html and "fw-dias" in html
    assert "clientes-year" in html and "cal-logo" in html


def test_ranking_tiene_spinner_carga():
    from pathlib import Path
    html = Path("airbnb_agent/templates/ranking.html").read_text(encoding="utf-8").lower()
    assert "spinner" in html or ("loading" in html and "cargando" in html)


def test_total_mes_sin_link_y_copa_ranking_al_lado():
    from pathlib import Path
    html = Path("airbnb_agent/templates/calendar.html").read_text(encoding="utf-8")
    assert '<a href="/ranking"' not in html.split('id="widget-total-mes"')[0].split("income-widgets-sidebar")[-1] or \
        html.count('<a href="/ranking"') == 1
    # el widget Total del Mes no es link; el único link es la copa Ranking al lado
    assert 'id="widget-total-mes"' in html
    seg = html[html.find('id="widget-total-mes"')-500:html.find('id="widget-total-mes"')]
    assert '/ranking' not in seg
    assert '/ranking' in html and 'Ranking' in html and '🏆' in html
