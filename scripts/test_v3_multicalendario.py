#!/usr/bin/env python3
"""
Tests visuales y de API para v3.0.0 multi-calendario.

NO toca Atlas. Solo valida:
  - Endpoints /api/month y /api/reservas/por-fecha
  - Service: parseo de JSON, auto-detect URL simple, slugify
  - Helper: ingresos por calendario
  - Compat: shape del response (regresión)

Uso:
    python scripts/test_v3_multicalendario.py
"""
import sys
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import date

# Cargar .env desde la raíz del proyecto
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_slugify():
    """Servicio: slugify de nombres humanos."""
    from airbnb_agent.services.airbnb_calendar import _slugify

    casos = [
        ("Paraiso Los Quinquelles 1", "paraiso_los_quinquelles_1"),
        ("Santiago Magno", "santiago_magno"),
        ("Café Ñandú", "cafe_nandu"),
        ("  Casa del Lago   ", "casa_del_lago"),
        ("", ""),
        ("!!!@@@###", "unnamed"),
    ]
    for inp, esperado in casos:
        got = _slugify(inp)
        assert got == esperado, f"slugify({inp!r}) = {got!r}, esperado {esperado!r}"
    print("✓ _slugify() correcto (6 casos)")


def test_parse_json():
    """Servicio: parseo de JSON multi-calendario."""
    import importlib
    # Forzar el valor de env ANTES de cargar el módulo
    os.environ["AIRBNB_CALENDAR_URL"] = '''[
        {"nombre": "Paraiso Los Quinquelles 1", "source": "airbnb", "url": "https://x.com/a.ics"},
        {"nombre": "Santiago Magno", "source": "airbnb", "url": "https://x.com/b.ics"}
    ]'''
    # load_dotenv() va a sobreescribir esto. Hack: monkey-patch os.getenv
    # durante la instanciación para que retorne nuestro valor.
    from airbnb_agent.services import airbnb_calendar as ac_mod
    original_getenv = os.getenv
    def fake_getenv(key, default=''):
        if key == 'AIRBNB_CALENDAR_URL':
            return os.environ[key]
        return original_getenv(key, default)
    os.getenv = fake_getenv
    try:
        svc = ac_mod.CalendarService()
        assert len(svc.calendars) == 2, f"Esperaba 2, obtuve {len(svc.calendars)}"
        assert svc.calendars[0]["calendario_id"] == "paraiso_los_quinquelles_1"
        assert svc.calendars[1]["calendario_id"] == "santiago_magno"
        assert svc.calendars[0]["nombre"] == "Paraiso Los Quinquelles 1"
    finally:
        os.getenv = original_getenv
    print("✓ parseo JSON multi-calendario OK")


def test_parse_url_simple():
    """Servicio: compat con URL simple legacy."""
    from airbnb_agent.services import airbnb_calendar as ac_mod
    original_getenv = os.getenv
    url_test = "https://www.airbnb.com/calendar/ical/SINGLE.ics"
    def fake_getenv(key, default=''):
        if key == 'AIRBNB_CALENDAR_URL':
            return url_test
        return original_getenv(key, default)
    os.getenv = fake_getenv
    try:
        svc = ac_mod.CalendarService()
        assert len(svc.calendars) == 1, f"Esperaba 1 calendario, obtuve {len(svc.calendars)}"
        assert svc.calendars[0]["calendario_id"] == "default"
        assert svc.calendars[0]["source"] == "airbnb"
    finally:
        os.getenv = original_getenv
    print("✓ parseo URL simple (legacy compat) OK")


def test_ingresos_por_calendario():
    """Helper: subtotales por calendario_id."""
    from airbnb_agent.app import _calcular_ingresos_por_calendario

    events = [
        # 3 reservas mismo día (mix de calendarios)
        {
            "start": "2026-09-15", "end": "2026-09-18",
            "estado": "reservado", "precio": 100000, "extra_valor": 0,
            "calendario_id": "paraiso_los_quinquelles_1",
            "source": "airbnb"
        },
        {
            "start": "2026-09-15", "end": "2026-09-17",
            "estado": "reservado", "precio": 80000, "extra_valor": 0,
            "calendario_id": "santiago_magno",
            "source": "airbnb"
        },
        {
            "start": "2026-09-15", "end": "2026-09-16",
            "estado": "reservado", "precio": 50000, "extra_valor": 0,
            "calendario_id": None,  # legacy
            "source": "admin"
        },
        # 1 reserva fuera del mes (no debe contar)
        {
            "start": "2026-10-01", "end": "2026-10-03",
            "estado": "reservado", "precio": 999999, "extra_valor": 0,
            "calendario_id": "x",
            "source": "airbnb"
        },
    ]
    res = _calcular_ingresos_por_calendario(events, 2026, 9)
    assert "paraiso_los_quinquelles_1" in res
    assert "santiago_magno" in res
    assert "__legacy__" in res
    # 100k + 80k + 50k = 230k total
    assert res["paraiso_los_quinquelles_1"]["arriendo"] == 100000
    assert res["santiago_magno"]["arriendo"] == 80000
    assert res["__legacy__"]["arriendo"] == 50000
    print("✓ _calcular_ingresos_por_calendario() agrupa correctamente")


def test_endpoint_calendarios():
    """Endpoint /api/calendarios retorna calendarios configurados."""
    from airbnb_agent.app import app

    client = app.test_client()
    r = client.get('/api/calendarios')
    assert r.status_code == 200
    data = r.get_json()
    assert "configured" in data
    assert "has_legacy" in data
    # Tu .env tiene 2 calendarios
    assert len(data["configured"]) >= 2, f"Esperaba ≥2 calendarios, obtuve {len(data['configured'])}"
    nombres = [c["nombre"] for c in data["configured"]]
    assert "Paraiso Los Quinquelles 1" in nombres, f"No encontré Paraiso. Nombres: {nombres}"
    assert "Santiago Magno" in nombres, f"No encontré Santiago Magno. Nombres: {nombres}"
    print(f"✓ /api/calendarios retorna {len(data['configured'])} calendarios + has_legacy={data['has_legacy']}")


def test_endpoint_month_filtro():
    """Endpoint /api/month acepta calendario_ids."""
    from airbnb_agent.app import app

    client = app.test_client()

    # Sin filtro
    r1 = client.get('/api/month?year=2026&month=9')
    d1 = r1.get_json()
    n1 = len(d1.get("events", []))

    # Con filtro Paraiso
    r2 = client.get('/api/month?year=2026&month=9&calendario_ids=paraiso_los_quinquelles_1')
    d2 = r2.get_json()
    n2 = len(d2.get("events", []))

    # Con filtro Santiago Magno
    r3 = client.get('/api/month?year=2026&month=9&calendario_ids=santiago_magno')
    d3 = r3.get_json()
    n3 = len(d3.get("events", []))

    # Con filtro vacío → []
    r4 = client.get('/api/month?year=2026&month=9&calendario_ids=')
    d4 = r4.get_json()
    n4 = len(d4.get("events", []))

    assert n2 <= n1, "Filtro Paraiso debería dar subset"
    assert n3 <= n1, "Filtro Santiago Magno debería dar subset"
    assert n4 == n1, "Filtro vacío debería ser igual a sin filtro"

    # Todos los eventos del filtro2 deben tener calendario_id=paraiso_los_quinquelles_1
    for ev in d2.get("events", []):
        assert ev.get("calendario_id") == "paraiso_los_quinquelles_1", \
            f"Evento filtrado tiene calendario_id={ev.get('calendario_id')}"

    # Ingresos_por_calendario presente en todos los responses
    assert "ingresos_por_calendario" in d1
    assert "ingresos_por_calendario" in d2

    print(f"✓ /api/month filtro OK: sin={n1}, paraiso={n2}, santiago={n3}, vacio={n4}")


def test_endpoint_reservas_por_fecha_plural():
    """Endpoint /api/reservas/por-fecha/<fecha> (NUEVO plural)."""
    from airbnb_agent.app import app

    client = app.test_client()
    # Sin auth devuelve 401, pero la firma del endpoint debe existir
    r = client.get('/api/reservas/por-fecha/2026-09-15')
    assert r.status_code == 401, f"Esperaba 401 (sin login), obtuve {r.status_code}"
    print("✓ /api/reservas/por-fecha/<fecha> existe (plural, requiere auth)")


def test_shape_compat_v3():
    """El response tiene los campos nuevos + todos los legacy."""
    from airbnb_agent.app import app

    client = app.test_client()
    r = client.get('/api/month?year=2026&month=9')
    d = r.get_json()

    # Campos legacy que el frontend lee
    legacy_keys = {"year", "month", "month_name", "days", "events", "ingresos"}
    assert legacy_keys.issubset(d.keys()), f"Faltan keys legacy: {legacy_keys - d.keys()}"

    # Nuevos
    assert "ingresos_por_calendario" in d

    # Cada evento tiene calendario_id (puede ser None para legacy)
    for ev in d.get("events", []):
        # El frontend lee estos campos
        for k in ("id", "start", "end", "estado", "summary", "nombre_huesped",
                  "precio", "extra_valor", "calendario_id", "source"):
            assert k in ev, f"Evento sin campo {k}"

    print(f"✓ Shape del response retrocompatible + campos nuevos presentes")


def main():
    print("=" * 60)
    print("Tests v3.0.0 — Multi-calendario")
    print("=" * 60)

    tests = [
        test_slugify,
        test_parse_json,
        test_parse_url_simple,
        test_ingresos_por_calendario,
        test_endpoint_calendarios,
        test_endpoint_month_filtro,
        test_endpoint_reservas_por_fecha_plural,
        test_shape_compat_v3,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"Resultado: {passed} pasaron, {failed} fallaron")
    if failed:
        sys.exit(1)
    else:
        print("✅ Todos los tests v3.0.0 pasaron.")


if __name__ == "__main__":
    main()