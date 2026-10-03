"""Pagos de arriendo con alias -> eventos de calendario (solo categoria arriendo, solo admin).

TDD RED: estas funciones no existen aun.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from airbnb_agent.services.database import DatabaseService


def make_svc(monkeypatch):
    svc = DatabaseService.__new__(DatabaseService)
    svc.uri = ""
    svc.client = None
    svc.db = None
    svc.db_bci = MagicMock()
    svc.transacciones_bci = MagicMock()
    svc.alias_descripcion = MagicMock()
    svc.connected = False
    svc.ultima_sync = None
    svc.sync_interval = 300
    monkeypatch.setattr(svc, "connect", lambda: True)
    return svc


def test_alias_map_incluye_calendario_id(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.alias_descripcion.find.return_value = [
        {"descripcion": "TRANSF ARRIENDO X", "alias": "Arriendo X",
         "categoria": "arriendo", "calendario_id": "casa_costa"},
    ]
    assert svc.obtener_alias_map() == {
        "TRANSF ARRIENDO X": {"alias": "Arriendo X", "categoria": "arriendo",
                              "calendario_id": "casa_costa"},
    }


def test_guardar_alias_con_calendario_id(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.alias_descripcion.update_one.return_value = MagicMock(upserted_id=None)
    r = svc.guardar_alias("TRANSF ARRIENDO X", "Arriendo X", "arriendo", "casa_costa")
    assert r["calendario_id"] == "casa_costa"
    args, _ = svc.alias_descripcion.update_one.call_args
    assert args[1]["$set"]["calendario_id"] == "casa_costa"


def test_pagos_arriendo_mes_solo_categoria_arriendo(monkeypatch):
    svc = make_svc(monkeypatch)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.__iter__ = lambda self: iter([
        {"_id": "a1", "fecha": "05-03-2026", "descripcion": "TRANSF ARRIENDO X",
         "abono": 500000.0, "cargo": 0.0, "trx_key": "k-arriendo"},
        {"_id": "s1", "fecha": "06-03-2026", "descripcion": "SUELDO Y",
         "abono": 900000.0, "cargo": 0.0, "trx_key": "k-sueldo"},
        {"_id": "n1", "fecha": "07-03-2026", "descripcion": "SIN ALIAS",
         "abono": 100000.0, "cargo": 0.0, "trx_key": "k-sin-alias"},
        {"_id": "t1", "fecha": "08-03-2026", "descripcion": "TRANSF OTRA",
         "abono": 50000.0, "cargo": 0.0, "trx_key": "k-transfer"},
    ])
    svc.transacciones_bci.find.return_value = cursor
    monkeypatch.setattr(svc, "obtener_alias_map", lambda: {
        "TRANSF ARRIENDO X": {"alias": "Arriendo X", "categoria": "arriendo",
                              "calendario_id": "casa_costa"},
        "SUELDO Y": {"alias": "Mi Sueldo", "categoria": "sueldo", "calendario_id": ""},
        "TRANSF OTRA": {"alias": "Otra", "categoria": "transferencia", "calendario_id": ""},
    })
    pagos = svc.obtener_pagos_arriendo_mes(2026, 3)
    assert len(pagos) == 1
    p = pagos[0]
    assert p["start"] == "2026-03-05" and p["end"] == "2026-03-05"
    assert p["source"] == "arriendo"
    assert p["estado"] == "reservado"
    assert p["precio"] == 500000
    assert p["calendario_id"] == "casa_costa"
    assert p["tipo"] == "pago_arriendo"
    assert p["readonly"] is True


def test_pagos_arriendo_mes_excluye_sin_calendario_y_sin_abono(monkeypatch):
    svc = make_svc(monkeypatch)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.__iter__ = lambda self: iter([
        {"_id": "a2", "fecha": "09-03-2026", "descripcion": "ARRIENDO SIN CAL",
         "abono": 300000.0, "cargo": 0.0, "trx_key": "k-nocal"},
        {"_id": "a3", "fecha": "10-03-2026", "descripcion": "ARRIENDO CERO",
         "abono": 0.0, "cargo": 0.0, "trx_key": "k-cero"},
    ])
    svc.transacciones_bci.find.return_value = cursor
    monkeypatch.setattr(svc, "obtener_alias_map", lambda: {
        "ARRIENDO SIN CAL": {"alias": "Arriendo NC", "categoria": "arriendo",
                             "calendario_id": ""},
        "ARRIENDO CERO": {"alias": "Arriendo 0", "categoria": "arriendo",
                          "calendario_id": "casa_costa"},
    })
    pagos = svc.obtener_pagos_arriendo_mes(2026, 3)
    assert pagos == []


def test_api_month_fusiona_pagos_solo_admin(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"id": "r1", "start": "2026-03-10", "end": "2026-03-12",
         "estado": "reservado", "precio": 100000, "extra_valor": 0,
         "calendario_id": "casa_costa", "source": "airbnb"},
    ]
    app_module.db_service.obtener_pagos_arriendo_mes.return_value = [
        {"id": "arriendo-k1", "start": "2026-03-05", "end": "2026-03-05",
         "estado": "reservado", "precio": 500000, "extra_valor": 0,
         "calendario_id": "casa_costa", "source": "arriendo",
         "tipo": "pago_arriendo", "summary": "Pago arriendo Arriendo X"},
    ]
    r = logged_in_flask_client.get("/api/month?year=2026&month=3")
    assert r.status_code == 200
    data = r.get_json()
    starts = {e["start"] for e in data["events"]}
    assert "2026-03-05" in starts and "2026-03-10" in starts
    assert data["ingresos"]["arriendo"] >= 500000


def test_api_month_no_fusiona_pagos_anonimo(flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"id": "r1", "start": "2026-03-10", "end": "2026-03-12",
         "estado": "reservado", "precio": 100000, "extra_valor": 0,
         "calendario_id": "casa_costa", "source": "airbnb"},
    ]
    r = flask_client.get("/api/month?year=2026&month=3")
    assert r.status_code == 200
    data = r.get_json()
    assert all(e.get("source") != "arriendo" for e in data["events"])
    assert not app_module.db_service.obtener_pagos_arriendo_mes.called
