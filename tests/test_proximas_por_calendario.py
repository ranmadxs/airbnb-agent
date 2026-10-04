"""Tests para _ids_proximas_por_calendario (una PRÓXIMA ESTADÍA por propiedad).

Bug: el template usaba un solo flag global found_next, así que con dos
check-in el mismo día en distintas propiedades solo la primera salía como
próxima (ej. santiago_magno sí, paraiso_los_quinquelles_1 no).
"""
from __future__ import annotations

import pytest

from airbnb_agent.app import _ids_proximas_por_calendario


def ev(id, cid, start, estado="reservado", source="airbnb"):
    return {
        "id": id,
        "calendario_id": cid,
        "event_start": start,
        "start": start,
        "end": "2099-01-05",
        "estado": estado,
        "source": source,
    }


class TestProximasPorCalendario:
    def test_dos_checkin_mismo_dia_distinta_propiedad_ambas_proximas(self):
        events = [
            ev("a1", "paraiso_los_quinquelles_1", "2099-01-10"),
            ev("b1", "santiago_magno", "2099-01-10"),
        ]
        assert _ids_proximas_por_calendario(events, "2099-01-04") == {"a1", "b1"}

    def test_mismo_calendario_solo_la_primera(self):
        events = [
            ev("a1", "paraiso_los_quinquelles_1", "2099-01-10"),
            ev("a2", "paraiso_los_quinquelles_1", "2099-01-16"),
        ]
        assert _ids_proximas_por_calendario(events, "2099-01-04") == {"a1"}

    def test_ignora_pasadas_eliminadas_y_canceladas(self):
        events = [
            ev("past", "paraiso_los_quinquelles_1", "2099-01-01"),
            ev("del", "paraiso_los_quinquelles_1", "2099-01-10", estado="eliminado"),
            ev("can", "santiago_magno", "2099-01-10", estado="cancelado"),
            ev("ok", "santiago_magno", "2099-01-12"),
        ]
        assert _ids_proximas_por_calendario(events, "2099-01-04") == {"ok"}

    def test_sin_eventos_futuros_vacio(self):
        assert _ids_proximas_por_calendario([], "2099-01-04") == set()
