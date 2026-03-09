"""
Servicio para operaciones de base de datos MongoDB
"""
import os
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "")


class DatabaseService:
    """Servicio para operaciones de MongoDB."""
    
    def __init__(self):
        self.uri = MONGODB_URI
        self.client = None
        self.reservas = None
        self.dias = None
        self.connected = False
        self.ultima_sync = None
        self.sync_interval = 300  # 5 minutos
        
        # Intentar conectar al inicializar si está configurado
        if self.uri:
            self.connect()
    
    def connect(self):
        """Conecta a MongoDB."""
        if not self.uri:
            return False
        
        try:
            from pymongo import MongoClient
            
            if self.client is None:
                self.client = MongoClient(self.uri, serverSelectionTimeoutMS=2000)
            
            # Ping para verificar conexión
            self.client.admin.command('ping')
            
            if self.reservas is None:
                db = self.client["airbnb-db"]
                self.reservas = db["reservas"]
                self.dias = db["dias"]
                
                # Crear índices
                self.reservas.create_index([("event_start", 1), ("event_end", 1)], unique=True)
                self.dias.create_index("fecha", unique=True)
            
            self.connected = True
            return True
        except Exception as e:
            print(f"❌ Error MongoDB: {e}")
            self.connected = False
            return False
    
    def _ping(self) -> bool:
        """Verifica conexión con ping rápido."""
        if self.client is None:
            return False
        try:
            self.client.admin.command('ping')
            return True
        except:
            return False
    
    def get_status(self) -> dict:
        """Retorna el estado de la conexión."""
        if not self.uri:
            return {"configured": False, "connected": False}
        
        if self.connected:
            # Verificar que sigue conectado
            if not self._ping():
                self.connected = False
        else:
            # Intentar reconectar
            self.connect()
        
        return {
            "configured": True,
            "connected": self.connected
        }
    
    def necesita_sync(self) -> bool:
        """Verifica si necesita sincronizar."""
        if self.ultima_sync is None:
            return True
        return (datetime.now() - self.ultima_sync).total_seconds() > self.sync_interval
    
    def sync_en_background(self, eventos: list, audit: dict = None):
        """Sincroniza en segundo plano sin bloquear."""
        if not self.necesita_sync():
            return
        
        thread = threading.Thread(
            target=self._sync_worker,
            args=(eventos, audit),
            daemon=True
        )
        thread.start()
    
    def _sync_worker(self, eventos: list, audit: dict = None):
        """Worker que hace la sincronización real."""
        try:
            self.guardar_eventos(eventos, audit)
            self.ultima_sync = datetime.now()
            print(f"✅ Sync completado: {len(eventos)} eventos")
        except Exception as e:
            print(f"❌ Error en sync: {e}")
    
    def guardar_eventos(self, eventos: list, audit: dict = None):
        """Guarda eventos en airbnb-dias y días en 'dias' usando bulk operations.
        
        - Eventos de iCal se guardan con source: "airbnb"
        - Eventos en BD que no vienen en iCal se marcan como source: "cache_airbnb"
        - Datos históricos (< hoy) no se modifican
        """
        from pymongo import UpdateOne
        
        if not self.connect():
            return 0
        
        if audit is None:
            audit = {"user_origin": "system", "user_agent": "system"}
        
        hoy = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Obtener eventos actuales de iCal (claves)
        eventos_ical_keys = set()
        for event in eventos:
            if event["end"] >= hoy:
                eventos_ical_keys.add(f"{event['start']}_{event['end']}")
        
        # 2. Marcar eventos futuros que NO están en iCal como cache_airbnb
        try:
            self.reservas.update_many(
                {
                    "event_end": {"$gte": hoy},
                    "source": "airbnb"
                },
                {"$set": {"source": "cache_airbnb"}}
            )
        except Exception as e:
            print(f"❌ Error marcando cache: {e}")
        
        # 3. Preparar bulk para eventos de iCal (solo futuros)
        eventos_ops = []
        eventos_unicos = {}
        
        for event in eventos:
            # Solo sincronizar eventos que terminan hoy o en el futuro
            if event["end"] < hoy:
                continue
                
            event_key = f"{event['start']}_{event['end']}"
            if event_key not in eventos_unicos:
                estado = "bloqueado" if not event.get("reservation_url") else "reservado"
                eventos_unicos[event_key] = {"event": event, "estado": estado}
                
                eventos_ops.append(UpdateOne(
                    {"event_start": event["start"], "event_end": event["end"]},
                    {"$set": {
                        "event_start": event["start"],
                        "event_end": event["end"],
                        "estado": estado,
                        "source": "airbnb",
                        "summary": event.get("summary"),
                        "reservation_url": event.get("reservation_url"),
                        "days": event.get("days"),
                        "updated_at": datetime.utcnow(),
                        "user_origin": audit.get("user_origin", "system"),
                        "user_agent": audit.get("user_agent", "system")
                    }, "$setOnInsert": {"created_at": datetime.utcnow()}},
                    upsert=True
                ))
        
        # 2. Ejecutar bulk eventos
        eventos_guardados = 0
        try:
            if eventos_ops:
                resultado = self.reservas.bulk_write(eventos_ops)
                eventos_guardados = resultado.upserted_count + resultado.modified_count
        except Exception as e:
            print(f"❌ Error bulk eventos: {e}")
            return 0
        
        # 3. Marcar días futuros como cache_airbnb (antes de actualizar con iCal)
        try:
            self.dias.update_many(
                {
                    "fecha": {"$gte": hoy},
                    "source": "airbnb"
                },
                {"$set": {"source": "cache_airbnb"}}
            )
        except Exception as e:
            print(f"❌ Error marcando días cache: {e}")
        
        # 4. Preparar bulk para días (solo días >= hoy)
        dias_ops = []
        dias_unicos = set()
        
        for event_key, info in eventos_unicos.items():
            event = info["event"]
            estado = info["estado"]
            start = datetime.strptime(event["start"], "%Y-%m-%d")
            end = datetime.strptime(event["end"], "%Y-%m-%d")
            current = start
            
            while current < end:
                fecha_str = current.strftime("%Y-%m-%d")
                # Solo sincronizar días >= hoy (históricos son definitivos)
                if fecha_str >= hoy and fecha_str not in dias_unicos:
                    dias_unicos.add(fecha_str)
                    partes = fecha_str.split("-")
                    
                    dias_ops.append(UpdateOne(
                        {"fecha": fecha_str},
                        {"$set": {
                            "anio": int(partes[0]),
                            "mes": int(partes[1]),
                            "dia": int(partes[2]),
                            "fecha": fecha_str,
                            "estado": estado,
                            "source": "airbnb",
                            "event_start": event["start"],
                            "event_end": event["end"],
                            "updated_at": datetime.utcnow(),
                            "user_origin": audit.get("user_origin", "system"),
                            "user_agent": audit.get("user_agent", "system")
                        }, "$setOnInsert": {"created_at": datetime.utcnow()}},
                        upsert=True
                    ))
                current += timedelta(days=1)
        
        # 4. Ejecutar bulk días
        try:
            if dias_ops:
                resultado = self.dias.bulk_write(dias_ops)
                return resultado.upserted_count + resultado.modified_count
        except Exception as e:
            print(f"❌ Error bulk días: {e}")
        
        return 0
    
    def obtener_dias(self, anio: int = None, mes: int = None) -> list:
        """Obtiene días desde MongoDB."""
        if not self.connect():
            return []
        
        try:
            query = {}
            if anio and mes:
                query = {"anio": anio, "mes": mes}
            
            cursor = self.dias.find(query, {"_id": 0}).sort("fecha", 1)
            
            dias = []
            for doc in cursor:
                if "updated_at" in doc and doc["updated_at"]:
                    doc["updated_at"] = doc["updated_at"].isoformat()
                if "created_at" in doc and doc["created_at"]:
                    doc["created_at"] = doc["created_at"].isoformat()
                if "reserva_id" in doc and doc["reserva_id"]:
                    doc["reserva_id"] = str(doc["reserva_id"])
                dias.append(doc)
            
            return dias
        except Exception as e:
            print(f"❌ Error obteniendo días: {e}")
            return []
    
    def obtener_eventos(self) -> list:
        """Obtiene eventos desde MongoDB (formato interno)."""
        if not self.connect():
            return []
        
        try:
            cursor = self.reservas.find({}, {"_id": 0}).sort("event_start", 1)
            
            eventos = []
            for doc in cursor:
                if "updated_at" in doc and doc["updated_at"]:
                    doc["updated_at"] = doc["updated_at"].isoformat()
                if "created_at" in doc and doc["created_at"]:
                    doc["created_at"] = doc["created_at"].isoformat()
                eventos.append(doc)
            
            return eventos
        except Exception as e:
            print(f"❌ Error obteniendo eventos: {e}")
            return []
    
    def obtener_eventos_formato_ical(self) -> list:
        """Obtiene eventos desde MongoDB en formato compatible con iCal/frontend."""
        if not self.connect():
            return []
        
        try:
            cursor = self.reservas.find({}, {"_id": 0}).sort("event_start", 1)
            
            eventos = []
            for doc in cursor:
                eventos.append({
                    "start": doc.get("event_start"),
                    "end": doc.get("event_end"),
                    "days": doc.get("days", 1),
                    "summary": doc.get("summary", "Cached"),
                    "reservation_url": doc.get("reservation_url"),
                    "source": doc.get("source", "cache_airbnb")
                })
            
            return eventos
        except Exception as e:
            print(f"❌ Error obteniendo eventos: {e}")
            return []
    
    def forzar_sync(self, eventos: list, audit: dict = None) -> dict:
        """Fuerza sincronización inmediata (bloqueante)."""
        try:
            guardados = self.guardar_eventos(eventos, audit)
            self.ultima_sync = datetime.now()
            return {"guardados": guardados, "cancelados": 0}
        except Exception as e:
            return {"error": str(e), "guardados": 0, "cancelados": 0}


# Instancia singleton
db_service = DatabaseService()
