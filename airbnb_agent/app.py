"""
Airbnb Agent - Calendario Visual de Reservas
"""

from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
from pathlib import Path
import requests
import os
from icalendar import Calendar
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configuración
AIRBNB_CALENDAR_URL = os.getenv('AIRBNB_CALENDAR_URL', '')
APP_VERSION = "1.0.0"

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
                
                if start and end:
                    start_dt = start.dt if hasattr(start, 'dt') else start
                    end_dt = end.dt if hasattr(end, 'dt') else end
                    
                    # Convertir a datetime si es date
                    if not isinstance(start_dt, datetime):
                        start_dt = datetime.combine(start_dt, datetime.min.time())
                    if not isinstance(end_dt, datetime):
                        end_dt = datetime.combine(end_dt, datetime.min.time())
                    
                    events.append({
                        'start': start_dt.isoformat(),
                        'end': end_dt.isoformat(),
                        'summary': summary,
                        'days': (end_dt - start_dt).days
                    })
        
        # Ordenar por fecha de inicio
        events.sort(key=lambda x: x['start'])
        return events
        
    except Exception as e:
        print(f"Error obteniendo calendario: {e}")
        return []

def get_calendar_stats(events):
    """Calcula estadísticas del calendario."""
    now = datetime.now()
    next_30_days = now + timedelta(days=30)
    
    total_reserved_days = 0
    upcoming_reservations = 0
    
    for event in events:
        start = datetime.fromisoformat(event['start'])
        end = datetime.fromisoformat(event['end'])
        
        if start >= now:
            upcoming_reservations += 1
        
        # Contar días reservados en próximos 30 días
        if start <= next_30_days and end >= now:
            overlap_start = max(start, now)
            overlap_end = min(end, next_30_days)
            total_reserved_days += (overlap_end - overlap_start).days
    
    ocupacion = round((total_reserved_days / 30) * 100)
    
    return {
        'total_reservations': len(events),
        'upcoming_reservations': upcoming_reservations,
        'reserved_days_30': total_reserved_days,
        'ocupacion_30': ocupacion
    }

def get_month_calendar(year, month):
    """Genera datos del calendario para un mes específico."""
    import calendar
    
    cal = calendar.Calendar(firstweekday=0)  # Lunes = 0
    month_days = list(cal.itermonthdays2(year, month))
    
    return {
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'days': month_days
    }

@app.route('/')
def home():
    """Página principal - Calendario de Airbnb."""
    events = fetch_calendar_events()
    stats = get_calendar_stats(events)
    
    # Obtener calendario del mes actual y siguiente
    now = datetime.now()
    current_month = get_month_calendar(now.year, now.month)
    
    next_month = now.month + 1
    next_year = now.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    next_month_cal = get_month_calendar(next_year, next_month)
    
    return render_template('calendar.html',
                         events=events,
                         stats=stats,
                         current_month=current_month,
                         next_month=next_month_cal,
                         version=APP_VERSION)

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
