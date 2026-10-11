"""Tests para gastos por calendario (v3.7.0).

TDD RED: estos tests deben FALLAR antes de implementar calendario_id en gastos.
Cubre:
- guardar_* persiste calendario_id
- obtener_* retorna calendario_id (+ proveedor_id donde faltaba)
- obtener_gastos_mes / agregados filtran por calendario_ids
- actualizar_gasto permite reasignar calendario (editar)
- seed incluye Comunidad Edificio Santiago Magno y Tur Bus
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from airbnb_agent.services.database import DatabaseService


def make_db_service():
    svc = DatabaseService.__new__(DatabaseService)
    svc.uri = ""
    svc.client = None
    svc.db = None
    svc.db_bci = None
    svc.reservas = None
    svc.dias = None
    svc.connected = False
    svc.ultima_sync = None
    svc.sync_interval = 300
    return svc


def _patch_gastos(svc, monkeypatch, coll_name, docs):
    """Mockea connect() + colección de gastos con find/insert/update."""
    monkeypatch.setattr(svc, "connect", lambda: True)
    svc.db = MagicMock()
    coll = MagicMock()

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.__iter__ = lambda self: iter(docs)
    coll.find.return_value = cursor
    svc.db.__getitem__.return_value = coll
    setattr(svc.db, coll_name, coll)
    return coll


class TestGuardarGastoConCalendario:
    def test_guardar_agua_persiste_calendario_id(self, monkeypatch):
        svc = make_db_service()
        coll = _patch_gastos(svc, monkeypatch, "gastos_agua", [])
        inserted = MagicMock()
        inserted.inserted_id = "abc"
        coll.insert_one.return_value = inserted

        res = svc.guardar_gasto_agua({
            "razon": "Consumo",
            "nombre": "Aguas",
            "tipo": "consumo",
            "fecha_pago": "2026-10-01",
            "valor": 15000,
            "descripcion": "",
            "whatsapp": "",
            "pagado": True,
            "proveedor_id": "",
            "calendario_id": "paraiso_los_quinquelles_1",
        })
        assert res["success"] is True
        doc = coll.insert_one.call_args[0][0]
        assert doc["calendario_id"] == "paraiso_los_quinquelles_1"

    def test_guardar_otros_persiste_calendario_id(self, monkeypatch):
        svc = make_db_service()
        coll = _patch_gastos(svc, monkeypatch, "gastos_otros", [])
        inserted = MagicMock()
        inserted.inserted_id = "xyz"
        coll.insert_one.return_value = inserted

        res = svc.guardar_gasto_otros({
            "razon": "Gasto común",
            "nombre": "Comunidad Edificio Santiago Magno",
            "tipo": "gasto_comun",
            "fecha_pago": "2026-10-01",
            "valor": 50000,
            "descripcion": "",
            "whatsapp": "",
            "pagado": True,
            "proveedor_id": "",
            "calendario_id": "santiago_magno",
        })
        assert res["success"] is True
        doc = coll.insert_one.call_args[0][0]
        assert doc["calendario_id"] == "santiago_magno"


class TestObtenerGastoConCalendario:
    def test_obtener_agua_retorna_calendario_id(self, monkeypatch):
        svc = make_db_service()
        docs = [{
            "_id": "a1",
            "razon": "Consumo",
            "nombre": "Aguas",
            "tipo": "consumo",
            "fecha_pago": "2026-10-05",
            "fecha_creacion": "2026-10-05",
            "valor": 15000,
            "descripcion": "",
            "whatsapp": "",
            "pagado": True,
            "proveedor_id": "p1",
            "calendario_id": "paraiso_los_quinquelles_1",
        }]
        _patch_gastos(svc, monkeypatch, "gastos_agua", docs)
        gastos = svc.obtener_gastos_agua(2026, 10)
        assert len(gastos) == 1
        assert gastos[0]["calendario_id"] == "paraiso_los_quinquelles_1"
        assert gastos[0]["proveedor_id"] == "p1"


class TestObtenerGastosMesFiltroCalendario:
    def test_filtra_por_calendario_ids(self, monkeypatch):
        svc = make_db_service()
        monkeypatch.setattr(svc, "connect", lambda: True)

        llamadas = {}

        def fake_obtener(year, month, calendario_ids=None):
            llamadas["calendario_ids"] = calendario_ids
            return []

        monkeypatch.setattr(svc, "obtener_gastos_agua", lambda y, m, calendario_ids=None: (llamadas.update({"agua": calendario_ids}) or []))
        monkeypatch.setattr(svc, "obtener_gastos_internet", lambda y, m, calendario_ids=None: [])
        monkeypatch.setattr(svc, "obtener_gastos_gasolina", lambda y, m, calendario_ids=None: [])
        monkeypatch.setattr(svc, "obtener_gastos_aseo", lambda y, m, calendario_ids=None: [])
        monkeypatch.setattr(svc, "obtener_gastos_otros", lambda y, m, calendario_ids=None: [])
        monkeypatch.setattr(svc, "obtener_gastos_electricidad", lambda y, m, calendario_ids=None: [])
        # evitar error de firma si la implementación aún no acepta el kwarg
        try:
            svc.obtener_gastos_mes(2026, 10, calendario_ids=["paraiso_los_quinquelles_1"])
        except TypeError:
            raise AssertionError("obtener_gastos_mes debe aceptar calendario_ids")
        assert llamadas.get("agua") == ["paraiso_los_quinquelles_1"]


class TestActualizarGasto:
    def test_actualizar_calendario_id(self, monkeypatch):
        svc = make_db_service()
        monkeypatch.setattr(svc, "connect", lambda: True)
        svc.db = MagicMock()
        coll = MagicMock()
        svc.db.__getitem__.return_value = coll
        coll.update_one.return_value = MagicMock(matched_count=1, modified_count=1)
        try:
            res = svc.actualizar_gasto("gastos_agua", "64f000000000000000000001", {"calendario_id": "santiago_magno", "valor": 20000})
        except AttributeError:
            raise AssertionError("DatabaseService debe exponer actualizar_gasto(coleccion, gasto_id, datos)")
        assert res["success"] is True
        set_doc = coll.update_one.call_args[0][1]["$set"]
        assert set_doc["calendario_id"] == "santiago_magno"
        assert set_doc["valor"] == 20000


class TestSeedProveedoresGastos:
    def test_seed_incluye_comunidad_y_turbus(self, monkeypatch):
        svc = make_db_service()
        monkeypatch.setattr(svc, "connect", lambda: True)
        svc.db = MagicMock()
        proveedores = MagicMock()
        svc.db.proveedores = proveedores
        # find_one -> None (no existen, deben crearse)
        proveedores.find_one.return_value = None
        try:
            svc.seed_proveedores_gastos()
        except AttributeError:
            raise AssertionError("DatabaseService debe exponer seed_proveedores_gastos()")
        insertados = [c[0][0].get("nombre") for c in proveedores.insert_one.call_args_list]
        assert "Comunidad Edificio Santiago Magno" in insertados
        assert "Tur Bus" in insertados


# ============================================================
# API: POST acepta calendario_id + PUT edita
# ============================================================
class TestApiGastosCalendario:
    def _calendarios(self, app_module):
        app_module.airbnb_service.calendars = [
            {"calendario_id": "paraiso_los_quinquelles_1", "nombre": "Paraíso"},
            {"calendario_id": "santiago_magno", "nombre": "Santiago"},
        ]
        app_module.db_service.listar_calendarios.return_value = []

    def test_post_agua_envia_calendario_id(self, logged_in_flask_client, app_module):
        self._calendarios(app_module)
        app_module.db_service.guardar_gasto_agua.return_value = {"success": True, "id": "x"}
        res = logged_in_flask_client.post("/api/gastos/agua", json={
            "razon": "Test", "valor": 1000, "fecha_pago": "2026-10-01",
            "calendario_id": "santiago_magno",
        })
        assert res.status_code == 200
        gasto = app_module.db_service.guardar_gasto_agua.call_args[0][0]
        assert gasto["calendario_id"] == "santiago_magno"

    def test_post_agua_calendario_invalido_se_sanitiza(self, logged_in_flask_client, app_module):
        self._calendarios(app_module)
        app_module.db_service.guardar_gasto_agua.return_value = {"success": True, "id": "x"}
        res = logged_in_flask_client.post("/api/gastos/agua", json={
            "razon": "Test", "valor": 1000, "fecha_pago": "2026-10-01",
            "calendario_id": "no_existe",
        })
        assert res.status_code == 200
        gasto = app_module.db_service.guardar_gasto_agua.call_args[0][0]
        assert gasto["calendario_id"] == ""

    def test_put_agua_actualiza_calendario(self, logged_in_flask_client, app_module):
        self._calendarios(app_module)
        app_module.db_service.actualizar_gasto.return_value = {"success": True}
        res = logged_in_flask_client.put("/api/gastos/agua/64f000000000000000000001", json={
            "calendario_id": "santiago_magno", "valor": 2000,
        })
        assert res.status_code == 200
        args = app_module.db_service.actualizar_gasto.call_args[0]
        assert args[0] == "gastos_agua"
        assert args[2]["calendario_id"] == "santiago_magno"

    def test_alias_transporte_get(self, logged_in_flask_client, app_module):
        app_module.db_service.obtener_gastos_gasolina.return_value = []
        res = logged_in_flask_client.get("/api/gastos/transporte?year=2026&month=10")
        assert res.status_code == 200
        assert "gastos" in res.get_json()
