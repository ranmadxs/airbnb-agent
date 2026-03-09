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

# MongoDB configuración
MONGODB_URI = os.getenv("MONGODB_URI", "")
mongo_client = None
airbnb_dias_collection = None
calendario_collection = None

def get_mongo_collections():
    """Obtiene las colecciones de MongoDB."""
    global mongo_client, airbnb_dias_collection, calendario_collection
    
    if not MONGODB_URI:
        return None, None
    
    if mongo_client is None:
        try:
            from pymongo import MongoClient
            mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            mongo_client.admin.command('ping')
            db = mongo_client["airbnb-db"]
            
            # Colección de eventos/reservas de Airbnb (llave única: event_start + event_end)
            airbnb_dias_collection = db["airbnb-dias"]
            airbnb_dias_collection.create_index([("event_start", 1), ("event_end", 1)], unique=True)
            
            # Colección de días del calendario (llave única: fecha)
            calendario_collection = db["dias"]
            calendario_collection.create_index("fecha", unique=True)
            
            print("✅ MongoDB conectado para Airbnb Agent")
        except Exception as e:
            print(f"❌ Error conectando MongoDB: {e}")
            return None, None
    
    return airbnb_dias_collection, calendario_collection

def get_mongo_connection():
    """Obtiene la colección airbnb-dias (compatibilidad)."""
    airbnb_dias, _ = get_mongo_collections()
    return airbnb_dias

# Estado de conexiones
calendar_status = {"connected": False, "last_check": None, "events_count": 0}
mongo_status = {"connected": False}

# ============================================================
# FUNCIONES DE CACHÉ MONGODB
# ============================================================

def get_audit_info():
    """Obtiene información de auditoría del request actual."""
    try:
        user_origin = request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown')
        user_agent = request.headers.get('User-Agent', 'unknown')
        return {
            "user_origin": user_origin,
            "user_agent": user_agent
        }
    except:
        return {
            "user_origin": "system",
            "user_agent": "system"
        }

def guardar_evento_airbnb(event_data: dict, estado: str, source: str, audit: dict = None):
    """Guarda o actualiza un evento en airbnb-dias (llave única: event_start + event_end)."""
    collection = get_mongo_connection()
    if collection is None:
        return None
    
    event_start = event_data.get("start")
    event_end = event_data.get("end")
    
    if not event_start or not event_end:
        return None
    
    documento = {
        "event_start": event_start,
        "event_end": event_end,
        "estado": estado,
        "source": source,
        "summary": event_data.get("summary"),
        "reservation_url": event_data.get("reservation_url"),
        "days": event_data.get("days"),
        "updated_at": datetime.utcnow()
    }
    
    # Agregar datos de auditoría
    if audit:
        documento.update({
            "user_origin": audit.get("user_origin"),
            "user_agent": audit.get("user_agent")
        })
    
    try:
        result = collection.update_one(
            {"event_start": event_start, "event_end": event_end},
            {"$set": documento, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
        # Obtener el ID del documento
        if result.upserted_id:
            return result.upserted_id
        else:
            doc = collection.find_one({"event_start": event_start, "event_end": event_end}, {"_id": 1})
            return doc["_id"] if doc else None
    except Exception as e:
        print(f"❌ Error guardando evento {event_start}-{event_end}: {e}")
        return None

def guardar_dias_airbnb(eventos: list, audit: dict = None):
    """
    Guarda eventos en airbnb-dias (únicos por event_start+event_end) 
    y días individuales en 'dias' (únicos por fecha).
    """
    from pymongo import UpdateOne
    
    airbnb_dias, calendario = get_mongo_collections()
    if calendario is None:
        return 0
    
    if audit is None:
        audit = get_audit_info()
    
    # 1. Guardar eventos únicos en airbnb-dias y obtener sus IDs
    eventos_guardados = {}
    for event in eventos:
        event_key = f"{event['start']}_{event['end']}"
        if event_key not in eventos_guardados:
            estado = "bloqueado" if not event.get("reservation_url") else "reservado"
            evento_id = guardar_evento_airbnb(event, estado, "airbnb", audit)
            if evento_id:
                eventos_guardados[event_key] = {
                    "_id": evento_id,
                    "estado": estado,
                    "event": event
                }
    
    # 2. Crear días únicos vinculados a su evento
    dias_unicos = {}
    for event_key, info in eventos_guardados.items():
        event = info["event"]
        start = datetime.strptime(event["start"], "%Y-%m-%d")
        end = datetime.strptime(event["end"], "%Y-%m-%d")
        current = start
        while current < end:
            fecha_str = current.strftime("%Y-%m-%d")
            if fecha_str not in dias_unicos:
                dias_unicos[fecha_str] = {
                    "airbnb_dia_id": info["_id"],
                    "estado": info["estado"]
                }
            current += timedelta(days=1)
    
    if not dias_unicos:
        return 0
    
    # 3. Guardar días en colección 'dias' con bulk
    operaciones = []
    for fecha_str, info in dias_unicos.items():
        partes = fecha_str.split("-")
        anio = int(partes[0])
        mes = int(partes[1])
        dia = int(partes[2])
        
        documento = {
            "anio": anio,
            "mes": mes,
            "dia": dia,
            "fecha": fecha_str,
            "estado": info["estado"],
            "airbnb_dia_id": info["airbnb_dia_id"],
            "updated_at": datetime.utcnow(),
            "user_origin": audit.get("user_origin") if audit else "system",
            "user_agent": audit.get("user_agent") if audit else "system"
        }
        
        operaciones.append(UpdateOne(
            {"fecha": fecha_str},
            {"$set": documento, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        ))
    
    # Ejecutar bulk
    try:
        if operaciones:
            resultado = calendario.bulk_write(operaciones)
            return resultado.upserted_count + resultado.modified_count
    except Exception as e:
        print(f"❌ Error guardando días: {e}")
    
    return 0

def obtener_dias_desde_mongodb(fecha_inicio: str = None, fecha_fin: str = None):
    """Obtiene días desde MongoDB en un rango de fechas."""
    collection = get_mongo_connection()
    if collection is None:
        return {}
    
    try:
        query = {}
        if fecha_inicio and fecha_fin:
            query = {"fecha": {"$gte": fecha_inicio, "$lte": fecha_fin}}
        
        cursor = collection.find(query, {"_id": 0})
        return {doc["fecha"]: doc for doc in cursor}
    except Exception as e:
        print(f"❌ Error obteniendo días: {e}")
        return {}

def sincronizar_con_airbnb(eventos_airbnb: list, audit: dict = None):
    """
    Sincroniza MongoDB con Airbnb:
    - Guarda eventos únicos (por event_start + event_end)
    - Detecta cancelaciones (eventos en DB que ya no están en Airbnb)
    """
    collection = get_mongo_connection()
    if collection is None:
        return {"guardados": 0, "cancelados": 0}
    
    if audit is None:
        audit = get_audit_info()
    
    # Guardar eventos y días
    dias_guardados = guardar_dias_airbnb(eventos_airbnb, audit)
    
    # Crear set de eventos actuales de Airbnb (por event_start + event_end)
    eventos_actuales = set()
    for event in eventos_airbnb:
        eventos_actuales.add(f"{event['start']}_{event['end']}")
    
    # Detectar cancelaciones: eventos en DB que ya no están en Airbnb
    cancelados = 0
    try:
        eventos_en_db = collection.find(
            {"source": "airbnb", "estado": {"$ne": "cancelado"}}, 
            {"event_start": 1, "event_end": 1}
        )
        for doc in eventos_en_db:
            event_key = f"{doc.get('event_start')}_{doc.get('event_end')}"
            if event_key not in eventos_actuales:
                collection.update_one(
                    {"event_start": doc["event_start"], "event_end": doc["event_end"]},
                    {"$set": {
                        "estado": "cancelado", 
                        "updated_at": datetime.utcnow(),
                        "user_origin": audit.get("user_origin"),
                        "user_agent": audit.get("user_agent")
                    }}
                )
                cancelados += 1
                print(f"📅 Cancelación detectada: {doc.get('event_start')} - {doc.get('event_end')}")
    except Exception as e:
        print(f"❌ Error sincronizando: {e}")
    
    return {"guardados": dias_guardados, "cancelados": cancelados}

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
        # Buscar en [project] (PEP 621) o fallback a [tool.poetry]
        APP_VERSION = pyproject.get("project", {}).get("version") or \
                      pyproject.get("tool", {}).get("poetry", {}).get("version", APP_VERSION)
except Exception:
    pass

# Configuración
AIRBNB_CALENDAR_URL = os.getenv('AIRBNB_CALENDAR_URL', '')
PROPERTY_NAME = os.getenv('PROPERTY_NAME', 'Posada en el Bosque')

def fetch_calendar_from_airbnb():
    """Obtiene las reservas directamente del calendario iCal de Airbnb."""
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
        
        events.sort(key=lambda x: x['start'])
        return events
        
    except Exception as e:
        print(f"Error obteniendo calendario Airbnb: {e}")
        return []

def fetch_calendar_events():
    """
    Obtiene las reservas combinando MongoDB (caché) y Airbnb.
    - Sincroniza con Airbnb para detectar nuevos eventos y cancelaciones
    - Retorna eventos para mostrar en el calendario
    """
    global calendar_status
    
    if not AIRBNB_CALENDAR_URL:
        calendar_status = {"connected": False, "last_check": datetime.now().isoformat(), "events_count": 0, "error": "URL no configurada"}
        return []
    
    try:
        # 1. Obtener eventos frescos de Airbnb
        eventos_airbnb = fetch_calendar_from_airbnb()
        
        # 2. Sincronizar con MongoDB (guarda nuevos, detecta cancelaciones)
        sync_result = sincronizar_con_airbnb(eventos_airbnb)
        
        # 3. Actualizar estado
        calendar_status = {
            "connected": True, 
            "last_check": datetime.now().isoformat(), 
            "events_count": len(eventos_airbnb),
            "sync": sync_result
        }
        
        return eventos_airbnb
        
    except Exception as e:
        print(f"Error obteniendo calendario: {e}")
        calendar_status = {
            "connected": False, 
            "last_check": datetime.now().isoformat(), 
            "events_count": 0,
            "error": str(e)
        }
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
    
    # Guardar días de Airbnb en MongoDB (solo los que tienen eventos)
    audit = get_audit_info()
    guardar_dias_airbnb(events, audit)
    
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

@app.route('/api/status')
def api_status():
    """API: Estado de conexiones (MongoDB y Calendario)."""
    global mongo_status
    
    # Verificar MongoDB
    collection = get_mongo_connection()
    mongo_status = {
        "configured": bool(MONGODB_URI),
        "connected": collection is not None
    }
    
    return jsonify({
        "calendar": calendar_status,
        "mongodb": mongo_status
    })

@app.route('/api/dias')
def api_dias():
    """API: Días almacenados en MongoDB."""
    fecha_inicio = request.args.get('desde')
    fecha_fin = request.args.get('hasta')
    
    dias = obtener_dias_desde_mongodb(fecha_inicio, fecha_fin)
    
    # Convertir datetime a string para JSON
    for fecha, doc in dias.items():
        if "updated_at" in doc and doc["updated_at"]:
            doc["updated_at"] = doc["updated_at"].isoformat()
        if "created_at" in doc and doc["created_at"]:
            doc["created_at"] = doc["created_at"].isoformat()
    
    return jsonify({
        "total": len(dias),
        "dias": list(dias.values())
    })

@app.route('/api/sync', methods=['POST'])
def api_sync():
    """API: Forzar sincronización con Airbnb."""
    eventos_airbnb = fetch_calendar_from_airbnb()
    result = sincronizar_con_airbnb(eventos_airbnb)
    return jsonify({
        "mensaje": "Sincronización completada",
        "eventos_airbnb": len(eventos_airbnb),
        "dias_guardados": result["guardados"],
        "cancelaciones": result["cancelados"]
    })

@app.route('/api/calendario')
def api_calendario():
    """API: Días del calendario desde la colección 'dias'."""
    anio = request.args.get('anio', datetime.now().year, type=int)
    mes = request.args.get('mes', datetime.now().month, type=int)
    
    _, calendario = get_mongo_collections()
    if calendario is None:
        return jsonify({"error": "MongoDB no disponible", "dias": []})
    
    try:
        cursor = calendario.find(
            {"anio": anio, "mes": mes},
            {"_id": 0}
        ).sort("dia", 1)
        
        dias = []
        for doc in cursor:
            if "updated_at" in doc and doc["updated_at"]:
                doc["updated_at"] = doc["updated_at"].isoformat()
            if "created_at" in doc and doc["created_at"]:
                doc["created_at"] = doc["created_at"].isoformat()
            if "airbnb_dia_id" in doc and doc["airbnb_dia_id"]:
                doc["airbnb_dia_id"] = str(doc["airbnb_dia_id"])
            dias.append(doc)
        
        return jsonify({
            "anio": anio,
            "mes": mes,
            "total": len(dias),
            "dias": dias
        })
    except Exception as e:
        return jsonify({"error": str(e), "dias": []})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
