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


def test_guardar_calendario_con_logo_binario(monkeypatch):
    svc = make_svc(monkeypatch)
    svc.calendarios.find_one.return_value = None
    svc.calendarios.update_one.return_value = MagicMock(upserted_id=None)
    r = svc.guardar_calendario({
        "nombre": "Casa Lago", "source": "airbnb",
        "logo_bytes": b"\x89PNG...",
        "logo_mime": "image/png",
        "logo_nombre": "logo.png",
    })
    assert r["success"] is True
    assert r["tiene_logo"] is True
    args, _ = svc.calendarios.update_one.call_args
    guardado = args[1]["$set"]
    assert bytes(guardado["logo_bin"]) == b"\x89PNG..."
    assert guardado["logo_mime"] == "image/png"


def test_listar_calendarios_con_tiene_logo(monkeypatch):
    from bson import Binary
    svc = make_svc(monkeypatch)
    cursor = MagicMock()
    cursor.sort.return_value = [
        {"_id": "x", "calendario_id": "con_logo", "nombre": "Con Logo",
         "source": "airbnb", "url": "", "color": "",
         "logo_bin": Binary(b"\x89PNG"), "logo_mime": "image/png"},
        {"_id": "y", "calendario_id": "sin_logo", "nombre": "Sin Logo",
         "source": "airbnb", "url": "", "color": ""},
    ]
    svc.calendarios.find.return_value = cursor
    cals = {c["calendario_id"]: c for c in svc.listar_calendarios()}
    assert cals["con_logo"]["tiene_logo"] is True
    assert cals["sin_logo"]["tiene_logo"] is False


def test_obtener_logo_calendario(monkeypatch):
    from bson import Binary
    svc = make_svc(monkeypatch)
    svc.calendarios.find_one.return_value = {
        "calendario_id": "casa_lago",
        "logo_bin": Binary(b"\x89PNG..."), "logo_mime": "image/png",
    }
    contenido, mime = svc.obtener_logo_calendario("casa_lago")
    assert bytes(contenido) == b"\x89PNG..."
    assert mime == "image/png"
    svc.calendarios.find_one.return_value = {"calendario_id": "otro"}
    assert svc.obtener_logo_calendario("otro") is None


def test_get_logo_endpoint(logged_in_flask_client, app_module):
    app_module.db_service.obtener_logo_calendario.return_value = (b"\x89PNG...", "image/png")
    r = logged_in_flask_client.get("/api/calendarios/casa_lago/logo")
    assert r.status_code == 200
    assert r.content_type == "image/png"
    assert r.get_data() == b"\x89PNG..."
    app_module.db_service.obtener_logo_calendario.return_value = None
    r2 = logged_in_flask_client.get("/api/calendarios/sin_logo/logo")
    assert r2.status_code == 404


def test_post_calendario_con_logo_y_color(logged_in_flask_client, app_module):
    app_module.db_service.listar_calendarios.return_value = []
    app_module.db_service.guardar_calendario.return_value = {
        "success": True, "calendario_id": "casa_lago", "nombre": "Casa Lago",
        "tiene_logo": True,
    }
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
    assert data["logo_url"] == "/api/calendarios/casa_lago/logo"
    args, _ = app_module.db_service.guardar_calendario.call_args
    assert args[0]["color"] == "#ff0000"
    assert args[0]["logo_bytes"] == png
    assert args[0]["logo_mime"] == "image/png"


def test_post_calendario_logo_invalido_devuelve_json(logged_in_flask_client, app_module, monkeypatch):
    """Extensión no soportada o tamaño excedido => 400 JSON (nunca HTML)."""
    app_module.db_service.listar_calendarios.return_value = []
    r = logged_in_flask_client.post(
        "/api/calendarios",
        data={"nombre": "Casa Lago", "imagen": (io.BytesIO(b"exe..."), "logo.exe")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert r.content_type.startswith("application/json")
    assert r.get_json()["success"] is False

    monkeypatch.setattr(app_module, "CALENDARIO_IMAGEN_MAX_BYTES", 10)
    r2 = logged_in_flask_client.post(
        "/api/calendarios",
        data={"nombre": "Casa Lago",
              "imagen": (io.BytesIO(b"0" * 100), "logo.png")},
        content_type="multipart/form-data",
    )
    assert r2.status_code == 400
    assert r2.get_json()["success"] is False


def test_post_calendario_requiere_login(flask_client, app_module):
    r = flask_client.post("/api/calendarios", data={"nombre": "X"})
    assert r.status_code == 401


def test_api_calendarios_incluye_url(logged_in_flask_client, app_module, monkeypatch):
    from unittest.mock import MagicMock
    app_module.airbnb_service.calendars = [
        {"calendario_id": "env_uno", "nombre": "Env", "source": "airbnb",
         "url": "https://x.ics", "imagen": "", "thumbnail": "", "logo": ""},
    ]
    app_module.db_service.listar_calendarios.return_value = []
    monkeypatch.setattr(app_module.db_service, "connect", MagicMock(return_value=False))
    c0 = logged_in_flask_client.get("/api/calendarios").get_json()["configured"][0]
    assert c0["url"] == "https://x.ics"


def test_put_calendario_actualiza(logged_in_flask_client, app_module):
    app_module.airbnb_service.calendars = [
        {"calendario_id": "env_uno", "nombre": "Env", "source": "airbnb", "url": "https://x"},
    ]
    app_module.db_service.listar_calendarios.return_value = [
        {"calendario_id": "casa_lago", "nombre": "Casa Lago", "source": "airbnb",
         "url": "", "color": "", "tiene_logo": True, "dinamico": True},
    ]
    app_module.db_service.guardar_calendario.return_value = {
        "success": True, "calendario_id": "casa_lago", "nombre": "Casa Lago Nuevo",
        "tiene_logo": True,
    }
    png = b"\x89PNG" + b"1" * 100
    r = logged_in_flask_client.put(
        "/api/calendarios/casa_lago",
        data={"nombre": "Casa Lago Nuevo", "source": "booking",
              "url": "https://example.com/n.ics", "color": "#00ff00",
              "imagen": (io.BytesIO(png), "nuevo.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["logo_url"] == "/api/calendarios/casa_lago/logo"
    args, kwargs = app_module.db_service.guardar_calendario.call_args
    assert kwargs.get("calendario_id") == "casa_lago" or (len(args) > 1 and args[1] == "casa_lago")
    assert args[0]["nombre"] == "Casa Lago Nuevo"
    assert args[0]["logo_bytes"] == png


def test_put_calendario_sin_logo_conserva_binario(logged_in_flask_client, app_module):
    app_module.airbnb_service.calendars = []
    app_module.db_service.listar_calendarios.return_value = [
        {"calendario_id": "casa_lago", "nombre": "Casa Lago", "dinamico": True,
         "tiene_logo": True},
    ]
    app_module.db_service.guardar_calendario.return_value = {
        "success": True, "calendario_id": "casa_lago", "tiene_logo": True,
    }
    r = logged_in_flask_client.put(
        "/api/calendarios/casa_lago",
        data={"nombre": "Casa Lago Editada"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    args, _ = app_module.db_service.guardar_calendario.call_args
    assert not args[0].get("logo_bytes")


def test_put_calendario_env_rechazado(logged_in_flask_client, app_module):
    app_module.airbnb_service.calendars = [
        {"calendario_id": "env_uno", "nombre": "Env", "source": "airbnb", "url": "https://x"},
    ]
    r = logged_in_flask_client.put("/api/calendarios/env_uno", data={"nombre": "X"})
    assert r.status_code == 400


def test_put_calendario_inexistente_404(logged_in_flask_client, app_module):
    app_module.airbnb_service.calendars = []
    app_module.db_service.listar_calendarios.return_value = []
    r = logged_in_flask_client.put("/api/calendarios/fantasma", data={"nombre": "X"})
    assert r.status_code == 404


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
