"""Configuración global para pytest.

Mockea variables de entorno y servicios externos (MongoDB, requests) ANTES
de que se importe el paquete airbnb_agent, ya que app.py y los servicios
hacen lecturas/llamadas costosas en el momento de import.

Cada test que necesite MongoDB real debe usar `mongo_collection_mock`
(ver fixtures) o skipear si no hay red disponible.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Raíz del repo (para encontrar pyproject.toml en runtime.txt)
REPO_ROOT = Path(__file__).resolve().parent.parent

# Variables de entorno mínimas para que airbnb_agent se importe sin reventar.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("AUTH_USERNAME", "admin")
os.environ.setdefault("AUTH_PASSWORD", "admin")
os.environ.setdefault("MONGODB_URI", "")
os.environ.setdefault("AIRBNB_CALENDAR_URL", "")
os.environ.setdefault("BOOKING_CALENDAR_URL", "")
os.environ.setdefault("MERCADOPAGO_ACCESS_TOKEN", "")
os.environ.setdefault("MERCADOPAGO_WEBHOOK_SECRET", "")
os.environ.setdefault("VERCEL", "")


@pytest.fixture
def app_module():
    """Importa airbnb_agent.app y devuelve el módulo. Mockea db_service
    para evitar intentos de conexión a Mongo durante tests."""
    with patch("airbnb_agent.services.database.MONGODB_URI", ""):
        # Re-importar en limpio para tomar el patch antes de instanciar db_service
        if "airbnb_agent.app" in sys.modules:
            del sys.modules["airbnb_agent.app"]
        from airbnb_agent import app as _app

        # Stub de db_service y airbnb_service
        _app.db_service = MagicMock()
        _app.airbnb_service = MagicMock()
        _app.airbnb_service.calendars = []
        _app.airbnb_service.get_status.return_value = {
            "global": {"connected": False, "events_count": 0, "calendars_count": 0},
            "per_calendar": {},
        }
        _app.airbnb_service.get_stats.return_value = {
            "total_reservations": 0,
            "upcoming_reservations": 0,
            "reserved_days_30": 0,
            "ocupacion_30": 0,
        }
        _app.airbnb_service.fetch_events.return_value = []
        return _app


@pytest.fixture
def flask_client(app_module):
    """Cliente Flask con sesión habilitada para tests de rutas."""
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def logged_in_flask_client(app_module):
    """Cliente Flask autenticado como admin."""
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["logged_in"] = True
        yield client