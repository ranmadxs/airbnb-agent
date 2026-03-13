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
        self.db = None
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
                self.db = self.client["airbnb-db"]
                self.reservas = self.db["reservas"]
                self.dias = self.db["dias"]
                
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
        #    (NO tocar las que tienen readonly=True)
        try:
            self.reservas.update_many(
                {
                    "event_end": {"$gte": hoy},
                    "source": "airbnb",
                    "readonly": {"$ne": True}
                },
                {"$set": {"source": "cache_airbnb"}}
            )
        except Exception as e:
            print(f"❌ Error marcando cache: {e}")
        
        # 3. Obtener reservas protegidas (readonly=True) para no sobrescribirlas
        reservas_protegidas = set()
        reservas_protegidas_rangos = []
        try:
            for doc in self.reservas.find({"readonly": True}, {"event_start": 1, "event_end": 1}):
                reservas_protegidas.add(f"{doc['event_start']}_{doc['event_end']}")
                # Guardar como datetime para comparación robusta
                prot_start = datetime.strptime(doc['event_start'], "%Y-%m-%d")
                prot_end = datetime.strptime(doc['event_end'], "%Y-%m-%d")
                reservas_protegidas_rangos.append((prot_start, prot_end))
        except Exception as e:
            print(f"❌ Error obteniendo reservas protegidas: {e}")
        
        # Función para verificar si un rango se superpone con reservas protegidas
        def superpone_con_protegida(start_str, end_str):
            try:
                start = datetime.strptime(start_str, "%Y-%m-%d")
                end = datetime.strptime(end_str, "%Y-%m-%d")
                for prot_start, prot_end in reservas_protegidas_rangos:
                    # Hay superposición si: start < prot_end AND end > prot_start
                    if start < prot_end and end > prot_start:
                        print(f"🚫 Evento {start_str}->{end_str} superpone con protegida {prot_start.strftime('%Y-%m-%d')}->{prot_end.strftime('%Y-%m-%d')}")
                        return True
            except:
                pass
            return False
        
        # 4. Preparar bulk para eventos de iCal (solo futuros, no protegidos)
        eventos_ops = []
        eventos_unicos = {}
        
        for event in eventos:
            # Solo sincronizar eventos que terminan hoy o en el futuro
            if event["end"] < hoy:
                continue
                
            event_key = f"{event['start']}_{event['end']}"
            
            # NO sobrescribir reservas protegidas (readonly)
            if event_key in reservas_protegidas:
                print(f"⚠️ Reserva protegida, omitiendo: {event_key}")
                continue
            
            # NO crear bloqueos que se superponen con reservas protegidas
            if superpone_con_protegida(event["start"], event["end"]):
                print(f"⚠️ Se superpone con reserva protegida, omitiendo: {event_key}")
                continue
            
            if event_key not in eventos_unicos:
                # Determinar si es reserva: tiene URL, o el summary indica "Reserved"
                summary_ical = event.get("summary", "")
                es_reserva = event.get("reservation_url") or "reserved" in summary_ical.lower()
                estado = "reservado" if es_reserva else "bloqueado"
                
                # Descripción basada en el estado
                if estado == "reservado":
                    summary = "Reservado por usuarios de Airbnb"
                else:
                    summary = "Bloqueado por propietario en Airbnb"
                
                eventos_unicos[event_key] = {"event": event, "estado": estado}
                
                # Verificar si ya existe en la BD para no sobrescribir estado "reservado"
                existente = self.reservas.find_one({"event_start": event["start"], "event_end": event["end"]})
                if existente and existente.get("estado") == "reservado":
                    # Ya es reserva, no cambiar estado
                    eventos_ops.append(UpdateOne(
                        {"event_start": event["start"], "event_end": event["end"]},
                        {"$set": {
                            "source": "airbnb",
                            "reservation_url": event.get("reservation_url") or existente.get("reservation_url"),
                            "days": event.get("days"),
                            "updated_at": datetime.utcnow(),
                        }},
                        upsert=False
                    ))
                else:
                    eventos_ops.append(UpdateOne(
                        {"event_start": event["start"], "event_end": event["end"]},
                        {"$set": {
                            "event_start": event["start"],
                            "event_end": event["end"],
                            "estado": estado,
                            "source": "airbnb",
                            "summary": summary,
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
        #    (NO tocar días con readonly=True)
        try:
            self.dias.update_many(
                {
                    "fecha": {"$gte": hoy},
                    "source": "airbnb",
                    "readonly": {"$ne": True}
                },
                {"$set": {"source": "cache_airbnb"}}
            )
        except Exception as e:
            print(f"❌ Error marcando días cache: {e}")
        
        # 4. Obtener días protegidos (readonly=True)
        dias_protegidos = set()
        try:
            for doc in self.dias.find({"readonly": True, "fecha": {"$gte": hoy}}, {"fecha": 1}):
                dias_protegidos.add(doc['fecha'])
        except Exception as e:
            print(f"❌ Error obteniendo días protegidos: {e}")
        
        # 5. Preparar bulk para días (solo días >= hoy, no protegidos)
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
                # Solo sincronizar días >= hoy, no protegidos, no duplicados
                if fecha_str >= hoy and fecha_str not in dias_unicos and fecha_str not in dias_protegidos:
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
            cursor = self.reservas.find().sort("event_start", 1)
            
            eventos = []
            for doc in cursor:
                eventos.append({
                    "id": str(doc.get("_id")),
                    "start": doc.get("event_start"),
                    "end": doc.get("event_end"),
                    "days": doc.get("days", 1),
                    "summary": doc.get("summary", "Cached"),
                    "reservation_url": doc.get("reservation_url"),
                    "source": doc.get("source", "cache_airbnb"),
                    "estado": doc.get("estado", "bloqueado"),
                    "readonly": doc.get("readonly", False),
                    "checkout": doc.get("checkout"),
                    "hora_checkin": doc.get("hora_checkin", ""),
                    "hora_checkout": doc.get("hora_checkout") or "18:00",
                    "nombre_huesped": doc.get("nombre_huesped", ""),
                    "adultos": doc.get("adultos", 0),
                    "ninos": doc.get("ninos", 0),
                    "mascotas": doc.get("mascotas", 0),
                    "notas": doc.get("notas", ""),
                    "precio": doc.get("precio", 0),
                    "extra_concepto": doc.get("extra_concepto", ""),
                    "extra_valor": doc.get("extra_valor", 0),
                    "comuna": doc.get("comuna", ""),
                    "pais": doc.get("pais", "")
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
    
    def obtener_reserva_por_id(self, reserva_id: str) -> dict:
        """Obtiene una reserva por su ID."""
        if not self.connect():
            return None
        
        try:
            from bson import ObjectId
            doc = self.reservas.find_one({"_id": ObjectId(reserva_id)})
            if doc:
                doc['_id'] = str(doc['_id'])
            return doc
        except Exception as e:
            print(f"❌ Error obteniendo reserva: {e}")
            return None
    
    def buscar_reserva_por_fecha(self, fecha: str) -> dict:
        """Busca una reserva que incluya la fecha dada."""
        if not self.connect():
            return None
        
        try:
            doc = self.reservas.find_one({
                "event_start": {"$lte": fecha},
                "event_end": {"$gt": fecha}
            })
            if doc:
                doc['_id'] = str(doc['_id'])
            return doc
        except Exception as e:
            print(f"❌ Error buscando reserva: {e}")
            return None
    
    def guardar_reserva_manual(self, reserva_id: str, datos: dict, audit: dict = None) -> dict:
        """Guarda una reserva creada/editada manualmente."""
        if not self.connect():
            return {"success": False, "error": "No hay conexión a MongoDB"}
        
        if audit is None:
            audit = {"user_origin": "admin", "user_agent": "admin"}
        
        try:
            from bson import ObjectId
            
            # Calcular días
            start = datetime.strptime(datos['event_start'], "%Y-%m-%d")
            end = datetime.strptime(datos['event_end'], "%Y-%m-%d")
            days = (end - start).days
            
            doc = {
                "event_start": datos['event_start'],
                "event_end": datos['event_end'],
                "days": days,
                "estado": datos['estado'],
                "summary": datos.get('summary', 'Manual'),
                "reservation_url": datos.get('reservation_url'),
                "source": datos.get('source', 'admin'),
                "readonly": datos.get('readonly', False),
                "hora_checkin": datos.get('hora_checkin', ''),
                "hora_checkout": datos.get('hora_checkout', ''),
                "nombre_huesped": datos.get('nombre_huesped', ''),
                "adultos": datos.get('adultos', 0),
                "ninos": datos.get('ninos', 0),
                "mascotas": datos.get('mascotas', 0),
                "notas": datos.get('notas', ''),
                "precio": datos.get('precio', 0),
                "extra_concepto": datos.get('extra_concepto', ''),
                "extra_valor": datos.get('extra_valor', 0),
                "comuna": datos.get('comuna', ''),
                "pais": datos.get('pais', ''),
                "updated_at": datetime.utcnow(),
                "user_origin": audit.get("user_origin", "admin"),
                "user_agent": audit.get("user_agent", "admin")
            }
            
            if reserva_id:
                # Actualizar existente
                result = self.reservas.update_one(
                    {"_id": ObjectId(reserva_id)},
                    {"$set": doc}
                )
                success = result.modified_count > 0 or result.matched_count > 0
            else:
                # Crear nueva
                doc["created_at"] = datetime.utcnow()
                result = self.reservas.insert_one(doc)
                success = result.inserted_id is not None
                reserva_id = str(result.inserted_id)
            
            # Actualizar colección dias
            if success:
                self._actualizar_dias_reserva(datos, audit)
            
            return {"success": success, "id": reserva_id}
        except Exception as e:
            print(f"❌ Error guardando reserva: {e}")
            return {"success": False, "error": str(e)}
    
    def _actualizar_dias_reserva(self, datos: dict, audit: dict):
        """Actualiza la colección dias para una reserva."""
        try:
            from pymongo import UpdateOne
            
            start = datetime.strptime(datos['event_start'], "%Y-%m-%d")
            end = datetime.strptime(datos['event_end'], "%Y-%m-%d")
            current = start
            
            ops = []
            while current < end:
                fecha_str = current.strftime("%Y-%m-%d")
                partes = fecha_str.split("-")
                
                ops.append(UpdateOne(
                    {"fecha": fecha_str},
                    {"$set": {
                        "anio": int(partes[0]),
                        "mes": int(partes[1]),
                        "dia": int(partes[2]),
                        "fecha": fecha_str,
                        "estado": datos['estado'],
                        "source": datos.get('source', 'admin'),
                        "readonly": datos.get('readonly', False),
                        "event_start": datos['event_start'],
                        "event_end": datos['event_end'],
                        "updated_at": datetime.utcnow(),
                        "user_origin": audit.get("user_origin", "admin"),
                        "user_agent": audit.get("user_agent", "admin")
                    }, "$setOnInsert": {"created_at": datetime.utcnow()}},
                    upsert=True
                ))
                current += timedelta(days=1)
            
            if ops:
                self.dias.bulk_write(ops)
        except Exception as e:
            print(f"❌ Error actualizando días: {e}")
    
    def eliminar_reserva(self, reserva_id: str, audit: dict = None) -> bool:
        """Eliminación LÓGICA: marca estado='eliminado' y readonly=True."""
        if not self.connect():
            return False
        
        if audit is None:
            audit = {"user_origin": "admin", "user_agent": "admin"}
        
        try:
            from bson import ObjectId
            
            # Guardar estado anterior antes de eliminar
            reserva = self.reservas.find_one({"_id": ObjectId(reserva_id)})
            if not reserva:
                return False
            
            # Eliminación lógica
            result = self.reservas.update_one(
                {"_id": ObjectId(reserva_id)},
                {"$set": {
                    "estado": "eliminado",
                    "estado_anterior": reserva.get("estado"),
                    "readonly": True,
                    "updated_at": datetime.utcnow(),
                    "user_origin": audit.get("user_origin", "admin"),
                    "user_agent": audit.get("user_agent", "admin")
                }}
            )
            
            # Marcar días como eliminados también
            if result.modified_count > 0:
                self.dias.update_many(
                    {
                        "event_start": reserva['event_start'],
                        "event_end": reserva['event_end']
                    },
                    {"$set": {
                        "estado": "eliminado",
                        "readonly": True,
                        "updated_at": datetime.utcnow()
                    }}
                )
            
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error eliminando reserva: {e}")
            return False
    
    def restaurar_reserva(self, reserva_id: str, audit: dict = None) -> bool:
        """Restaura una reserva eliminada a su estado anterior."""
        if not self.connect():
            return False
        
        if audit is None:
            audit = {"user_origin": "admin", "user_agent": "admin"}
        
        try:
            from bson import ObjectId
            
            reserva = self.reservas.find_one({"_id": ObjectId(reserva_id)})
            if not reserva or reserva.get("estado") != "eliminado":
                return False
            
            # Restaurar al estado anterior
            estado_anterior = reserva.get("estado_anterior", "bloqueado")
            
            result = self.reservas.update_one(
                {"_id": ObjectId(reserva_id)},
                {
                    "$set": {
                        "estado": estado_anterior,
                        "readonly": False,
                        "updated_at": datetime.utcnow(),
                        "user_origin": audit.get("user_origin", "admin"),
                        "user_agent": audit.get("user_agent", "admin")
                    },
                    "$unset": {"estado_anterior": ""}
                }
            )
            
            # Restaurar días también
            if result.modified_count > 0:
                self.dias.update_many(
                    {
                        "event_start": reserva['event_start'],
                        "event_end": reserva['event_end']
                    },
                    {"$set": {
                        "estado": estado_anterior,
                        "readonly": False,
                        "updated_at": datetime.utcnow()
                    }}
                )
            
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error restaurando reserva: {e}")
            return False
    
    def finalizar_estadia(self, reserva_id: str, audit: dict = None) -> dict:
        """Marca checkout de una estadía (cliente se retiró). No cambia el estado."""
        if not self.connect():
            return {"success": False, "error": "No hay conexión a MongoDB"}
        
        if audit is None:
            audit = {"user_origin": "admin", "user_agent": "admin"}
        
        try:
            from bson import ObjectId
            
            reserva = self.reservas.find_one({"_id": ObjectId(reserva_id)})
            if not reserva:
                return {"success": False, "error": "Reserva no encontrada"}
            
            if reserva.get("estado") != "reservado":
                return {"success": False, "error": "Solo se pueden marcar checkout en reservas activas"}
            
            if reserva.get("checkout"):
                return {"success": False, "error": "Esta reserva ya tiene checkout registrado"}
            
            hoy = datetime.now().strftime("%Y-%m-%d")
            
            result = self.reservas.update_one(
                {"_id": ObjectId(reserva_id)},
                {"$set": {
                    "checkout": hoy,
                    "updated_at": datetime.utcnow(),
                    "user_origin": audit.get("user_origin", "admin"),
                    "user_agent": audit.get("user_agent", "admin")
                }}
            )
            
            return {"success": result.modified_count > 0}
        except Exception as e:
            print(f"❌ Error registrando checkout: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # GASTOS DE AGUA
    # ============================================================
    
    def obtener_gastos_agua(self, year: int, month: int) -> list:
        """Obtiene gastos de agua del mes especificado."""
        if not self.connect():
            return []
        
        try:
            # Buscar por año y mes de fecha_pago
            inicio_mes = f"{year}-{str(month).zfill(2)}-01"
            if month == 12:
                fin_mes = f"{year + 1}-01-01"
            else:
                fin_mes = f"{year}-{str(month + 1).zfill(2)}-01"
            
            cursor = self.db.gastos_agua.find({
                'fecha_pago': {'$gte': inicio_mes, '$lt': fin_mes}
            }).sort('fecha_pago', -1)
            
            gastos = []
            for doc in cursor:
                gastos.append({
                    'id': str(doc.get('_id')),
                    'razon': doc.get('razon', ''),
                    'nombre': doc.get('nombre', ''),
                    'tipo': doc.get('tipo', ''),
                    'fecha_pago': doc.get('fecha_pago', ''),
                    'fecha_creacion': doc.get('fecha_creacion', ''),
                    'valor': doc.get('valor', 0),
                    'descripcion': doc.get('descripcion', ''),
                    'whatsapp': doc.get('whatsapp', ''),
                    'pagado': doc.get('pagado', True)
                })
            
            return gastos
        except Exception as e:
            print(f"❌ Error obteniendo gastos agua: {e}")
            return []
    
    def guardar_gasto_agua(self, gasto: dict) -> dict:
        """Guarda un nuevo gasto de agua."""
        if not self.connect():
            return {"success": False, "error": "No se pudo conectar a la base de datos"}
        
        try:
            doc = {
                'razon': gasto.get('razon', ''),
                'nombre': gasto.get('nombre', ''),
                'tipo': gasto.get('tipo', 'consumo'),
                'fecha_pago': gasto.get('fecha_pago', ''),
                'fecha_creacion': datetime.utcnow().isoformat(),
                'valor': gasto.get('valor', 0),
                'descripcion': gasto.get('descripcion', ''),
                'whatsapp': gasto.get('whatsapp', ''),
                'pagado': gasto.get('pagado', True),
                'proveedor_id': gasto.get('proveedor_id', '')
            }
            
            result = self.db.gastos_agua.insert_one(doc)
            
            return {"success": result.inserted_id is not None, "id": str(result.inserted_id)}
        except Exception as e:
            print(f"❌ Error guardando gasto agua: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # GASTOS DE INTERNET
    # ============================================================
    
    def obtener_gastos_internet(self, year: int, month: int) -> list:
        """Obtiene gastos de internet del mes especificado."""
        if not self.connect():
            return []
        
        try:
            inicio_mes = f"{year}-{str(month).zfill(2)}-01"
            if month == 12:
                fin_mes = f"{year + 1}-01-01"
            else:
                fin_mes = f"{year}-{str(month + 1).zfill(2)}-01"
            
            cursor = self.db.gastos_internet.find({
                'fecha_pago': {'$gte': inicio_mes, '$lt': fin_mes}
            }).sort('fecha_pago', -1)
            
            gastos = []
            for doc in cursor:
                gastos.append({
                    'id': str(doc.get('_id')),
                    'razon': doc.get('razon', ''),
                    'nombre': doc.get('nombre', ''),
                    'tipo': doc.get('tipo', ''),
                    'fecha_pago': doc.get('fecha_pago', ''),
                    'fecha_creacion': doc.get('fecha_creacion', ''),
                    'valor': doc.get('valor', 0),
                    'descripcion': doc.get('descripcion', ''),
                    'whatsapp': doc.get('whatsapp', ''),
                    'pagado': doc.get('pagado', True)
                })
            
            return gastos
        except Exception as e:
            print(f"❌ Error obteniendo gastos internet: {e}")
            return []
    
    def guardar_gasto_internet(self, gasto: dict) -> dict:
        """Guarda un nuevo gasto de internet."""
        if not self.connect():
            return {"success": False, "error": "No se pudo conectar a la base de datos"}
        
        try:
            doc = {
                'razon': gasto.get('razon', ''),
                'nombre': gasto.get('nombre', ''),
                'tipo': gasto.get('tipo', 'mensualidad'),
                'fecha_pago': gasto.get('fecha_pago', ''),
                'fecha_creacion': datetime.utcnow().isoformat(),
                'valor': gasto.get('valor', 0),
                'descripcion': gasto.get('descripcion', ''),
                'whatsapp': gasto.get('whatsapp', ''),
                'pagado': gasto.get('pagado', True),
                'proveedor_id': gasto.get('proveedor_id', '')
            }
            
            result = self.db.gastos_internet.insert_one(doc)
            
            return {"success": result.inserted_id is not None, "id": str(result.inserted_id)}
        except Exception as e:
            print(f"❌ Error guardando gasto internet: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # GASTOS DE GASOLINA
    # ============================================================
    
    def obtener_gastos_gasolina(self, year: int, month: int) -> list:
        """Obtiene gastos de gasolina del mes especificado."""
        if not self.connect():
            return []
        
        try:
            inicio_mes = f"{year}-{str(month).zfill(2)}-01"
            if month == 12:
                fin_mes = f"{year + 1}-01-01"
            else:
                fin_mes = f"{year}-{str(month + 1).zfill(2)}-01"
            
            cursor = self.db.gastos_gasolina.find({
                'fecha_pago': {'$gte': inicio_mes, '$lt': fin_mes}
            }).sort('fecha_pago', -1)
            
            gastos = []
            for doc in cursor:
                gastos.append({
                    'id': str(doc.get('_id')),
                    'razon': doc.get('razon', ''),
                    'nombre': doc.get('nombre', ''),
                    'tipo': doc.get('tipo', ''),
                    'fecha_pago': doc.get('fecha_pago', ''),
                    'fecha_creacion': doc.get('fecha_creacion', ''),
                    'valor': doc.get('valor', 0),
                    'descripcion': doc.get('descripcion', ''),
                    'whatsapp': doc.get('whatsapp', ''),
                    'pagado': doc.get('pagado', True)
                })
            
            return gastos
        except Exception as e:
            print(f"❌ Error obteniendo gastos gasolina: {e}")
            return []
    
    def guardar_gasto_gasolina(self, gasto: dict) -> dict:
        """Guarda un nuevo gasto de gasolina."""
        if not self.connect():
            return {"success": False, "error": "No se pudo conectar a la base de datos"}
        
        try:
            doc = {
                'razon': gasto.get('razon', ''),
                'nombre': gasto.get('nombre', ''),
                'tipo': gasto.get('tipo', 'combustible'),
                'fecha_pago': gasto.get('fecha_pago', ''),
                'fecha_creacion': datetime.utcnow().isoformat(),
                'valor': gasto.get('valor', 0),
                'descripcion': gasto.get('descripcion', ''),
                'whatsapp': gasto.get('whatsapp', ''),
                'pagado': gasto.get('pagado', True),
                'proveedor_id': gasto.get('proveedor_id', '')
            }
            
            result = self.db.gastos_gasolina.insert_one(doc)
            
            return {"success": result.inserted_id is not None, "id": str(result.inserted_id)}
        except Exception as e:
            print(f"❌ Error guardando gasto gasolina: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # GASTOS DE ASEO
    # ============================================================
    
    def obtener_gastos_aseo(self, year: int, month: int) -> list:
        """Obtiene gastos de aseo del mes especificado."""
        if not self.connect():
            return []
        
        try:
            inicio_mes = f"{year}-{str(month).zfill(2)}-01"
            if month == 12:
                fin_mes = f"{year + 1}-01-01"
            else:
                fin_mes = f"{year}-{str(month + 1).zfill(2)}-01"
            
            cursor = self.db.gastos_aseo.find({
                'fecha_pago': {'$gte': inicio_mes, '$lt': fin_mes}
            }).sort('fecha_pago', -1)
            
            gastos = []
            for doc in cursor:
                gastos.append({
                    'id': str(doc.get('_id')),
                    'razon': doc.get('razon', ''),
                    'nombre': doc.get('nombre', ''),
                    'tipo': doc.get('tipo', ''),
                    'fecha_pago': doc.get('fecha_pago', ''),
                    'fecha_creacion': doc.get('fecha_creacion', ''),
                    'valor': doc.get('valor', 0),
                    'descripcion': doc.get('descripcion', ''),
                    'whatsapp': doc.get('whatsapp', ''),
                    'pagado': doc.get('pagado', True)
                })
            
            return gastos
        except Exception as e:
            print(f"❌ Error obteniendo gastos aseo: {e}")
            return []
    
    def guardar_gasto_aseo(self, gasto: dict) -> dict:
        """Guarda un nuevo gasto de aseo."""
        if not self.connect():
            return {"success": False, "error": "No se pudo conectar a la base de datos"}
        
        try:
            doc = {
                'razon': gasto.get('razon', ''),
                'nombre': gasto.get('nombre', ''),
                'tipo': gasto.get('tipo', 'limpieza'),
                'fecha_pago': gasto.get('fecha_pago', ''),
                'fecha_creacion': datetime.utcnow().isoformat(),
                'valor': gasto.get('valor', 0),
                'descripcion': gasto.get('descripcion', ''),
                'whatsapp': gasto.get('whatsapp', ''),
                'pagado': gasto.get('pagado', True),
                'proveedor_id': gasto.get('proveedor_id', '')
            }
            
            result = self.db.gastos_aseo.insert_one(doc)
            
            return {"success": result.inserted_id is not None, "id": str(result.inserted_id)}
        except Exception as e:
            print(f"❌ Error guardando gasto aseo: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # PROVEEDORES
    # ============================================================
    
    def obtener_proveedores(self, tipo: str = None) -> list:
        """Obtiene lista de proveedores, opcionalmente filtrado por tipo."""
        if not self.connect():
            return []
        
        try:
            filtro = {}
            if tipo:
                filtro['tipo'] = tipo
            
            cursor = self.db.proveedores.find(filtro).sort('nombre', 1)
            
            proveedores = []
            for doc in cursor:
                proveedores.append({
                    'id': str(doc.get('_id')),
                    'nombre': doc.get('nombre', ''),
                    'servicio': doc.get('servicio', ''),
                    'tipo': doc.get('tipo', ''),
                    'banco': doc.get('banco', ''),
                    'rut': doc.get('rut', ''),
                    'tipo_cuenta': doc.get('tipo_cuenta', ''),
                    'numero_cuenta': doc.get('numero_cuenta', ''),
                    'email': doc.get('email', ''),
                    'whatsapp': doc.get('whatsapp', '')
                })
            
            return proveedores
        except Exception as e:
            print(f"❌ Error obteniendo proveedores: {e}")
            return []
    
    def guardar_proveedor(self, proveedor: dict) -> dict:
        """Guarda un nuevo proveedor."""
        if not self.connect():
            return {"success": False, "error": "No se pudo conectar"}
        
        try:
            doc = {
                'nombre': proveedor.get('nombre', ''),
                'servicio': proveedor.get('servicio', ''),
                'tipo': proveedor.get('tipo', ''),
                'banco': proveedor.get('banco', ''),
                'rut': proveedor.get('rut', ''),
                'tipo_cuenta': proveedor.get('tipo_cuenta', ''),
                'numero_cuenta': proveedor.get('numero_cuenta', ''),
                'email': proveedor.get('email', ''),
                'whatsapp': proveedor.get('whatsapp', ''),
                'fecha_creacion': datetime.utcnow().isoformat()
            }
            
            result = self.db.proveedores.insert_one(doc)
            return {"success": True, "id": str(result.inserted_id)}
        except Exception as e:
            print(f"❌ Error guardando proveedor: {e}")
            return {"success": False, "error": str(e)}


# Instancia singleton
db_service = DatabaseService()
