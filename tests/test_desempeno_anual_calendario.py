"""Desglose anual de Arriendo por calendario (/api/desempeno -> Resumen Anual).

TDD RED: `arriendo_por_calendario` no existe en la respuesta mensual.
"""
from __future__ import annotations


def _gastos_cero():
    base = {'agua': 0, 'internet': 0, 'gasolina': 0, 'aseo': 0, 'otros': 0,
            'electricidad': 0, 'pagado': 0, 'proximos': 0}
    return {m: dict(base) for m in range(1, 13)}


def test_por_calendario_suma_al_arriendo_del_mes():
    from airbnb_agent.app import (
        _calcular_ingresos_mes_reservas,
        _calcular_ingresos_por_calendario,
    )
    eventos = [
        {"start": "2026-03-10", "end": "2026-03-12", "estado": "reservado",
         "precio": 300000, "extra_valor": 0, "calendario_id": "casa_costa"},
        {"start": "2026-03-20", "end": "2026-03-22", "estado": "reservado",
         "precio": 150000, "extra_valor": 0, "calendario_id": "casa_cordillera"},
        {"start": "2026-03-05", "end": "2026-03-05", "estado": "reservado",
         "precio": 500000, "extra_valor": 0, "calendario_id": "casa_costa",
         "source": "arriendo", "tipo": "pago_arriendo"},
        {"start": "2026-03-25", "end": "2026-03-26", "estado": "reservado",
         "precio": 60000, "extra_valor": 0},  # sin calendario -> __legacy__
    ]
    arriendo, _, _, _ = _calcular_ingresos_mes_reservas(eventos, 2026, 3)
    por_cal = _calcular_ingresos_por_calendario(eventos, 2026, 3)
    assert sum(v["arriendo"] for v in por_cal.values()) == arriendo
    assert por_cal["casa_costa"]["arriendo"] == 800000
    assert por_cal["casa_cordillera"]["arriendo"] == 150000
    assert por_cal["__legacy__"]["arriendo"] == 60000


def test_api_desempeno_incluye_arriendo_por_calendario(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"id": "r1", "start": "2026-03-10", "end": "2026-03-12",
         "estado": "reservado", "precio": 300000, "extra_valor": 0,
         "calendario_id": "casa_costa", "source": "airbnb"},
        {"id": "r2", "start": "2026-03-20", "end": "2026-03-22",
         "estado": "reservado", "precio": 150000, "extra_valor": 0,
         "calendario_id": "casa_cordillera", "source": "airbnb"},
    ]
    app_module.db_service.obtener_pagos_arriendo_mes.return_value = []
    app_module.db_service.obtener_gastos_agregados_anio.return_value = _gastos_cero()
    r = logged_in_flask_client.get("/api/desempeno?year=2026")
    assert r.status_code == 200
    meses = {m["mes"]: m for m in r.get_json()["meses"]}
    marzo = meses[3]
    assert marzo["arriendo"] == 450000
    apc = marzo["arriendo_por_calendario"]
    assert apc["casa_costa"]["arriendo"] == 300000
    assert apc["casa_cordillera"]["arriendo"] == 150000
    assert sum(v["arriendo"] for v in apc.values()) == marzo["arriendo"]
    assert meses[4].get("arriendo_por_calendario", {}) == {}
