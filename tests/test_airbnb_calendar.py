"""Tests para CalendarService: parseo de URLs y slugify.

Cubre los helpers _slugify y _parse_value que son la base del
multi-calendario (v3.0.0+).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


# ============================================================
# CalendarService.fetch_events
# ============================================================
class TestFetchEvents:
    """Cobertura de fetch_events: sincroniza todos los calendarios y
    clasifica el resultado en status global + per_calendar."""

    @pytest.fixture
    def service(self):
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = []
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {"global": {}, "per_calendar": {}}
        return svc

    def test_sin_calendarios_devuelve_none_y_status_error(
        self, service
    ):
        result = service.fetch_events()
        assert result is None
        assert service.status["global"]["connected"] is False
        assert service.status["global"]["error"] == "No hay calendarios configurados"
        assert service.status["global"]["calendars_count"] == 0
        assert service.status["per_calendar"] == {}

    def test_todos_los_calendarios_fallan_devuelve_none(
        self, service, monkeypatch
    ):
        service.calendars = [
            {"calendario_id": "a", "nombre": "A", "source": "airbnb", "url": "u1"},
            {"calendario_id": "b", "nombre": "B", "source": "airbnb", "url": "u2"},
        ]
        monkeypatch.setattr(service, "_fetch_one", lambda cfg: None)

        result = service.fetch_events()
        assert result is None
        assert service.status["global"]["connected"] is False
        assert service.status["global"]["error"] == "all_calendars_failed"
        # per_calendar: ambos como failed
        assert service.status["per_calendar"]["a"]["connected"] is False
        assert service.status["per_calendar"]["a"]["error"] == "fetch_failed"
        assert service.status["per_calendar"]["b"]["connected"] is False

    def test_exito_total_devuelve_eventos_y_status_ok(
        self, service, monkeypatch
    ):
        service.calendars = [
            {"calendario_id": "a", "nombre": "A", "source": "airbnb", "url": "u1"},
            {"calendario_id": "b", "nombre": "B", "source": "airbnb", "url": "u2"},
        ]
        # _fetch_one devuelve eventos distintos por calendario
        def fake_fetch(cfg):
            return [
                {"start": "2099-06-15", "end": "2099-06-17",
                 "source": cfg["source"], "calendario_id": cfg["calendario_id"]},
            ]
        monkeypatch.setattr(service, "_fetch_one", fake_fetch)

        result = service.fetch_events()
        assert result is not None
        assert len(result) == 2
        # Status global: connected=True con contadores correctos
        assert service.status["global"]["connected"] is True
        assert service.status["global"]["events_count"] == 2
        assert service.status["global"]["successful_calendars"] == 2
        assert service.status["global"]["failed_calendars"] == 0
        # Eventos ordenados por start
        assert result[0]["calendario_id"] == "a"
        assert result[1]["calendario_id"] == "b"
        # cached_events actualizado
        assert service.cached_events == result
        assert service.last_fetch is not None

    def test_fallo_parcial_devuelve_eventos_de_los_que_funcionan(
        self, service, monkeypatch
    ):
        service.calendars = [
            {"calendario_id": "ok", "nombre": "OK", "source": "airbnb", "url": "u1"},
            {"calendario_id": "fail", "nombre": "FAIL", "source": "airbnb", "url": "u2"},
        ]
        def fake_fetch(cfg):
            if cfg["calendario_id"] == "ok":
                return [{"start": "2099-06-10", "end": "2099-06-12",
                         "calendario_id": "ok", "source": "airbnb"}]
            return None
        monkeypatch.setattr(service, "_fetch_one", fake_fetch)

        result = service.fetch_events()
        # Al menos uno trajo eventos → devuelve lista, no None
        assert result is not None
        assert len(result) == 1
        assert result[0]["calendario_id"] == "ok"
        # Status refleja mixto
        assert service.status["global"]["connected"] is True
        assert service.status["global"]["successful_calendars"] == 1
        assert service.status["global"]["failed_calendars"] == 1
        assert service.status["per_calendar"]["fail"]["connected"] is False


# ============================================================
# CalendarService._parse_event
# ============================================================
class TestParseEvent:
    """Cobertura del parseo de VEVENTs: taggea source + calendario_id,
    extrae reservation_url y codigo_reserva del description."""

    @pytest.fixture
    def service(self):
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = []
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {"global": {}, "per_calendar": {}}
        return svc

    @pytest.fixture
    def cal_cfg(self):
        return {
            "calendario_id": "paraiso_los_quinquelles_1",
            "nombre": "Paraiso Los Quinquelles 1",
            "source": "airbnb",
            "url": "https://a.ics",
        }

    @staticmethod
    def _make_dt(year, month, day):
        """Helper: crea un objeto con .dt (como hace icalendar)."""
        from datetime import datetime
        from types import SimpleNamespace
        return SimpleNamespace(dt=datetime(year, month, day))

    def test_evento_basico_sin_reservation_url(
        self, service, cal_cfg
    ):
        comp = SimpleNamespace(
            **{"get": lambda key, default=None: {
                "dtstart": TestParseEvent._make_dt(2099, 6, 15),
                "dtend": TestParseEvent._make_dt(2099, 6, 17),
                "summary": "Reservado por Juan",
                "description": "Huesped standard",
            }.get(key, default)}
        )
        ev = service._parse_event(comp, cal_cfg)
        assert ev is not None
        assert ev["calendario_id"] == "paraiso_los_quinquelles_1"
        assert ev["source"] == "airbnb"
        assert ev["nombre"] == "Paraiso Los Quinquelles 1"
        assert ev["summary"] == "Reservado por Juan"
        assert ev["days"] == 2
        assert ev["reservation_url"] is None
        assert ev["codigo_reserva"] is None

    def test_evento_con_reservation_url_y_code_param(
        self, service, cal_cfg
    ):
        desc = (
            "Huesped Juan\n"
            "Reservation URL: https://www.airbnb.com/reservations/details?"
            "code=HM123ABC&guest=1\n"
        )
        comp = SimpleNamespace(
            **{"get": lambda key, default=None: {
                "dtstart": TestParseEvent._make_dt(2099, 7, 1),
                "dtend": TestParseEvent._make_dt(2099, 7, 4),
                "summary": "Airbnb",
                "description": desc,
            }.get(key, default)}
        )
        ev = service._parse_event(comp, cal_cfg)
        assert ev["reservation_url"].startswith("https://www.airbnb.com/")
        assert ev["codigo_reserva"] == "HM123ABC"

    def test_evento_con_reservation_url_sin_code(
        self, service, cal_cfg
    ):
        # URL con formato /reservations/<id> en el path (no en ?code=)
        desc = "Reservation URL: https://www.airbnb.com/reservations/RES-20250101\n"
        comp = SimpleNamespace(
            **{"get": lambda key, default=None: {
                "dtstart": TestParseEvent._make_dt(2099, 7, 1),
                "dtend": TestParseEvent._make_dt(2099, 7, 2),
                "summary": "Airbnb",
                "description": desc,
            }.get(key, default)}
        )
        ev = service._parse_event(comp, cal_cfg)
        assert ev["reservation_url"] is not None
        # codigo_reserva cae al último segmento del path
        assert ev["codigo_reserva"] == "RES-20250101"

    def test_evento_sin_dtstart_o_dtend_devuelve_none(
        self, service, cal_cfg
    ):
        comp = SimpleNamespace(
            **{"get": lambda key, default=None: {
                "summary": "x", "description": "",
                # dtstart y dtend faltan
            }.get(key, default)}
        )
        ev = service._parse_event(comp, cal_cfg)
        assert ev is None

    def test_evento_con_fechas_como_date_no_datetime(
        self, service, cal_cfg
    ):
        # Cuando dtstart es date (no datetime), el código debe
        # combinarlo con datetime.min.time() (all-day events).
        from datetime import date
        from types import SimpleNamespace
        comp = SimpleNamespace(
            **{"get": lambda key, default=None: {
                "dtstart": SimpleNamespace(dt=date(2099, 8, 10)),
                "dtend": SimpleNamespace(dt=date(2099, 8, 12)),
                "summary": "All-day",
                "description": "",
            }.get(key, default)}
        )
        ev = service._parse_event(comp, cal_cfg)
        assert ev is not None
        assert ev["days"] == 2


# ============================================================
# CalendarService._fetch_one (con requests mockeado)
# ============================================================
class TestFetchOne:
    """Cobertura del fetch HTTP real: éxito, fallo de red,
    respuesta que no es iCal válido."""

    @pytest.fixture
    def service(self):
        svc = CalendarService.__new__(CalendarService)
        svc.calendars = []
        svc.last_fetch = None
        svc.cached_events = []
        svc.status = {"global": {}, "per_calendar": {}}
        return svc

    @pytest.fixture
    def cal_cfg(self):
        return {
            "calendario_id": "paraiso_los_quinquelles_1",
            "nombre": "Paraiso Los Quinquelles 1",
            "source": "airbnb",
            "url": "https://www.airbnb.com/calendar/ical/X.ics",
        }

    def _ical_with_event(self, summary="Reservado"):
        """Construye un .ics mínimo con 1 VEVENT."""
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:test1@airbnb\r\n"
            f"SUMMARY:{summary}\r\n"
            "DTSTART:20990615\r\n"
            "DTEND:20990617\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ).encode("utf-8")

    def test_exito_descarga_parsea_y_devuelve_eventos(
        self, service, cal_cfg, monkeypatch
    ):
        mock_response = MagicMock()
        mock_response.content = self._ical_with_event("Reservado por Juan")
        mock_response.raise_for_status = MagicMock()
        monkeypatch.setattr(
            "airbnb_agent.services.airbnb_calendar.requests.get",
            MagicMock(return_value=mock_response),
        )

        result = service._fetch_one(cal_cfg)
        assert result is not None
        assert len(result) == 1
        ev = result[0]
        assert ev["calendario_id"] == "paraiso_los_quinquelles_1"
        assert ev["source"] == "airbnb"
        assert ev["summary"] == "Reservado por Juan"
        assert ev["start"] == "2099-06-15"
        assert ev["end"] == "2099-06-17"
        assert ev["days"] == 2

    def test_error_http_devuelve_none_y_logea(
        self, service, cal_cfg, monkeypatch, capsys
    ):
        # requests.get raises → _fetch_one devuelve None
        def raise_http(*args, **kwargs):
            raise ConnectionError("timeout")
        monkeypatch.setattr(
            "airbnb_agent.services.airbnb_calendar.requests.get",
            raise_http,
        )

        result = service._fetch_one(cal_cfg)
        assert result is None
        captured = capsys.readouterr()
        assert "Error obteniendo calendario" in captured.out
        assert "paraiso_los_quinquelles_1" in captured.out

    def test_http_error_status_devuelve_none(
        self, service, cal_cfg, monkeypatch
    ):
        # raise_for_status lanza HTTPError (4xx/5xx)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=Exception("500 Server Error")
        )
        monkeypatch.setattr(
            "airbnb_agent.services.airbnb_calendar.requests.get",
            MagicMock(return_value=mock_response),
        )

        result = service._fetch_one(cal_cfg)
        assert result is None