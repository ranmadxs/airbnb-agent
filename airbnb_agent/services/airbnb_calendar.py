"""
Servicio para obtener datos del calendario de Airbnb
"""
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from icalendar import Calendar
from dotenv import load_dotenv

load_dotenv()

AIRBNB_CALENDAR_URL = os.getenv('AIRBNB_CALENDAR_URL', '')
TIMEZONE = os.getenv('TIMEZONE', 'America/Santiago')


class AirbnbCalendarService:
    """Servicio para interactuar con el calendario iCal de Airbnb."""
    
    def __init__(self):
        self.url = AIRBNB_CALENDAR_URL
        self.last_fetch = None
        self.cached_events = []
        self.status = {"connected": False, "last_check": None, "events_count": 0}
    
    def fetch_events(self) -> list:
        """Obtiene eventos del calendario iCal de Airbnb."""
        if not self.url:
            self.status = {
                "connected": False, 
                "last_check": datetime.now().isoformat(), 
                "events_count": 0,
                "error": "URL no configurada"
            }
            return []
        
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            
            cal = Calendar.from_ical(response.content)
            events = []
            
            for component in cal.walk():
                if component.name == "VEVENT":
                    event = self._parse_event(component)
                    if event:
                        events.append(event)
            
            events.sort(key=lambda x: x['start'])
            
            self.cached_events = events
            self.last_fetch = datetime.now()
            self.status = {
                "connected": True, 
                "last_check": datetime.now().isoformat(), 
                "events_count": len(events)
            }
            
            return events
            
        except Exception as e:
            print(f"❌ Error obteniendo calendario Airbnb: {e}")
            self.status = {
                "connected": False, 
                "last_check": datetime.now().isoformat(), 
                "events_count": 0,
                "error": str(e)
            }
            return []
    
    def _parse_event(self, component) -> dict:
        """Parsea un componente VEVENT a diccionario."""
        import re
        
        start = component.get('dtstart')
        end = component.get('dtend')
        summary = str(component.get('summary', 'Reservado'))
        description = str(component.get('description', ''))
        
        # Extraer URL de reserva
        reservation_url = None
        if 'Reservation URL:' in description:
            match = re.search(r'Reservation URL:\s*(https://[^\s\\]+)', description)
            if match:
                reservation_url = match.group(1)
        
        if not start or not end:
            return None
        
        start_dt = start.dt if hasattr(start, 'dt') else start
        end_dt = end.dt if hasattr(end, 'dt') else end
        
        # Convertir a datetime si es date
        if not isinstance(start_dt, datetime):
            start_dt = datetime.combine(start_dt, datetime.min.time())
        if not isinstance(end_dt, datetime):
            end_dt = datetime.combine(end_dt, datetime.min.time())
        
        # Convertir a zona horaria de la propiedad si iCal trae timezone (evita desfase UTC)
        tz_prop = ZoneInfo(TIMEZONE)
        if start_dt.tzinfo is not None:
            start_dt = start_dt.astimezone(tz_prop)
        if end_dt.tzinfo is not None:
            end_dt = end_dt.astimezone(tz_prop)
        
        return {
            'start': start_dt.strftime('%Y-%m-%d'),
            'end': end_dt.strftime('%Y-%m-%d'),
            'summary': summary,
            'days': (end_dt - start_dt).days,
            'reservation_url': reservation_url
        }
    
    def get_stats(self, events: list = None) -> dict:
        """Calcula estadísticas del calendario (solo reservas, no bloqueos)."""
        from datetime import timedelta
        
        if events is None:
            events = self.cached_events
        
        # Filtrar solo reservas (no bloqueos ni eliminados)
        reservas = [e for e in events if e.get('estado') == 'reservado']
        
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        next_30_days = today + timedelta(days=30)
        
        total_reserved_days = 0
        upcoming_reservations = 0
        
        for event in reservas:
            start = datetime.strptime(event['start'], '%Y-%m-%d')
            end = datetime.strptime(event['end'], '%Y-%m-%d')
            
            # Próximas = check-in en el futuro
            if start > today:
                upcoming_reservations += 1
            
            # Ocupación próximos 30 días
            if start <= next_30_days and end >= today:
                overlap_start = max(start, today)
                overlap_end = min(end, next_30_days)
                total_reserved_days += (overlap_end - overlap_start).days
        
        ocupacion = round((total_reserved_days / 30) * 100) if total_reserved_days else 0
        
        return {
            'total_reservations': len(reservas),
            'upcoming_reservations': upcoming_reservations,
            'reserved_days_30': total_reserved_days,
            'ocupacion_30': ocupacion
        }
    
    def get_status(self) -> dict:
        """Retorna el estado del servicio."""
        return self.status


# Instancia singleton
airbnb_service = AirbnbCalendarService()
