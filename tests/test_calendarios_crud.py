"""CRUD de calendarios creados por admin (logo + color propios).

TDD RED: DatabaseService.listar/guardar/eliminar_calendario y los endpoints
POST/DELETE /api/calendarios no existen aun.
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock

from airbnb_agent.services.database import DatabaseService


def make_svc(monkeypatch):
    svc = DatabaseService.__new__(DatabaseService)
    svc.uri = ""
    svc.client = None
    svc.db = None
    svc.calendarios = MagicMock()
    svc.connected = False
    monkeypatch.setattr(svc, "connect", lambda: True)
    return svc


def test_guardar_calendario_requiere_nombre(monkeypatch):
    svc = make_svc(monkeypatch)
    r = svc.guardar_calendario({"nombre": "   ", "source": "airbnb"})
    assert r["success"] is False


def test_guardar_calendario_genera_slug_y_valida_color(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.calendarios.find_one.return_value = None
    svc.calendarios.update_one.return_value = MagicMock(upserted_id=None)
    r = svc.guardar_calendario({
        "nombre": "Casa Lago", "source": "airbnb",
        "url": "https://example.com/x.ics", "color": "#ff0000",
        "thumbnail": "images/calendarios/casa_lago.png",
    })
    assert r["success"] is True
    assert r["calendario_id"] == "casa_lago"
    args, _ = svc.calendarios.update_one.call_args
    assert args[0] == {"calendario_id": "casa_lago"}
    assert args[1]["$set"]["color"] == "#ff0000"


def test_guardar_calendario_color_invalido_se_limpia(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.calendarios.find_one.return_value = None
    svc.calendarios.update_one.return_value = MagicMock(upserted_id=None)
    r = svc.guardar_calendario({"nombre": "Casa Lago", "color": "rojo"})
    assert r["success"] is True
    args, _ = svc.calendarios.update_one.call_args
    assert args[1]["$set"]["color"] == ""


def test_guardar_calendario_slug_duplicado_agrega_sufijo(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.calendarios.find_one.side_effect = lambda q: {"calendario_id": q["calendario_id"]} if q["calendario_id"] in ("casa_lago",) else None
    svc.calendarios.update_one.return_value = MagicMock(upserted_id=None)
    r = svc.guardar_calendario({"nombre": "Casa Lago"})
    assert r["calendario_id"] == "casa_lago_2"


def test_listar_calendarios(monkeypatch):
    svc = make_svc(monkeypatch)
    cursor = MagicMock()
    cursor.sort.return_value = [
        {"_id": "x", "calendario_id": "casa_lago", "nombre": "Casa Lago",
         "source": "airbnb", "url": "", "color": "#ff0000",
         "thumbnail": "images/calendarios/casa_lago.png", "logo": ""},
    ]
    svc.calendarios.find.return_value = cursor
    cals = svc.listar_calendarios()
    assert len(cals) == 1
    assert cals[0]["calendario_id"] == "casa_lago"
    assert cals[0]["color"] == "#ff0000"


def test_eliminar_calendario(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.calendarios.delete_one.return_value = MagicMock(deleted_count=1)
    assert svc.eliminar_calendario("casa_lago") is True
    svc.calendarios.delete_one.return_value = MagicMock(deleted_count=0)
    assert svc.eliminar_calendario("inexistente") is False


def test_fetch_ignora_calendario_sin_url():
    from airbnb_agent.services.airbnb_calendar import CalendarService
    svc = CalendarService.__new__(CalendarService)
    svc.calendars = [
        {"calendario_id": "manual", "nombre": "Manual", "source": "admin", "url": ""},
    ]
    svc.last_fetch = None
    svc.cached_events = []
    svc.status = {}
    assert svc.fetch_events() == []


def test_post_calendario_con_logo_y_color(logged_in_flask_client, app_module, tmp_path, monkeypatch):
    app_module.db_service.listar_calendarios.return_value = []
    app_module.db_service.guardar_calendario.return_value = {
        "success": True, "calendario_id": "casa_lago", "nombre": "Casa Lago",
    }
    monkeypatch.setattr(app_module, "CALENDARIOS_UPLOAD_DIR", str(tmp_path))
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = logged_in_flask_client.post(
        "/api/calendarios",
        data={"nombre": "Casa Lago", "source": "airbnb",
              "url": "https://example.com/x.ics", "color": "#ff0000",
              "imagen": (io.BytesIO(png), "logo.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["calendario_id"] == "casa_lago"
    saved = list(tmp_path.iterdir())
    assert len(saved) == 1 and saved[0].suffix == ".png"
    args, _ = app_module.db_service.guardar_calendario.call_args
    assert args[0]["color"] == "#ff0000"
    assert args[0]["thumbnail"].startswith("images/calendarios/")


def test_post_calendario_requiere_login(flask_client, app_module):
    r = flask_client.post("/api/calendarios", data={"nombre": "X"})
    assert r.status_code == 401


def test_delete_calendario_dinamico(logged_in_flask_client, app_module):
    app_module.airbnb_service.calendars = [
        {"calendario_id": "env_uno", "nombre": "Env", "source": "airbnb", "url": "https://x"},
    ]
    app_module.db_service.eliminar_calendario.return_value = True
    r = logged_in_flask_client.delete("/api/calendarios/casa_lago")
    assert r.status_code == 200
    assert r.get_json()["success"] is True


def test_delete_calendario_env_rechazado(logged_in_flask_client, app_module):
    app_module.airbnb_service.calendars = [
        {"calendario_id": "env_uno", "nombre": "Env", "source": "airbnb", "url": "https://x"},
    ]
    r = logged_in_flask_client.delete("/api/calendarios/env_uno")
    assert r.status_code == 400
