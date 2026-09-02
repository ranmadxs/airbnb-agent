"""Tests para helpers puros de airbnb_agent.app.

Cubre la lógica de cálculo de ingresos, parseo de query params,
firma de webhook de MercadoPago y el helper de calendario.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import date
from unittest.mock import MagicMock

import pytest

from airbnb_agent.app import (
    _calcular_ingresos_mes_reservas,
    _calcular_ingresos_por_calendario,
    _validar_firma_webhook_mp,
    get_month_calendar,
    get_month_calendar_tinaja,
)


# ============================================================
# _calcular_ingresos_mes_reservas
# ============================================================
class TestCalcularIngresosMesReservas:
    def test_reserva_dentro_del_mes(self):
        events = [
            {
                "estado": "reservado",
                "start": "2025-06-10",
                "end": "2025-06-15",
                "precio": 100_000,
                "extra_valor": 20_000,
            }
        ]
        arriendo, tinaja, pagado, proximos = _calcular_ingresos_mes_reservas(
            events, 2025, 6
        )
        assert arriendo == 100_000
        assert tinaja == 20_000
        # 5 noches en junio, todas pasadas → va a 'pagado'
        assert pagado == 120_000
        assert proximos == 0

    def test_reserva_atraviesa_meses_proporcion(self):
        # end es INCLUSIVO (día de checkout). Reserva del 28 jun al 8 jul
        # son 11 "noches" según esta lógica. En junio toca del 28 jun al 30 jun
        # = 3 días; en julio del 1 jul al 8 jul = 8 días; total 11.
        events = [
            {
                "estado": "reservado",
                "start": "2025-06-28",
                "end": "2025-07-08",
                "precio": 110_000,
                "extra_valor": 0,
            }
        ]
        arriendo_jun, _, _, _ = _calcular_ingresos_mes_reservas(events, 2025, 6)
        arriendo_jul, _, _, _ = _calcular_ingresos_mes_reservas(events, 2025, 7)
        assert arriendo_jun + arriendo_jul == 110_000
        # 3/11 y 8/11 redondeados
        assert arriendo_jun == 30_000
        assert arriendo_jul == 80_000

    def test_reserva_futura_no_se_cuenta_como_pagada(self):
        events = [
            {
                "estado": "reservado",
                "start": "2099-06-10",
                "end": "2099-06-15",
                "precio": 100_000,
                "extra_valor": 0,
            }
        ]
        _, _, pagado, proximos = _calcular_ingresos_mes_reservas(events, 2099, 6)
        assert pagado == 0
        assert proximos == 100_000

    def test_evento_no_reservado_se_ignora(self):
        events = [
            {"estado": "bloqueado", "start": "2025-06-10", "end": "2025-06-15", "precio": 50_000},
            {"estado": "eliminado", "start": "2025-06-10", "end": "2025-06-15", "precio": 50_000},
            {"estado": "cancelado", "start": "2025-06-10", "end": "2025-06-15", "precio": 50_000},
        ]
        arriendo, tinaja, _, _ = _calcular_ingresos_mes_reservas(events, 2025, 6)
        assert arriendo == 0
        assert tinaja == 0

    def test_eventos_sin_overlap_con_mes_se_ignoran(self):
        events = [
            {"estado": "reservado", "start": "2025-05-01", "end": "2025-05-03", "precio": 999},
            {"estado": "reservado", "start": "2025-07-01", "end": "2025-07-03", "precio": 999},
        ]
        arriendo, _, _, _ = _calcular_ingresos_mes_reservas(events, 2025, 6)
        assert arriendo == 0

    def test_eventos_mal_formados_se_ignoran_sin_explotar(self):
        events = [
            {"estado": "reservado", "start": "basura", "end": "mas-basura", "precio": 100},
            {"estado": "reservado", "precio": 100},  # sin start/end
            {"estado": "reservado", "start": "2025-06-10", "end": "2025-06-15", "precio": 50_000},
        ]
        arriendo, _, _, _ = _calcular_ingresos_mes_reservas(events, 2025, 6)
        # Solo el último cuenta
        assert arriendo == 50_000

    def test_diciembre_usa_anio_siguiente_para_fin_mes(self):
        events = [
            {
                "estado": "reservado",
                "start": "2025-12-30",
                "end": "2026-01-02",
                "precio": 100_000,
                "extra_valor": 0,
            }
        ]
        arriendo_dec, _, _, _ = _calcular_ingresos_mes_reservas(events, 2025, 12)
        arriendo_jan, _, _, _ = _calcular_ingresos_mes_reservas(events, 2026, 1)
        # 2 noches en dic, 2 en ene → 50/50
        assert arriendo_dec == 50_000
        assert arriendo_jan == 50_000


# ============================================================
# _calcular_ingresos_por_calendario
# ============================================================
class TestCalcularIngresosPorCalendario:
    def test_agrupa_por_calendario_id(self):
        events = [
            {"estado": "reservado", "start": "2025-06-10", "end": "2025-06-12",
             "precio": 60_000, "extra_valor": 10_000, "calendario_id": "santiago_magno"},
            {"estado": "reservado", "start": "2025-06-15", "end": "2025-06-17",
             "precio": 40_000, "extra_valor": 0, "calendario_id": "los_quinquelles"},
            {"estado": "reservado", "start": "2025-06-20", "end": "2025-06-22",
             "precio": 30_000, "extra_valor": 5_000, "calendario_id": None},  # legacy
        ]
        por_cal = _calcular_ingresos_por_calendario(events, 2025, 6)

        assert por_cal["santiago_magno"]["arriendo"] == 60_000
        assert por_cal["santiago_magno"]["tinaja"] == 10_000
        assert por_cal["santiago_magno"]["total"] == 70_000

        assert por_cal["los_quinquelles"]["arriendo"] == 40_000
        assert por_cal["los_quinquelles"]["total"] == 40_000

        assert por_cal["__legacy__"]["arriendo"] == 30_000
        assert por_cal["__legacy__"]["tinaja"] == 5_000

    def test_eventos_no_reservados_se_ignoran(self):
        events = [
            {"estado": "bloqueado", "start": "2025-06-10", "end": "2025-06-12",
             "precio": 60_000, "extra_valor": 10_000, "calendario_id": "x"},
        ]
        por_cal = _calcular_ingresos_por_calendario(events, 2025, 6)
        assert por_cal == {}


# ============================================================
# _parse_calendario_ids (helper usado por /api/month)
# ============================================================
class TestParseCalendarioIds:
    """Como _parse_calendario_ids() lee del request global de Flask,
    testeamos via endpoint /api/month para validar el flujo completo."""

    def test_sin_param_devuelve_todos(self, flask_client, monkeypatch):
        from airbnb_agent import app as _app
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(_app.db_service, "obtener_eventos_formato_ical", mock_fn)
        res = flask_client.get("/api/month?year=2025&month=6")
        assert res.status_code == 200
        # Sin filtro → argumento calendario_ids=None
        args, kwargs = mock_fn.call_args
        assert kwargs.get("calendario_ids") is None

    def test_con_csv_filtra(self, flask_client, monkeypatch):
        from airbnb_agent import app as _app
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(_app.db_service, "obtener_eventos_formato_ical", mock_fn)
        res = flask_client.get("/api/month?year=2025&month=6&calendario_ids=a,b,c")
        assert res.status_code == 200
        args, kwargs = mock_fn.call_args
        assert kwargs.get("calendario_ids") == ["a", "b", "c"]

    def test_legacy_en_csv_se_mantiene(self, flask_client, monkeypatch):
        from airbnb_agent import app as _app
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(_app.db_service, "obtener_eventos_formato_ical", mock_fn)
        res = flask_client.get("/api/month?year=2025&month=6&calendario_ids=a,__legacy__")
        assert res.status_code == 200
        args, kwargs = mock_fn.call_args
        assert kwargs.get("calendario_ids") == ["a", "__legacy__"]


# ============================================================
# get_month_calendar / get_month_calendar_tinaja
# ============================================================
class TestGetMonthCalendar:
    def test_estructura_basica_sin_eventos(self):
        result = get_month_calendar(2025, 6)
        assert result["year"] == 2025
        assert result["month"] == 6
        assert result["month_name"]
        # 30 días en junio + tuplas (0, weekday) para celdas vacías
        assert len(result["days"]) >= 35  # 6 filas aprox

    def test_incluir_eventos_devuelve_solo_del_mes(self, monkeypatch):
        """Verifica que get_month_calendar con include_events=True devuelve
        shape correcto (events, ingresos, ingresos_por_calendario)."""
        from airbnb_agent import app as _app
        monkeypatch.setattr(
            _app.db_service,
            "obtener_eventos_formato_ical",
            MagicMock(return_value=[]),
        )
        result = get_month_calendar(2025, 6, include_events=True)
        assert "events" in result
        assert "ingresos" in result
        assert result["events"] == []

    def test_diciembre_tiene_31_dias(self):
        result = get_month_calendar(2025, 12)
        dias_validos = [d for d, _ in result["days"] if d != 0]
        assert len(dias_validos) == 31


class TestGetMonthCalendarTinaja:
    def test_filtra_solo_reservas_con_tinaja(self, monkeypatch):
        from airbnb_agent import app as _app
        monkeypatch.setattr(
            _app.db_service,
            "obtener_eventos_formato_ical",
            MagicMock(return_value=[
                {"estado": "reservado", "start": "2025-06-10", "end": "2025-06-12",
                 "extra_valor": 19_500, "precio": 50_000},
                {"estado": "reservado", "start": "2025-06-15", "end": "2025-06-17",
                 "extra_valor": 0, "precio": 50_000},  # sin tinaja
                {"estado": "bloqueado", "start": "2025-06-20", "end": "2025-06-22",
                 "extra_valor": 999, "precio": 0},  # no es reserva
            ]),
        )
        result = get_month_calendar_tinaja(2025, 6, include_events=True)
        assert len(result["events"]) == 1
        assert result["events"][0]["extra_valor"] == 19_500

    def test_eventos_sin_tinaja_se_excluyen(self, monkeypatch):
        from airbnb_agent import app as _app
        monkeypatch.setattr(
            _app.db_service,
            "obtener_eventos_formato_ical",
            MagicMock(return_value=[
                {"estado": "reservado", "start": "2025-06-10", "end": "2025-06-12",
                 "extra_valor": 0, "precio": 50_000},
            ]),
        )
        result = get_month_calendar_tinaja(2025, 6, include_events=True)
        assert result["events"] == []


# ============================================================
# _validar_firma_webhook_mp
# ============================================================
class TestValidarFirmaWebhookMP:
    def _make_signature(self, payment_id, x_request_id, ts, secret):
        manifest = f"id:{payment_id};request-id:{x_request_id};ts:{ts};"
        return hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()

    def test_firma_valida(self):
        secret = "test-secret"
        ts = "1700000000"
        sig = self._make_signature("123", "req-abc", ts, secret)
        assert _validar_firma_webhook_mp("123", f"ts={ts},v1={sig}", "req-abc", secret) is True

    def test_firma_invalida(self):
        assert _validar_firma_webhook_mp("123", "ts=1,v1=deadbeef", "req-abc", "secret") is False

    def test_sin_secret_no_valida(self):
        # Sin secret configurado → no validar (passthrough)
        assert _validar_firma_webhook_mp("123", "cualquier-cosa", "req-abc", "") is True

    def test_firma_vacia_con_secret_es_rechazada(self):
        assert _validar_firma_webhook_mp("123", "", "req-abc", "secret") is False

    def test_firma_sin_ts_o_v1_es_rechazada(self):
        # Solo uno de los dos componentes
        assert _validar_firma_webhook_mp("123", "v1=abc", "req-abc", "secret") is False
        assert _validar_firma_webhook_mp("123", "ts=123", "req-abc", "secret") is False


# ============================================================
# Flask app sanity
# ============================================================
class TestFlaskApp:
    def test_app_se_inicializa(self, app_module):
        assert app_module.app is not None
        assert app_module.app.name == "airbnb_agent.app"

    def test_home_no_explota_con_eventos_vacios(self, app_module, flask_client, monkeypatch):
        monkeypatch.setattr(
            app_module.db_service,
            "obtener_eventos_formato_ical",
            MagicMock(return_value=[]),
        )
        monkeypatch.setattr(
            app_module.airbnb_service,
            "fetch_events",
            MagicMock(return_value=[]),
        )
        res = flask_client.get("/")
        assert res.status_code == 200
        assert b"Calendario" in res.data or b"calendar" in res.data.lower()

    def test_login_con_credenciales_correctas(self, app_module, flask_client):
        res = flask_client.post(
            "/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        assert res.status_code in (200, 302)


# ============================================================
# v3.0.1: Home() respeta ?cal=... (regression del bug de filtro)
# ============================================================
class TestHomeFilterByQueryParam:
    """Tests de regresión para el fix v3.0.1.

    Antes del fix, la ruta / ignoraba ?cal= y renderizaba con todos los
    eventos. Esto rompía deep links tipo /?cal=santiago_magno.
    """

    def test_home_sin_cal_no_pasa_filtro_a_db(self, app_module, flask_client, monkeypatch):
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(app_module.db_service, "obtener_eventos_formato_ical", mock_fn)
        monkeypatch.setattr(app_module.airbnb_service, "fetch_events", MagicMock(return_value=[]))
        monkeypatch.setattr(app_module.airbnb_service, "get_stats", MagicMock(return_value={}))
        res = flask_client.get("/")
        assert res.status_code == 200
        # Sin ?cal= → calendario_ids debe ser None (todos los eventos)
        args, kwargs = mock_fn.call_args
        assert kwargs.get("calendario_ids") is None

    def test_home_con_cal_pasa_ids_validos_a_db(self, app_module, flask_client, monkeypatch):
        # Configurar 2 calendarios para validar el filtro
        app_module.airbnb_service.calendars = [
            {"calendario_id": "santiago_magno", "nombre": "Santiago Magno", "source": "airbnb", "url": "x"},
            {"calendario_id": "los_quinquelles", "nombre": "Los Quinquelles", "source": "airbnb", "url": "x"},
        ]
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(app_module.db_service, "obtener_eventos_formato_ical", mock_fn)
        monkeypatch.setattr(app_module.airbnb_service, "fetch_events", MagicMock(return_value=[]))
        monkeypatch.setattr(app_module.airbnb_service, "get_stats", MagicMock(return_value={}))

        res = flask_client.get("/?cal=santiago_magno")
        assert res.status_code == 200
        args, kwargs = mock_fn.call_args
        assert kwargs.get("calendario_ids") == ["santiago_magno"]

    def test_home_con_cal_csv_incluye_legacy(self, app_module, flask_client, monkeypatch):
        app_module.airbnb_service.calendars = [
            {"calendario_id": "santiago_magno", "nombre": "Santiago Magno", "source": "airbnb", "url": "x"},
        ]
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(app_module.db_service, "obtener_eventos_formato_ical", mock_fn)
        monkeypatch.setattr(app_module.airbnb_service, "fetch_events", MagicMock(return_value=[]))
        monkeypatch.setattr(app_module.airbnb_service, "get_stats", MagicMock(return_value={}))

        res = flask_client.get("/?cal=santiago_magno,__legacy__")
        assert res.status_code == 200
        args, kwargs = mock_fn.call_args
        # __legacy__ debe mantenerse en la lista para que la query Mongo lo maneje
        assert "santiago_magno" in kwargs["calendario_ids"]
        assert "__legacy__" in kwargs["calendario_ids"]

    def test_home_con_cal_invalido_se_ignora(self, app_module, flask_client, monkeypatch):
        app_module.airbnb_service.calendars = [
            {"calendario_id": "santiago_magno", "nombre": "Santiago Magno", "source": "airbnb", "url": "x"},
        ]
        mock_fn = MagicMock(return_value=[])
        monkeypatch.setattr(app_module.db_service, "obtener_eventos_formato_ical", mock_fn)
        monkeypatch.setattr(app_module.airbnb_service, "fetch_events", MagicMock(return_value=[]))
        monkeypatch.setattr(app_module.airbnb_service, "get_stats", MagicMock(return_value={}))

        res = flask_client.get("/?cal=hack_injection")
        assert res.status_code == 200
        args, kwargs = mock_fn.call_args
        # IDs inválidos se filtran → calendario_ids queda como lista vacía
        assert kwargs.get("calendario_ids") == []

    def test_home_filtra_ical_fallback_con_cal(self, app_module, flask_client, monkeypatch):
        """Cuando Mongo está vacío y se hace fallback a iCal, el filtro ?cal= debe
        seguir aplicándose a la lista en memoria."""
        app_module.airbnb_service.calendars = [
            {"calendario_id": "santiago_magno", "nombre": "Santiago Magno", "source": "airbnb", "url": "x"},
            {"calendario_id": "los_quinquelles", "nombre": "Los Quinquelles", "source": "airbnb", "url": "x"},
        ]
        # Mongo vacío
        monkeypatch.setattr(
            app_module.db_service,
            "obtener_eventos_formato_ical",
            MagicMock(return_value=[]),
        )
        # Pero iCal devuelve eventos de los 2 calendarios
        ical_events = [
            {"id": "1", "start": "2025-06-10", "end": "2025-06-12", "estado": "reservado",
             "calendario_id": "santiago_magno", "precio": 50_000, "extra_valor": 0},
            {"id": "2", "start": "2025-06-15", "end": "2025-06-17", "estado": "reservado",
             "calendario_id": "los_quinquelles", "precio": 60_000, "extra_valor": 0},
        ]
        monkeypatch.setattr(app_module.airbnb_service, "fetch_events", MagicMock(return_value=ical_events))
        monkeypatch.setattr(app_module.airbnb_service, "get_stats", MagicMock(return_value={}))

        # Pedir solo santiago_magno
        res = flask_client.get("/?cal=santiago_magno")
        assert res.status_code == 200
        # En el HTML renderizado debe aparecer "Santiago" (sí) y NO aparecer Quinqueños
        html = res.data.decode("utf-8")
        # Renderizamos por calendario_id (no por nombre humano); el filtro
        # elimina Quinqueños del array events que va al template.
        assert '"calendario_id": "santiago_magno"' in html
        assert '"calendario_id": "los_quinquelles"' not in html


# ============================================================
# /api/calendarios — expone los campos imagen/thumbnail/logo
# ============================================================
class TestApiCalendarios:
    """Cobertura del endpoint /api/calendarios para la feature ui de
    thumbnail + logo por arriendo (PR #4)."""

    def test_devuelve_imagen_thumbnail_y_logo_por_calendario(
        self, app_module, flask_client, monkeypatch
    ):
        app_module.airbnb_service.calendars = [
            {
                "calendario_id": "paraiso_los_quinquelles_1",
                "nombre": "Paraiso Los Quinquelles 1",
                "source": "airbnb",
                "url": "https://a.ics",
                "imagen": "images/los-quinquelles.png",
                "thumbnail": "images/los-quinquelles.png",
                "logo": "images/los-quinquelles-logo.png",
            },
            {
                "calendario_id": "santiago_magno",
                "nombre": "Santiago Magno",
                "source": "airbnb",
                "url": "https://b.ics",
                "imagen": "images/santiago-magno.png",
                "thumbnail": "images/santiago-magno.png",
                "logo": "images/santiago-magno-logo.png",
            },
        ]
        # Mock get_status para evitar acceso a per_cal_status
        monkeypatch.setattr(
            app_module.airbnb_service,
            "get_status",
            MagicMock(return_value={"global": {}, "per_calendar": {}}),
        )
        # Mock db_service.connect (no debería entrar si no hay legacy,
        # pero por las dudas evitamos cualquier acceso de red)
        monkeypatch.setattr(
            app_module.db_service,
            "connect",
            MagicMock(return_value=False),
        )

        res = flask_client.get("/api/calendarios")
        assert res.status_code == 200
        body = res.get_json()

        assert "configured" in body
        assert len(body["configured"]) == 2

        c0 = body["configured"][0]
        assert c0["calendario_id"] == "paraiso_los_quinquelles_1"
        assert c0["imagen"] == "images/los-quinquelles.png"
        assert c0["thumbnail"] == "images/los-quinquelles.png"
        assert c0["logo"] == "images/los-quinquelles-logo.png"

        c1 = body["configured"][1]
        assert c1["calendario_id"] == "santiago_magno"
        assert c1["imagen"] == "images/santiago-magno.png"
        assert c1["thumbnail"] == "images/santiago-magno.png"
        assert c1["logo"] == "images/santiago-magno-logo.png"

    def test_campos_imagen_vacios_cuando_calendario_no_tiene(self,
                                                              app_module,
                                                              flask_client,
                                                              monkeypatch):
        # Calendarios sin campo 'imagen' deben devolver string vacío,
        # no romper la API ni faltar la clave.
        app_module.airbnb_service.calendars = [
            {
                "calendario_id": "legacy",
                "nombre": "Legacy",
                "source": "airbnb",
                "url": "https://a.ics",
            },
        ]
        monkeypatch.setattr(
            app_module.airbnb_service,
            "get_status",
            MagicMock(return_value={"global": {}, "per_calendar": {}}),
        )
        monkeypatch.setattr(
            app_module.db_service,
            "connect",
            MagicMock(return_value=False),
        )

        res = flask_client.get("/api/calendarios")
        assert res.status_code == 200
        c0 = res.get_json()["configured"][0]
        assert c0["imagen"] == ""
        assert c0["thumbnail"] == ""
        assert c0["logo"] == ""