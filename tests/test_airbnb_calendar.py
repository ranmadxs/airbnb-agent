"""Tests para CalendarService: parseo de URLs y slugify.

Cubre los helpers _slugify y _parse_value que son la base del
multi-calendario (v3.0.0+).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from airbnb_agent.services.airbnb_calendar import CalendarService, _slugify


# ============================================================
# _slugify
# ============================================================
class TestSlugify:
    def test_texto_basico(self):
        assert _slugify("Posada del Bosque") == "posada_del_bosque"

    def test_acentos_se_normalizan(self):
        # NFKD + ascii ignore: 'ñ' → 'n', 'ó' → 'o'
        assert _slugify("Santiago Magnó") == "santiago_magno"
        assert _slugify("Paraíso Los Quinqueños") == "paraiso_los_quinquenos"

    def test_espacios_y_signos_se_convierten_a_underscore(self):
        assert _slugify("Los-Quinquelles #1") == "los_quinquelles_1"

    def test_string_vacio_devuelve_vacio(self):
        assert _slugify("") == ""

    def test_none_devuelve_vacio(self):
        assert _slugify(None) == ""

    def test_solo_caracteres_especiales_cae_a_unnamed(self):
        assert _slugify("###") == "unnamed"

    def test_minusculas_se_mantienen(self):
        assert _slugify("UPPERCASE") == "uppercase"

    def test_numeros_se_mantienen(self):
        assert _slugify("Cabaña 42") == "cabana_42"


# ============================================================
# CalendarService._parse_value
# ============================================================
class TestParseValue:
    @pytest.fixture
    def service(self):
        # No instanciar __init__ real (intenta leer .env); instanciar manualmente
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = []
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {"global": {}, "per_calendar": {}}
        return svc

    def test_url_simple_se_interpreta_como_default(self, service):
        items = service._parse_value("https://airbnb.com/calendar.ics", "airbnb")
        assert items == [{"nombre": "default", "source": "airbnb", "url": "https://airbnb.com/calendar.ics"}]

    def test_json_valido_con_multiples_calendarios(self, service):
        raw = '[{"nombre":"Santiago Magno","source":"airbnb","url":"https://a.com/1.ics"},' \
              '{"nombre":"Los Quinqueños","url":"https://b.com/2.ics"}]'
        items = service._parse_value(raw, "airbnb")
        assert len(items) == 2
        assert items[0]["nombre"] == "Santiago Magno"
        assert items[0]["source"] == "airbnb"
        # _parse_value NO rellena source cuando falta — eso lo hace _load_calendars
        assert "source" not in items[1]

    def test_json_invalido_devuelve_vacio(self, service, capsys):
        items = service._parse_value("[malformed json", "airbnb")
        assert items == []
        # Y loguea warning
        captured = capsys.readouterr()
        assert "JSON inválido" in captured.out

    def test_json_que_no_es_lista_devuelve_vacio(self, service):
        items = service._parse_value('{"nombre":"x","url":"y"}', "airbnb")
        assert items == []

    def test_string_vacio_devuelve_vacio(self, service):
        assert service._parse_value("", "airbnb") == []
        assert service._parse_value("   ", "airbnb") == []

    def test_formato_no_reconocido_devuelve_vacio(self, service):
        assert service._parse_value("ftp://algo", "airbnb") == []

    def test_comillas_externas_se_eliminan(self, service):
        items = service._parse_value('"https://airbnb.com/cal.ics"', "airbnb")
        assert len(items) == 1
        assert items[0]["url"] == "https://airbnb.com/cal.ics"


# ============================================================
# CalendarService._load_calendars (con env vars mockeadas)
# ============================================================
class TestLoadCalendars:
    @pytest.fixture
    def service(self):
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = []
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {"global": {}, "per_calendar": {}}
        return svc

    def test_sin_env_devuelve_lista_vacia(self, service, monkeypatch):
        monkeypatch.delenv("AIRBNB_CALENDAR_URL", raising=False)
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        assert service._load_calendars() == []

    def test_nombres_duplicados_agregan_sufijo(self, service, monkeypatch):
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"Cabaña","url":"https://a.ics"},'
                           '{"nombre":"Cabaña","url":"https://b.ics"}]')
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        cals = service._load_calendars()
        assert len(cals) == 2
        ids = [c["calendario_id"] for c in cals]
        assert ids[0] == "cabana"
        assert ids[1] == "cabana_2"

    def test_mezcla_airbnb_y_booking(self, service, monkeypatch):
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"X","url":"https://a.ics"}]')
        monkeypatch.setenv("BOOKING_CALENDAR_URL",
                           '[{"nombre":"Y","url":"https://b.ics"}]')
        cals = service._load_calendars()
        assert len(cals) == 2
        sources = {c["source"] for c in cals}
        assert sources == {"airbnb", "booking"}

    def test_item_sin_url_se_omite(self, service, monkeypatch, capsys):
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"SinUrl"},'
                           '{"nombre":"ConUrl","url":"https://a.ics"}]')
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        cals = service._load_calendars()
        assert len(cals) == 1
        assert cals[0]["nombre"] == "ConUrl"
        assert "sin url, omitido" in capsys.readouterr().out

    # ---- Cobertura feature ui thumbnail/logo ----

    def test_imagen_unica_deriva_thumbnail_y_logo(self, service, monkeypatch):
        # Si solo viene "imagen", thumbnail reusa el base y logo se deriva con sufijo.
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"Paraiso Los Quinquelles 1",'
                           '"source":"airbnb",'
                           '"url":"https://a.ics",'
                           '"imagen":"images/los-quinquelles.png"}]')
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        cals = service._load_calendars()
        assert len(cals) == 1
        c = cals[0]
        assert c["imagen"] == "images/los-quinquelles.png"
        assert c["thumbnail"] == "images/los-quinquelles.png"          # reusa el base
        assert c["logo"] == "images/los-quinquelles-logo.png"          # derivado

    def test_imagen_sin_extension_logo_asume_png(self, service, monkeypatch):
        # Si imagen viene sin extensión, el código asume .png para el logo
        # derivado (convención del proyecto: todos los assets son PNG).
        # thumbnail reusa el base tal cual (sin extensión).
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"Casa",'
                           '"url":"https://a.ics",'
                           '"imagen":"images/casa"}]')
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        cals = service._load_calendars()
        c = cals[0]
        assert c["imagen"] == "images/casa"
        assert c["thumbnail"] == "images/casa"
        assert c["logo"] == "images/casa-logo.png"

    def test_thumbnail_y_logo_explicitos_respetan_valores(self, service, monkeypatch):
        # Si vienen explícitos, NO se derivan del campo imagen.
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"A",'
                           '"url":"https://a.ics",'
                           '"imagen":"images/a.png",'
                           '"thumbnail":"static/a-mini.png",'
                           '"logo":"static/a-circle.svg"}]')
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        cals = service._load_calendars()
        c = cals[0]
        assert c["thumbnail"] == "static/a-mini.png"
        assert c["logo"] == "static/a-circle.svg"

    def test_sin_imagen_queda_todo_vacio(self, service, monkeypatch):
        # Sin 'imagen', 'thumbnail' ni 'logo', los campos quedan vacíos
        # (la UI cae a emoji genérico).
        monkeypatch.setenv("AIRBNB_CALENDAR_URL",
                           '[{"nombre":"Legacy",'
                           '"url":"https://a.ics"}]')
        monkeypatch.delenv("BOOKING_CALENDAR_URL", raising=False)
        cals = service._load_calendars()
        c = cals[0]
        assert c["imagen"] == ""
        assert c["thumbnail"] == ""
        assert c["logo"] == ""


# ============================================================
# CalendarService.get_stats
# ============================================================
class TestGetStats:
    @pytest.fixture
    def service(self):
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = []
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {"global": {}, "per_calendar": {}}
        return svc

    def test_sin_eventos_devuelve_cero(self, service):
        stats = service.get_stats([])
        assert stats["total_reservations"] == 0
        assert stats["upcoming_reservations"] == 0
        assert stats["reserved_days_30"] == 0
        assert stats["ocupacion_30"] == 0

    def test_solo_cuenta_reservas_no_bloqueos(self, service):
        eventos = [
            {"estado": "reservado", "start": "2099-01-01", "end": "2099-01-03"},
            {"estado": "bloqueado", "start": "2099-01-05", "end": "2099-01-07"},
            {"estado": "cancelado", "start": "2099-01-10", "end": "2099-01-12"},
        ]
        stats = service.get_stats(eventos)
        # Solo cuenta reservado
        assert stats["total_reservations"] == 1
        assert stats["upcoming_reservations"] == 1

    def test_ocupacion_en_ventana_30_dias(self, service):
        from datetime import datetime, timedelta
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        en_15 = (hoy + timedelta(days=15)).strftime("%Y-%m-%d")
        en_20 = (hoy + timedelta(days=20)).strftime("%Y-%m-%d")
        eventos = [
            {"estado": "reservado", "start": en_15, "end": en_20},  # 5 días dentro
        ]
        stats = service.get_stats(eventos)
        assert stats["reserved_days_30"] == 5
        assert stats["ocupacion_30"] == round(5 / 30 * 100)


# ============================================================
# CalendarService.get_status
# ============================================================
class TestGetStatus:
    @pytest.fixture
    def service(self):
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = [{"calendario_id": "a", "nombre": "A", "source": "airbnb", "url": "u"}]
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {
            "global": {
                "connected": True,
                "last_check": "2025-01-01T00:00:00",
                "events_count": 5,
                "calendars_count": 1,
            },
            "per_calendar": {"a": {"connected": True}},
        }
        return svc

    def test_devuelve_status_cacheado(self, service):
        # get_status() simplemente devuelve self.status (snapshot)
        status = service.get_status()
        assert status["global"]["connected"] is True
        assert status["global"]["events_count"] == 5
        assert status["per_calendar"] == {"a": {"connected": True}}