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


def test_obtener_alias_map_devuelve_dict(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.alias_descripcion.find.return_value = [
        {"descripcion": "CENTRA TRANSFER DE JUAN", "alias": "Arriendo Juan", "categoria": "arriendo"},
        {"descripcion": "VIRT U PAGO RECIBIDO X", "alias": ""},
        {"descripcion": "OTRA", "alias": "Sueldo", "categoria": "invalida"},
    ]
    assert svc.obtener_alias_map() == {
        "CENTRA TRANSFER DE JUAN": {"alias": "Arriendo Juan", "categoria": "arriendo"},
        "OTRA": {"alias": "Sueldo", "categoria": ""},
    }


def test_guardar_alias_upsert_y_borrado(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.alias_descripcion.update_one.return_value = MagicMock(upserted_id=None)
    r = svc.guardar_alias("CENTRA TRANSFER DE JUAN", "Arriendo Juan", "arriendo")
    assert r == {"success": True, "descripcion": "CENTRA TRANSFER DE JUAN", "alias": "Arriendo Juan", "categoria": "arriendo"}
    assert svc.alias_descripcion.update_one.called
    args, _ = svc.alias_descripcion.update_one.call_args
    assert args[1]["$set"]["categoria"] == "arriendo"
    r_inv = svc.guardar_alias("A", "B", "no-existe")
    assert r_inv["categoria"] == ""
    svc.alias_descripcion.delete_one.return_value = MagicMock(deleted_count=1)
    r2 = svc.guardar_alias("CENTRA TRANSFER DE JUAN", "   ")
    assert r2["success"] is True and r2.get("deleted") is True


def test_obtener_transacciones_mes_incluye_alias(monkeypatch):
    svc = make_svc(monkeypatch)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.__iter__ = lambda self: iter([
        {
            "_id": "abc", "fecha": "05-03-2026", "descripcion": "CENTRA TRANSFER DE JUAN",
            "abono": 500000.0, "cargo": 0.0, "saldo": 100.0,
            "cartola_id": "c1", "fecha_creacion": "", "trx_key": "k1",
        },
        {
            "_id": "def", "fecha": "06-03-2026", "descripcion": "SIN ALIAS",
            "abono": 1000.0, "cargo": 0.0, "saldo": 0.0,
            "cartola_id": "c1", "fecha_creacion": "", "trx_key": "k2",
        },
    ])
    svc.transacciones_bci.find.return_value = cursor
    monkeypatch.setattr(svc, "obtener_alias_map", lambda: {
        "CENTRA TRANSFER DE JUAN": {"alias": "Arriendo Juan", "categoria": "arriendo"},
    })
    trxs = svc.obtener_transacciones_mes(2026, 3)
    assert trxs[0]["alias"] == "Arriendo Juan"
    assert trxs[0]["alias_categoria"] == "arriendo"
    assert trxs[0]["descripcion"] == "CENTRA TRANSFER DE JUAN"
    assert trxs[1]["alias"] == ""
    assert trxs[1]["alias_categoria"] == ""


def test_api_transacciones_alias_get_y_post(logged_in_flask_client, app_module):
    app_module.db_service.obtener_alias_map.return_value = {
        "A": {"alias": "Alias A", "categoria": "sueldo"},
    }
    r = logged_in_flask_client.get("/api/transacciones-alias")
    assert r.status_code == 200
    assert r.get_json() == {"aliases": {"A": {"alias": "Alias A", "categoria": "sueldo"}}}

    app_module.db_service.guardar_alias.return_value = {
        "success": True, "descripcion": "A", "alias": "Alias A", "categoria": "sueldo",
    }
    r2 = logged_in_flask_client.post(
        "/api/transacciones-alias",
        json={"descripcion": "A", "alias": "Alias A", "categoria": "sueldo"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["success"] is True
    called_args, _ = app_module.db_service.guardar_alias.call_args
    assert called_args == ("A", "Alias A", "sueldo")

    r3 = logged_in_flask_client.post("/api/transacciones-alias", json={"descripcion": "  ", "alias": "x"})
    assert r3.status_code == 400
