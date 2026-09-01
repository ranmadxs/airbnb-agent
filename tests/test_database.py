"""Tests para DatabaseService con Mongo mockeado.

Cubre la lógica de query (especialmente el filtro por calendario_id y
legacy introducido en v3.0.0). Mongo se mockea completamente: no se
requiere conexión real.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from airbnb_agent.services.database import DatabaseService


def make_db_service():
    """Crea un DatabaseService sin intentar conectar a Mongo."""
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


def make_mock_cursor(docs):
    """Mock de cursor pymongo: soporta .sort()."""
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.__iter__ = lambda self: iter(docs)
    return cursor


# ============================================================
# obtener_eventos_formato_ical — filtro por calendario
# ============================================================
class TestObtenerEventosFormatoIcal:
    def _doc(self, **overrides):
        base = {
            "_id": "abc123",
            "event_start": "2025-06-10",
            "event_end": "2025-06-12",
            "days": 2,
            "summary": "Reserva Test",
            "reservation_url": "https://airbnb.com/r/123",
            "codigo_reserva": "RES123",
            "source": "airbnb",
            "calendario_id": "santiago_magno",
            "estado": "reservado",
            "readonly": False,
            "checkout": False,
            "hora_checkin": "15:00",
            "hora_checkout": "18:00",
            "nombre_huesped": "Juan",
            "adultos": 2,
            "ninos": 0,
            "mascotas": 0,
            "notas": "",
            "precio": 100_000,
            "extra_concepto": "Tinaja",
            "extra_valor": 0,
            "extra_pago_confirmado": False,
            "comuna": "",
            "pais": "",
        }
        base.update(overrides)
        return base

    def _patch_connect(self, monkeypatch, docs):
        svc = make_db_service()
        # Mock connect() para que devuelva True y arme collections
        cursor = make_mock_cursor(docs)

        monkeypatch.setattr(svc, "connect", lambda: True)
        svc.reservas = MagicMock()
        svc.reservas.find.return_value = cursor
        return svc, cursor

    def test_sin_filtro_query_excluye_eliminados_y_cache(self, monkeypatch):
        # El filtro Mongo real lo aplica el server. En el mock solo podemos
        # verificar que la query enviada tiene los operadores correctos.
        docs = []
        svc, cursor = self._patch_connect(monkeypatch, docs)
        svc.obtener_eventos_formato_ical()
        query = svc.reservas.find.call_args[0][0]
        assert query["estado"] == {"$ne": "eliminado"}
        assert query["source"] == {"$not": {"$regex": "^cache_"}}
        # Sin filtro de calendario
        assert "calendario_id" not in query
        assert "$or" not in query

    def test_calendario_ids_none_es_sin_filtro(self, monkeypatch):
        svc, cursor = self._patch_connect(monkeypatch, [])
        svc.obtener_eventos_formato_ical(calendario_ids=None)
        query = svc.reservas.find.call_args[0][0]
        # Sin filtro de calendario
        assert "calendario_id" not in query
        assert "$or" not in query

    def test_calendario_ids_lista_vacia_devuelve_vacio(self, monkeypatch):
        svc, _ = self._patch_connect(monkeypatch, [])
        result = svc.obtener_eventos_formato_ical(calendario_ids=[])
        assert result == []
        # No se debe llamar a find() si el filtro es vacío
        svc.reservas.find.assert_not_called()

    def test_calendario_ids_filtra_por_in(self, monkeypatch):
        svc, cursor = self._patch_connect(monkeypatch, [])
        svc.obtener_eventos_formato_ical(calendario_ids=["santiago_magno", "los_quinquelles"])
        query = svc.reservas.find.call_args[0][0]
        assert query["calendario_id"] == {"$in": ["santiago_magno", "los_quinquelles"]}

    def test_legacy_en_lista_incluye_docs_sin_calendario_id(self, monkeypatch):
        svc, cursor = self._patch_connect(monkeypatch, [])
        svc.obtener_eventos_formato_ical(calendario_ids=["santiago_magno", "__legacy__"])
        query = svc.reservas.find.call_args[0][0]
        # Debe usar $or para incluir el legacy (sin calendario_id)
        assert "$or" in query
        or_clauses = query["$or"]
        assert {"calendario_id": {"$in": ["santiago_magno"]}} in or_clauses
        assert {"calendario_id": None} in or_clauses
        assert {"calendario_id": {"$exists": False}} in or_clauses

    def test_solo_legacy_no_filtra_por_calendario_id(self, monkeypatch):
        svc, cursor = self._patch_connect(monkeypatch, [])
        svc.obtener_eventos_formato_ical(calendario_ids=["__legacy__"])
        query = svc.reservas.find.call_args[0][0]
        # Solo legacy → no aplica filtro de calendario
        assert "calendario_id" not in query
        assert "$or" not in query

    def test_connect_falla_devuelve_lista_vacia(self, monkeypatch):
        svc = make_db_service()
        monkeypatch.setattr(svc, "connect", lambda: False)
        result = svc.obtener_eventos_formato_ical()
        assert result == []

    def test_evento_se_serializa_correctamente(self, monkeypatch):
        docs = [self._doc(
            _id="abc123",
            event_start="2025-06-10",
            event_end="2025-06-12",
            precio=100_000,
            calendario_id="santiago_magno",
            estado="reservado",
        )]
        svc, cursor = self._patch_connect(monkeypatch, docs)
        result = svc.obtener_eventos_formato_ical()
        assert len(result) == 1
        ev = result[0]
        assert ev["id"] == "abc123"
        assert ev["start"] == "2025-06-10"
        assert ev["end"] == "2025-06-12"
        assert ev["calendario_id"] == "santiago_magno"
        assert ev["precio"] == 100_000


# ============================================================
# obtener_eventos (sin filtro de calendario)
# ============================================================
class TestObtenerEventos:
    def test_connect_falla_devuelve_lista_vacia(self, monkeypatch):
        svc = make_db_service()
        monkeypatch.setattr(svc, "connect", lambda: False)
        assert svc.obtener_eventos() == []

    def test_devuelve_eventos_ordenados_por_start(self, monkeypatch):
        svc = make_db_service()
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.__iter__ = lambda self: iter([
            {"_id": "1", "event_start": "2025-06-10", "event_end": "2025-06-12", "summary": "x"},
            {"_id": "2", "event_start": "2025-07-01", "event_end": "2025-07-03", "summary": "y"},
        ])
        monkeypatch.setattr(svc, "connect", lambda: True)
        svc.reservas = MagicMock()
        svc.reservas.find.return_value = cursor

        result = svc.obtener_eventos()
        assert len(result) == 2
        # Verifica que se haya ordenado por event_start
        cursor.sort.assert_called_with("event_start", 1)


# ============================================================
# connect / get_status (sin red)
# ============================================================
class TestConnect:
    def test_sin_uri_devuelve_false(self):
        svc = make_db_service()
        assert svc.uri == ""
        assert svc.connect() is False

    def test_get_status_sin_uri(self):
        svc = make_db_service()
        status = svc.get_status()
        assert status["connected"] is False
        assert status["configured"] is False

    def test_get_status_con_uri_pero_sin_conexion(self):
        # URI configurada pero connect() falla → get_status devuelve connected False
        svc = make_db_service()
        svc.uri = "mongodb://invalid-host-12345:27017"
        # connect() fallará (no hay red hacia ese host)
        # No queremos esperar timeout largo; cortamos con connect=False directo
        svc.connect = lambda: False
        status = svc.get_status()
        assert status["configured"] is True
        assert status["connected"] is False


# ============================================================
# necesita_sync
# ============================================================
class TestNecesitaSync:
    def test_sin_ultima_sync_devuelve_true(self):
        svc = make_db_service()
        svc.ultima_sync = None
        assert svc.necesita_sync() is True

    def test_sync_reciente_devuelve_false(self):
        svc = make_db_service()
        svc.ultima_sync = datetime.now()
        assert svc.necesita_sync() is False

    def test_sync_viejo_devuelve_true(self):
        from datetime import timedelta
        svc = make_db_service()
        svc.ultima_sync = datetime.now() - timedelta(seconds=400)
        svc.sync_interval = 300
        assert svc.necesita_sync() is True