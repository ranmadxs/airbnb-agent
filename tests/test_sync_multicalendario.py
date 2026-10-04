"""Reproduce bug HMK33ZWYJ9: santiago 10→14 se pierde si paraiso 10→12 esta protegida.

TDD RED: este test debe FALLAR antes del fix (santiago omitida por overlap
global) y PASAR despues (overlap scopeado por calendario_id).

Caso real 2026-10:
- DB protegida: admin paraiso_los_quinquelles_1 10→12 readonly=True (no tocar)
- iCal trae: paraiso 10→12 (misma, debe seguir bloqueada) +
             santiago_magno 10→14 HMK33ZWYJ9 (nueva, debe insertarse)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from airbnb_agent.services.database import DatabaseService

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def make_svc():
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


def future(days_from_now: int) -> str:
    return (datetime.now() + timedelta(days=days_from_now)).strftime("%Y-%m-%d")


def setup_mocks(svc, protected_docs):
    """Mockea Mongo para guardar_eventos y captura los UpdateOne de eventos."""
    svc.connect = lambda: True

    svc.reservas = MagicMock()
    svc.dias = MagicMock()

    # update_many cache marking
    svc.reservas.update_many.return_value = MagicMock(modified_count=0)
    svc.dias.update_many.return_value = MagicMock(modified_count=0)

    # dias protegidos: ninguno
    dias_cursor = MagicMock()
    dias_cursor.__iter__ = lambda self: iter([])
    svc.dias.find.return_value = dias_cursor
    svc.dias.bulk_write.return_value = MagicMock()
    svc.dias.delete_many.return_value = MagicMock()

    # find_one: no existe nada previo
    svc.reservas.find_one.return_value = None

    # find: protegidas vs stale (por filtro)
    def find_side_effect(filter_doc=None, *args, **kwargs):
        # protegidas: {"readonly": True}
        if filter_doc and filter_doc.get("readonly") is True:
            cur = MagicMock()
            cur.__iter__ = lambda self: iter(protected_docs)
            return cur
        # stale cache: lista vacia
        cur = MagicMock()
        cur.__iter__ = lambda self: iter([])
        return cur

    svc.reservas.find.side_effect = find_side_effect
    svc.reservas.delete_many.return_value = MagicMock()

    captured = {}

    def fake_bulk_write(ops, *args, **kwargs):
        captured["ops"] = list(ops)
        res = MagicMock()
        res.upserted_count = len(captured["ops"])
        res.modified_count = 0
        return res

    svc.reservas.bulk_write.side_effect = fake_bulk_write
    return captured


def ical_event(calendario_id, start, end, codigo):
    return {
        "start": start,
        "end": end,
        "days": 2,
        "summary": "Reserved",
        "reservation_url": f"https://www.airbnb.com/hosting/reservations/details/{codigo}",
        "codigo_reserva": codigo,
        "source": "airbnb",
        "calendario_id": calendario_id,
    }


def filtros_de_ops(ops):
    return [op._filter for op in ops]


class TestSyncMulticalendarioMismoDia:
    def test_santiago_no_se_pierde_si_solapa_protegida_otro_calendario(self):
        base = future(10)
        fin_paraiso = future(12)
        fin_santiago = future(14)

        svc = make_svc()
        protegidas = [
            {
                "event_start": base,
                "event_end": fin_paraiso,
                "calendario_id": "paraiso_los_quinquelles_1",
            }
        ]
        captured = setup_mocks(svc, protegidas)

        eventos = [
            ical_event("paraiso_los_quinquelles_1", base, fin_paraiso, "HMPYPZTKA3"),
            ical_event("santiago_magno", base, fin_santiago, "HMK33ZWYJ9"),
        ]
        svc.guardar_eventos(eventos, audit={"user_origin": "system", "user_agent": "system"})

        ops = captured.get("ops", [])
        filtros = filtros_de_ops(ops)
        # La nueva de santiago debe intentarse insertar aunque solape con
        # la protegida de paraiso (distinto calendario_id).
        assert any(
            f.get("calendario_id") == "santiago_magno"
            and f.get("event_start") == base
            and f.get("event_end") == fin_santiago
            for f in filtros
        ), f"santiago {base}->{fin_santiago} fue omitida. filtros={filtros}"

    def test_mismo_rango_distinto_calendario_no_colisiona(self):
        base = future(20)
        fin = future(22)

        svc = make_svc()
        captured = setup_mocks(svc, [])

        eventos = [
            ical_event("paraiso_los_quinquelles_1", base, fin, "AAA"),
            ical_event("santiago_magno", base, fin, "BBB"),
        ]
        svc.guardar_eventos(eventos, audit={"user_origin": "system", "user_agent": "system"})

        ops = captured.get("ops", [])
        filtros = filtros_de_ops(ops)
        cids = sorted([f.get("calendario_id") for f in filtros])
        assert cids == ["paraiso_los_quinquelles_1", "santiago_magno"], (
            f"mismo rango en 2 propiedades debe guardar 2 ops, filtros={filtros}"
        )

    def test_protegida_mismo_calendario_si_bloquea(self):
        # No romper proteccion dentro de la misma propiedad (paraiso no se toca).
        base = future(30)
        fin = future(32)

        svc = make_svc()
        protegidas = [
            {"event_start": base, "event_end": fin, "calendario_id": "paraiso_los_quinquelles_1"}
        ]
        captured = setup_mocks(svc, protegidas)

        eventos = [ical_event("paraiso_los_quinquelles_1", base, fin, "HMPYPZTKA3")]
        svc.guardar_eventos(eventos, audit={"user_origin": "system", "user_agent": "system"})

        ops = captured.get("ops", [])
        assert ops == [], f"protegida mismo calendario debe seguir omitida, ops={filtros_de_ops(ops)}"
