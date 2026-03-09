"""
Airbnb Agent - Calendario Visual de Reservas
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from pathlib import Path
import requests
import os
import tomllib
from icalendar import Calendar
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar rutas para Vercel
BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, 
            template_folder=str(BASE_DIR / 'templates'),
            static_folder=str(BASE_DIR / 'static'))

# Leer versión desde pyproject.toml
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_VERSION = "1.0.0"

try:
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
        APP_VERSION = pyproject.get("tool", {}).get("poetry", {}).get("version", APP_VERSION)
except Exception:
    pass

# Configuración
AIRBNB_CALENDAR_URL = os.getenv('AIRBNB_CALENDAR_URL', '')
PROPERTY_NAME = os.getenv('PROPERTY_NAME', 'Posada en el Bosque')

def fetch_calendar_events():
    """Obtiene las reservas del calendario iCal de Airbnb."""
    if not AIRBNB_CALENDAR_URL:
        return []
    
    try:
        response = requests.get(AIRBNB_CALENDAR_URL, timeout=10)
        response.raise_for_status()
        
        cal = Calendar.from_ical(response.content)
        events = []
        
        for component in cal.walk():
            if component.name == "VEVENT":
                start = component.get('dtstart')
                end = component.get('dtend')
                summary = str(component.get('summary', 'Reservado'))
                description = str(component.get('description', ''))
                
                # Extraer URL de reserva del description
                reservation_url = None
                if 'Reservation URL:' in description:
                    import re
                    match = re.search(r'Reservation URL:\s*(https://[^\s\\]+)', description)
                    if match:
                        reservation_url = match.group(1)
                
                if start and end:
                    start_dt = start.dt if hasattr(start, 'dt') else start
                    end_dt = end.dt if hasattr(end, 'dt') else end
                    
                    # Convertir a datetime si es date
                    if not isinstance(start_dt, datetime):
                        start_dt = datetime.combine(start_dt, datetime.min.time())
                    if not isinstance(end_dt, datetime):
                        end_dt = datetime.combine(end_dt, datetime.min.time())
                    
                    events.append({
                        'start': start_dt.strftime('%Y-%m-%d'),
                        'end': end_dt.strftime('%Y-%m-%d'),
                        'summary': summary,
                        'days': (end_dt - start_dt).days,
                        'reservation_url': reservation_url
                    })
        
        # Ordenar por fecha de inicio
        events.sort(key=lambda x: x['start'])
        return events
        
    except Exception as e:
        print(f"Error obteniendo calendario: {e}")
        return []

def get_calendar_stats(events):
    """Calcula estadísticas del calendario."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    next_30_days = today + timedelta(days=30)
    
    total_reserved_days = 0
    upcoming_reservations = 0
    
    for event in events:
        start = datetime.strptime(event['start'], '%Y-%m-%d')
        end = datetime.strptime(event['end'], '%Y-%m-%d')
        
        if start >= today:
            upcoming_reservations += 1
        
        # Contar días reservados en próximos 30 días
        if start <= next_30_days and end >= today:
            overlap_start = max(start, today)
            overlap_end = min(end, next_30_days)
            total_reserved_days += (overlap_end - overlap_start).days
    
    ocupacion = round((total_reserved_days / 30) * 100)
    
    return {
        'total_reservations': len(events),
        'upcoming_reservations': upcoming_reservations,
        'reserved_days_30': total_reserved_days,
        'ocupacion_30': ocupacion
    }

MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

def get_month_calendar(year, month):
    """Genera datos del calendario para un mes específico."""
    import calendar
    
    cal = calendar.Calendar(firstweekday=0)  # Lunes = 0
    month_days = list(cal.itermonthdays2(year, month))
    
    return {
        'year': year,
        'month': month,
        'month_name': MESES_ES[month],
        'days': month_days
    }

@app.route('/')
def home():
    """Página principal - Calendario de Airbnb."""
    events = fetch_calendar_events()
    stats = get_calendar_stats(events)
    
    # Iniciar en el mes actual
    now = datetime.now()
    current = get_month_calendar(now.year, now.month)
    
    return render_template('calendar.html',
                         events=events,
                         stats=stats,
                         current=current,
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME)

@app.route('/api/month')
def api_month():
    """API: Obtener datos de un mes específico."""
    year = request.args.get('year', 2025, type=int)
    month = request.args.get('month', 12, type=int)
    
    return jsonify(get_month_calendar(year, month))

@app.route('/api/events')
def api_events():
    """API: Lista de eventos del calendario."""
    events = fetch_calendar_events()
    return jsonify(events)

@app.route('/api/stats')
def api_stats():
    """API: Estadísticas del calendario."""
    events = fetch_calendar_events()
    stats = get_calendar_stats(events)
    return jsonify(stats)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
