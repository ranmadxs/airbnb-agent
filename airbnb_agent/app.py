"""
Airbnb Agent - Calendario Visual de Reservas
Solo endpoints Flask - lógica en services/
"""
import os
import calendar
import tomllib
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

from .services.airbnb_calendar import airbnb_service
from .services.database import db_service

load_dotenv()

# Configurar Flask
BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, 
            template_folder=str(BASE_DIR / 'templates'),
            static_folder=str(BASE_DIR / 'static'))

# Leer versión
PROJECT_ROOT = BASE_DIR.parent
APP_VERSION = "1.0.0"
try:
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
        APP_VERSION = pyproject.get("project", {}).get("version") or \
                      pyproject.get("tool", {}).get("poetry", {}).get("version", APP_VERSION)
except Exception:
    pass

# Config
PROPERTY_NAME = os.getenv('PROPERTY_NAME', 'Posada en el Bosque')

MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def get_audit_info() -> dict:
    """Obtiene info de auditoría del request."""
    try:
        return {
            "user_origin": request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown'),
            "user_agent": request.headers.get('User-Agent', 'unknown')
        }
    except:
        return {"user_origin": "system", "user_agent": "system"}


def get_month_calendar(year: int, month: int) -> dict:
    """Genera datos del calendario para un mes."""
    cal = calendar.Calendar(firstweekday=0)
    return {
        'year': year,
        'month': month,
        'month_name': MESES_ES[month],
        'days': list(cal.itermonthdays2(year, month))
    }


# ============================================================
# ENDPOINTS
# ============================================================

@app.route('/')
def home():
    """Página principal."""
    events = airbnb_service.fetch_events()
    data_source = "ical"
    
    # Si iCal falló, intentar desde MongoDB
    if not events and db_service.connected:
        events = db_service.obtener_eventos_formato_ical()
        data_source = "cache"
    
    stats = airbnb_service.get_stats(events)
    
    now = datetime.now()
    current = get_month_calendar(now.year, now.month)
    
    # Sync en background solo si tenemos datos frescos de iCal
    if data_source == "ical" and events:
        db_service.sync_en_background(events, get_audit_info())
    
    return render_template('calendar.html',
                         events=events,
                         stats=stats,
                         current=current,
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME,
                         data_source=data_source)


@app.route('/api/month')
def api_month():
    """API: Datos de un mes específico."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    return jsonify(get_month_calendar(year, month))


@app.route('/api/events')
def api_events():
    """API: Eventos del calendario."""
    events = airbnb_service.fetch_events()
    return jsonify(events)


@app.route('/api/stats')
def api_stats():
    """API: Estadísticas."""
    events = airbnb_service.fetch_events()
    stats = airbnb_service.get_stats(events)
    return jsonify(stats)


@app.route('/api/status')
def api_status():
    """API: Estado de conexiones."""
    return jsonify({
        "calendar": airbnb_service.get_status(),
        "mongodb": db_service.get_status()
    })


@app.route('/api/dias')
def api_dias():
    """API: Días desde MongoDB."""
    anio = request.args.get('anio', type=int)
    mes = request.args.get('mes', type=int)
    dias = db_service.obtener_dias(anio, mes)
    return jsonify({"total": len(dias), "dias": dias})


@app.route('/api/eventos-db')
def api_eventos_db():
    """API: Eventos desde MongoDB."""
    eventos = db_service.obtener_eventos()
    return jsonify({"total": len(eventos), "eventos": eventos})


@app.route('/api/sync', methods=['POST'])
def api_sync():
    """API: Forzar sincronización (bloqueante)."""
    events = airbnb_service.fetch_events()
    result = db_service.forzar_sync(events, get_audit_info())
    return jsonify({
        "mensaje": "Sincronización completada",
        "eventos_airbnb": len(events),
        **result
    })


@app.route('/api/calendario')
def api_calendario():
    """API: Días del calendario por mes."""
    anio = request.args.get('anio', datetime.now().year, type=int)
    mes = request.args.get('mes', datetime.now().month, type=int)
    dias = db_service.obtener_dias(anio, mes)
    return jsonify({
        "anio": anio,
        "mes": mes,
        "total": len(dias),
        "dias": dias
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
