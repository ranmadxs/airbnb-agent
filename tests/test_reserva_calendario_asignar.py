"""Primera asignación de calendario en edición.

Bug: una reserva legacy sin calendario_id no permite asignarle uno:
el modal deja el select readonly Y guardar_reserva_manual ignora
calendario_id al editar. Debe permitirse SOLO la primera asignación
(con calendario ya seteado, se preserva).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from airbnb_agent.services.database import DatabaseService

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def make_svc():
    svc = DatabaseService.__new__(DatabaseService)
    svc.uri = ""
    svc.client = None
    svc.db = None
    svc.db_bci = None
    svc.reservas = MagicMock()
    svc.dias = MagicMock()
    svc.connected = False
    svc.ultima_sync = None
    svc.sync_interval = 300
    svc.connect = lambda: True
    svc._actualizar_dias_reserva = lambda *a, **k: None
    return svc


def datos(cid):
    return {
        "event_start": "2026-02-19",
        "event_end": "2026-02-20",
        "estado": "reservado",
        "calendario_id": cid,
    }


RID = "69af819aaaff6e9ebf937972"


class TestPrimeraAsignacionCalendario:
    def test_edicion_sin_calendario_permite_asignar(self):
        svc = make_svc()
        svc.reservas.find_one.return_value = {"_id": RID, "calendario_id": None}
        svc.reservas.update_one.return_value = MagicMock(
            modified_count=1, matched_count=1
        )
        res = svc.guardar_reserva_manual(RID, datos("santiago_magno"), audit=None)
        assert res["success"] is True
        set_doc = svc.reservas.update_one.call_args[0][1]["$set"]
        assert set_doc.get("calendario_id") == "santiago_magno"

    def test_edicion_con_calendario_no_lo_cambia(self):
        svc = make_svc()
        svc.reservas.find_one.return_value = {
            "_id": RID,
            "calendario_id": "paraiso_los_quinquelles_1",
        }
        svc.reservas.update_one.return_value = MagicMock(
            modified_count=1, matched_count=1
        )
        res = svc.guardar_reserva_manual(RID, datos("santiago_magno"), audit=None)
        assert res["success"] is True
        set_doc = svc.reservas.update_one.call_args[0][1]["$set"]
        assert "calendario_id" not in set_doc

    def test_creacion_setea_calendario(self):
        svc = make_svc()
        inserted = {}

        def fake_insert(doc):
            inserted.update(doc)
            return MagicMock(inserted_id="abc")

        svc.reservas.insert_one.side_effect = fake_insert
        res = svc.guardar_reserva_manual("", datos("santiago_magno"), audit=None)
        assert res["success"] is True
        assert inserted.get("calendario_id") == "santiago_magno"
