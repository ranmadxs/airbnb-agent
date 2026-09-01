"""
Servicio para sincronizar calendarios iCal de múltiples plataformas/calendarios.

AIRBNB_CALENDAR_URL acepta 2 formatos (auto-detect):
  1. URL simple (legacy, compat 100%):
       AIRBNB_CALENDAR_URL="https://www.airbnb.com/calendar/ical/XYZ.ics"
     → 1 calendario con nombre "default", source "airbnb".

  2. JSON (multi-calendario):
       AIRBNB_CALENDAR_URL='[
         {"nombre": "Paraiso Los Quinquelles 1", "source": "airbnb",
          "url": "https://www.airbnb.com/calendar/ical/XYZ.ics"},
         {"nombre": "Santiago Magno", "source": "airbnb",
          "url": "https://www.airbnb.cl/calendar/ical/ABC.ics"}
       ]'
     → calendario_id derivado del nombre slugificado (slug("Paraiso Los Quinquelles 1")
       = "paraiso_los_quinquelles_1").

Tolerancia a fallos parciales:
  - Si al menos 1 calendario responde OK con eventos → sincroniza ese subset.
  - Si todos fallan → fetch_events() retorna None (guard contra borrado masivo).
  - Si todos responden OK pero unión vacía → fetch_events() retorna [].
"""
import json
import os
import re
import unicodedata
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar
from dotenv import load_dotenv

load_dotenv()

TIMEZONE = os.getenv('TIMEZONE', 'America/Santiago')


def _slugify(name: str) -> str:
    """Convierte 'Paraiso Los Quinquelles 1' en 'paraiso_los_quinquelles_1'."""
    if not name:
        return ''
    normalized = unicodedata.normalize('NFKD', name)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', ascii_str).strip('_').lower()
    return slug or 'unnamed'


class CalendarService:
    """Servicio para interactuar con N calendarios iCal."""

    def __init__(self):
        self.calendars = self._load_calendars()
        self.last_fetch = None
        self.cached_events = []
        self.status = {
            "global": {
                "connected": False,
                "last_check": None,
                "events_count": 0,
                "calendars_count": len(self.calendars),
            },
            "per_calendar": {}
        }

    def _load_calendars(self) -> list:
        """
        Parsea AIRBNB_CALENDAR_URL (URL simple o JSON) y retorna lista de calendarios.
        Cada item: {calendario_id, source, url, nombre}.
        """
        calendars = []
        for prefix in ('AIRBNB', 'BOOKING'):
            env_key = f'{prefix}_CALENDAR_URL'
            raw = os.getenv(env_key, '').strip()
            if not raw:
                continue

            default_source = prefix.lower()  # airbnb / booking
            items = self._parse_value(raw, default_source)
            for item in items:
                nombre = item.get('nombre', '').strip() or 'default'
                source = item.get('source', default_source).strip() or default_source
                url = item.get('url', '').strip()
                if not url:
                    print(f"⚠️ {env_key}: item sin url, omitido ({nombre!r})")
                    continue
                # calendario_id se deriva del nombre humano.
                # Si hay nombres duplicados, agregar sufijos numéricos.
                base_slug = _slugify(nombre)
                slug = base_slug
                suffix = 2
                while any(c['calendario_id'] == slug for c in calendars):
                    slug = f"{base_slug}_{suffix}"
                    suffix += 1
                calendars.append({
                    'calendario_id': slug,
                    'nombre': nombre,
                    'source': source,
                    'url': url,
                })

        return calendars

    def _parse_value(self, raw: str, default_source: str) -> list:
        """
        Auto-detecta formato:
          - Si empieza con '[' → JSON, se espera lista de {nombre, source, url}.
          - Si empieza con 'http' → URL simple, 1 calendario default.
          - Otro → [].

        Acepta comillas dobles externas (típico de archivos .env):
          AIRBNB_CALENDAR_URL="https://..."
        """
        if not raw:
            return []
        s = raw.strip()
        # Strip comillas externas si las trae (.env suele ponerlas).
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            s = s[1:-1].strip()
        if not s:
            return []
        first = s[0]
        if first == '[':
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
                print(f"⚠️ AIRBNB_CALENDAR_URL: JSON no es una lista, ignorado")
                return []
            except json.JSONDecodeError as e:
                print(f"⚠️ AIRBNB_CALENDAR_URL: JSON inválido ({e}), ignorado")
                return []
        if s.lower().startswith('http'):
            return [{'nombre': 'default', 'source': default_source, 'url': s}]
        print(f"⚠️ AIRBNB_CALENDAR_URL: formato no reconocido, ignorado")
        return []

    def _fetch_one(self, calendar_cfg: dict) -> list | None:
        """Descarga y parsea 1 calendario iCal. Retorna lista de eventos o None si falla."""
        url = calendar_cfg['url']
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            cal = Calendar.from_ical(response.content)
            events = []
            for component in cal.walk():
                if component.name == "VEVENT":
                    event = self._parse_event(component, calendar_cfg)
                    if event:
                        events.append(event)
            events.sort(key=lambda x: x['start'])
            return events
        except Exception as e:
            print(f"❌ Error obteniendo calendario {calendar_cfg['calendario_id']} ({url[:60]}...): {e}")
            return None

    def fetch_events(self) -> list | None:
        """
        Sincroniza TODOS los calendarios configurados.

        Retorna:
          - list con la unión de eventos taggeados con source + calendario_id.
            Puede ser [] si todos respondieron OK pero sin eventos futuros.
          - None si TODOS los calendarios fallaron.
        """
        if not self.calendars:
            self.status = {
                "global": {
                    "connected": False,
                    "last_check": datetime.now().isoformat(),
                    "events_count": 0,
                    "calendars_count": 0,
                    "error": "No hay calendarios configurados",
                },
                "per_calendar": {}
            }
            return None

        all_events = []
        now = datetime.now().isoformat()
        per_calendar_status = {}
        all_failed = True

        for cfg in self.calendars:
            cid = cfg['calendario_id']
            events = self._fetch_one(cfg)
            if events is None:
                per_calendar_status[cid] = {
                    "connected": False,
                    "last_check": now,
                    "events_count": 0,
                    "error": "fetch_failed",
                    "url": cfg['url'],
                    "source": cfg['source'],
                    "nombre": cfg['nombre'],
                }
                continue
            all_failed = False
            per_calendar_status[cid] = {
                "connected": True,
                "last_check": now,
                "events_count": len(events),
                "error": None,
                "url": cfg['url'],
                "source": cfg['source'],
                "nombre": cfg['nombre'],
            }
            all_events.extend(events)

        if all_failed:
            self.status = {
                "global": {
                    "connected": False,
                    "last_check": now,
                    "events_count": 0,
                    "calendars_count": len(self.calendars),
                    "error": "all_calendars_failed",
                },
                "per_calendar": per_calendar_status,
            }
            return None

        all_events.sort(key=lambda x: x['start'])
        self.cached_events = all_events
        self.last_fetch = datetime.now()

        self.status = {
            "global": {
                "connected": True,
                "last_check": now,
                "events_count": len(all_events),
                "calendars_count": len(self.calendars),
                "successful_calendars": sum(
                    1 for s in per_calendar_status.values() if s.get('connected')
                ),
                "failed_calendars": sum(
                    1 for s in per_calendar_status.values() if not s.get('connected')
                ),
            },
            "per_calendar": per_calendar_status,
        }

        return all_events

    def _parse_event(self, component, calendar_cfg: dict) -> dict | None:
        """Parsea un VEVENT y lo taggea con source + calendario_id."""
        start = component.get('dtstart')
        end = component.get('dtend')
        summary = str(component.get('summary', 'Reservado'))
        description = str(component.get('description', ''))

        reservation_url = None
        codigo_reserva = None
        if 'Reservation URL:' in description:
            match = re.search(r'Reservation URL:\s*(https://[^\s\\]+)', description)
            if match:
                reservation_url = match.group(1)
                code_match = re.search(r'[?&]code=([^&\s]+)', reservation_url)
                if code_match:
                    codigo_reserva = code_match.group(1)
                else:
                    parts = reservation_url.rstrip('/').split('/')
                    if parts:
                        last = parts[-1]
                        if last and not last.startswith('?'):
                            codigo_reserva = last.split('?')[0] or None

        if not start or not end:
            return None

        start_dt = start.dt if hasattr(start, 'dt') else start
        end_dt = end.dt if hasattr(end, 'dt') else end

        if not isinstance(start_dt, datetime):
            start_dt = datetime.combine(start_dt, datetime.min.time())
        if not isinstance(end_dt, datetime):
            end_dt = datetime.combine(end_dt, datetime.min.time())

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
            'reservation_url': reservation_url,
            'codigo_reserva': codigo_reserva,
            'source': calendar_cfg['source'],
            'calendario_id': calendar_cfg['calendario_id'],
            'nombre': calendar_cfg['nombre'],
        }

    def get_stats(self, events: list = None) -> dict:
        """Calcula estadísticas (ocupación 30 días, próximas reservas)."""
        if events is None:
            events = self.cached_events

        reservas = [e for e in events if e.get('estado') == 'reservado']

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        next_30_days = today + timedelta(days=30)

        total_reserved_days = 0
        upcoming_reservations = 0

        for event in reservas:
            start = datetime.strptime(event['start'], '%Y-%m-%d')
            end = datetime.strptime(event['end'], '%Y-%m-%d')

            if start > today:
                upcoming_reservations += 1

            if start <= next_30_days and end >= today:
                overlap_start = max(start, today)
                overlap_end = min(end, next_30_days)
                total_reserved_days += (overlap_end - overlap_start).days

        ocupacion = round((total_reserved_days / 30) * 100) if total_reserved_days else 0

        return {
            'total_reservations': len(reservas),
            'upcoming_reservations': upcoming_reservations,
            'reserved_days_30': total_reserved_days,
            'ocupacion_30': ocupacion,
        }

    def get_status(self) -> dict:
        """Retorna estado del servicio (global + per-calendario)."""
        return self.status


# Instancia singleton — nombre mantenido por compat con imports en app.py
airbnb_service = CalendarService()

# Alias legacy para imports que aún usen el nombre antiguo
AirbnbCalendarService = CalendarService