"""
Airbnb Agent - Calendario Visual de Reservas
Solo endpoints Flask - lógica en services/
"""
import os
import calendar
import tomllib
import secrets
from pathlib import Path
from datetime import datetime, date, timedelta
from functools import wraps
from zoneinfo import ZoneInfo
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from dotenv import load_dotenv

from .services.airbnb_calendar import airbnb_service
from .services.database import db_service

load_dotenv()

# Configurar Flask
BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, 
            template_folder=str(BASE_DIR / 'templates'),
            static_folder=str(BASE_DIR / 'static'))

# Secret key para sesiones
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Autenticación
AUTH_USERNAME = os.getenv('AUTH_USERNAME', 'admin')
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD', 'admin')

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
TIMEZONE = os.getenv('TIMEZONE', 'America/Santiago')


def _now_local():
    """Fecha/hora actual en la zona horaria de la propiedad (evita desfase en producción UTC)."""
    return datetime.now(ZoneInfo(TIMEZONE))

MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _calcular_ingresos_mes_reservas(
    all_events: list,
    year: int,
    month: int,
) -> tuple[int, int, int, int]:
    """
    Calcula ingresos del mes (arriendo, tinaja, pagado, próximos) usando la misma
    lógica que el calendario (event.end = checkout día INCLUSIVO).
    Devuelve: (ingreso_arriendo, ingreso_tinaja, ingreso_pagado, ingreso_proximos)
    """
    inicio_mes = date(year, month, 1)
    fin_mes = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    hoy = date.today()

    ingreso_arriendo = 0
    ingreso_tinaja = 0
    ingreso_pagado = 0
    ingreso_proximos = 0

    for ev in all_events:
        if ev.get('estado') == 'eliminado' or ev.get('estado') != 'reservado':
            continue
        try:
            ev_start = date.fromisoformat(ev.get('start', ''))
            ev_end = date.fromisoformat(ev.get('end', ''))
            # event.end = checkout día INCLUSIVO (igual que calendario)
            if ev_start >= fin_mes or ev_end < inicio_mes:
                continue
            # dias_totales = (end - start).days + 1 (calendario)
            dias_totales = max(1, (ev_end - ev_start).days + 1)
            # endInclusive = end + 1 día; overlap_end = min(endInclusive, fin_mes)
            ev_end_excl = ev_end + timedelta(days=1)
            overlap_start = max(ev_start, inicio_mes)
            overlap_end = min(ev_end_excl, fin_mes)
            dias_en_mes = max(0, (overlap_end - overlap_start).days)
            proporcion = dias_en_mes / dias_totales
            precio = round((ev.get('precio', 0) or 0) * proporcion)
            extra = round((ev.get('extra_valor', 0) or 0) * proporcion)
            ingreso_arriendo += precio
            ingreso_tinaja += extra
            if ev_end < hoy:
                ingreso_pagado += precio + extra
            else:
                ingreso_proximos += precio + extra
        except Exception:
            pass

    return ingreso_arriendo, ingreso_tinaja, ingreso_pagado, ingreso_proximos


def get_audit_info() -> dict:
    """Obtiene info de auditoría del request."""
    try:
        return {
            "user_origin": request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown'),
            "user_agent": request.headers.get('User-Agent', 'unknown')
        }
    except:
        return {"user_origin": "system", "user_agent": "system"}


def get_month_calendar(year: int, month: int, include_events: bool = False) -> dict:
    """Genera datos del calendario para un mes."""
    cal = calendar.Calendar(firstweekday=0)
    result = {
        'year': year,
        'month': month,
        'month_name': MESES_ES[month],
        'days': list(cal.itermonthdays2(year, month))
    }
    
    # Incluir eventos e ingresos si se solicita
    if include_events:
        inicio_mes = date(year, month, 1)
        if month == 12:
            fin_mes = date(year + 1, 1, 1)
        else:
            fin_mes = date(year, month + 1, 1)

        all_events = db_service.obtener_eventos_formato_ical()
        events_mes = []
        for ev in all_events:
            try:
                ev_start = date.fromisoformat(ev.get('start', ''))
                ev_end = date.fromisoformat(ev.get('end', ''))
                if ev_start < fin_mes and ev_end >= inicio_mes:
                    events_mes.append(ev)
            except Exception:
                pass
        result['events'] = events_mes

        # Ingresos del mes (misma lógica que desempeño/calendario)
        arriendo, tinaja, _, _ = _calcular_ingresos_mes_reservas(all_events, year, month)
        result['ingresos'] = {
            'arriendo': arriendo,
            'tinaja': tinaja,
            'total': arriendo + tinaja,
        }

    return result


def login_required(f):
    """Decorador para proteger rutas que requieren autenticación."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# AUTENTICACIÓN
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login."""
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == AUTH_USERNAME and password == AUTH_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('home'))
        else:
            error = 'Usuario o contraseña incorrectos'
    
    return render_template('login.html', error=error, version=APP_VERSION)


@app.route('/logout')
def logout():
    """Cerrar sesión."""
    session.clear()
    return redirect(url_for('home'))


# ============================================================
# ENDPOINTS
# ============================================================

@app.route('/')
def home():
    """Página principal."""
    # 1. Sincronizar desde iCal en background (si está disponible)
    ical_events = airbnb_service.fetch_events()
    if ical_events:
        db_service.sync_en_background(ical_events, get_audit_info())
    
    # 2. Mostrar siempre desde MongoDB (fuente principal)
    events = db_service.obtener_eventos_formato_ical()
    
    # 3. Fallback a iCal solo si MongoDB está vacío
    if not events and ical_events:
        events = ical_events
    
    stats = airbnb_service.get_stats(events)

    now = _now_local()
    current = get_month_calendar(now.year, now.month)
    arriendo, tinaja, _, _ = _calcular_ingresos_mes_reservas(events, now.year, now.month)
    ingresos_mes_actual = {'arriendo': arriendo, 'tinaja': tinaja, 'total': arriendo + tinaja}

    is_logged_in = session.get('logged_in', False)

    return render_template('calendar.html',
                         events=events,
                         stats=stats,
                         current=current,
                         ingresos_mes_actual=ingresos_mes_actual,
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME,
                         is_logged_in=is_logged_in,
                         today=now.strftime('%Y-%m-%d'),
                         now_time=now.strftime('%H:%M'))


@app.route('/desempeno')
@login_required
def desempeno():
    """Vista de desempeño financiero (ingresos/gastos por mes)."""
    now = datetime.now()
    return render_template('desempeno.html',
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME,
                         current_year=now.year,
                         current_month=now.month)


@app.route('/api/desempeno')
@login_required
def api_desempeno():
    """API: Datos de desempeño mensual (ingresos, gastos, pagado/próximos)."""
    year = request.args.get('year', datetime.now().year, type=int)

    all_events = db_service.obtener_eventos_formato_ical()
    gastos_por_mes = db_service.obtener_gastos_agregados_anio(year)

    meses_data = []
    for mes in range(1, 13):
        ingreso_arriendo, ingreso_tinaja, ingreso_pagado, ingreso_proximos = _calcular_ingresos_mes_reservas(
            all_events, year, mes
        )

        g = gastos_por_mes.get(mes, {})
        gasto_agua = g.get('agua', 0)
        gasto_internet = g.get('internet', 0)
        gasto_gasolina = g.get('gasolina', 0)
        gasto_aseo = g.get('aseo', 0)
        gasto_pagado = g.get('pagado', 0)
        gasto_proximos = g.get('proximos', 0)

        total_ingresos = ingreso_arriendo + ingreso_tinaja
        total_gastos = gasto_agua + gasto_internet + gasto_gasolina + gasto_aseo

        meses_data.append({
            'mes': mes,
            'anio': year,
            'arriendo': ingreso_arriendo,
            'tinaja': ingreso_tinaja,
            'agua': gasto_agua,
            'internet': gasto_internet,
            'gasolina': gasto_gasolina,
            'aseo': gasto_aseo,
            'ingreso_pagado': ingreso_pagado,
            'ingreso_proximos': ingreso_proximos,
            'gasto_pagado': gasto_pagado,
            'gasto_proximos': gasto_proximos,
            'total_ingresos': total_ingresos,
            'total_gastos': total_gastos,
            'neto': total_ingresos - total_gastos,
        })

    return jsonify({'meses': meses_data, 'year': year})


@app.route('/api/month')
def api_month():
    """API: Datos de un mes específico con eventos."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    return jsonify(get_month_calendar(year, month, include_events=True))


@app.route('/api/promedio-anual')
def api_promedio_anual():
    """API: Calcula el promedio de ingresos de meses cerrados (dic anterior + meses hasta hoy)."""
    hoy = date.today()
    anio_hoy = hoy.year
    mes_hoy = hoy.month
    
    # Obtener todos los eventos
    all_events = db_service.obtener_eventos_formato_ical()
    
    # Meses a calcular: diciembre año anterior + meses cerrados del año actual
    meses_cerrados = [{'mes': 12, 'anio': anio_hoy - 1}]
    for m in range(1, mes_hoy):
        meses_cerrados.append({'mes': m, 'anio': anio_hoy})
    
    resultados = []
    
    for mc in meses_cerrados:
        mes = mc['mes']
        anio = mc['anio']
        arriendo, tinaja, _, _ = _calcular_ingresos_mes_reservas(all_events, anio, mes)
        ingresos = arriendo + tinaja
        resultados.append({'mes': mes, 'anio': anio, 'ingresos': ingresos})
    
    total_ingresos = sum(r['ingresos'] for r in resultados)
    promedio = total_ingresos / len(resultados) if resultados else 0
    
    return jsonify({
        'meses_cerrados': resultados,
        'total_ingresos': total_ingresos,
        'promedio': round(promedio),
        'cantidad_meses': len(resultados)
    })


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


@app.route('/api/reserva/<reserva_id>/eliminar', methods=['POST'])
@login_required
def api_eliminar_reserva(reserva_id):
    """API: Eliminar reserva (lógico)."""
    resultado = db_service.eliminar_reserva(reserva_id, get_audit_info())
    return jsonify({"success": resultado})


@app.route('/api/reserva/<reserva_id>/restaurar', methods=['POST'])
@login_required
def api_restaurar_reserva(reserva_id):
    """API: Restaurar reserva eliminada."""
    resultado = db_service.restaurar_reserva(reserva_id, get_audit_info())
    return jsonify({"success": resultado})


@app.route('/api/reserva/<reserva_id>/finalizar', methods=['POST'])
@login_required
def api_finalizar_estadia(reserva_id):
    """API: Finalizar estadía (cliente se retiró)."""
    resultado = db_service.finalizar_estadia(reserva_id, get_audit_info())
    return jsonify(resultado)


@app.route('/api/reserva/por-fecha/<fecha>')
@login_required
def api_reserva_por_fecha(fecha):
    """API: Obtener reserva por fecha."""
    reserva = db_service.buscar_reserva_por_fecha(fecha)
    if reserva:
        return jsonify({
            "found": True,
            "id": str(reserva.get('_id', '')),
            "event_start": reserva.get('event_start', ''),
            "event_end": reserva.get('event_end', ''),
            "estado": reserva.get('estado', 'bloqueado'),
            "summary": reserva.get('summary', ''),
            "reservation_url": reserva.get('reservation_url', ''),
            "readonly": reserva.get('readonly', False),
            "source": reserva.get('source', ''),
            "hora_checkin": reserva.get('hora_checkin', ''),
            "hora_checkout": reserva.get('hora_checkout', ''),
            "nombre_huesped": reserva.get('nombre_huesped', ''),
            "adultos": reserva.get('adultos', 0),
            "ninos": reserva.get('ninos', 0),
            "mascotas": reserva.get('mascotas', 0),
            "notas": reserva.get('notas', ''),
            "precio": reserva.get('precio', 0),
            "extra_concepto": reserva.get('extra_concepto', ''),
            "extra_valor": reserva.get('extra_valor', 0),
            "comuna": reserva.get('comuna', ''),
            "pais": reserva.get('pais', '')
        })
    return jsonify({"found": False, "fecha": fecha})


@app.route('/api/reserva/guardar', methods=['POST'])
@login_required
def api_guardar_reserva():
    """API: Guardar/actualizar reserva."""
    data = request.get_json()
    
    datos = {
        'event_start': data.get('event_start'),
        'event_end': data.get('event_end'),
        'estado': data.get('estado', 'bloqueado'),
        'summary': data.get('summary', ''),
        'reservation_url': data.get('reservation_url') or None,
        'readonly': data.get('readonly', False),
        'source': 'admin',
        'hora_checkin': data.get('hora_checkin', ''),
        'hora_checkout': data.get('hora_checkout', ''),
        'nombre_huesped': data.get('nombre_huesped', ''),
        'adultos': data.get('adultos', 0),
        'ninos': data.get('ninos', 0),
        'mascotas': data.get('mascotas', 0),
        'notas': data.get('notas', ''),
        'precio': data.get('precio', 0),
        'extra_concepto': data.get('extra_concepto', ''),
        'extra_valor': data.get('extra_valor', 0),
        'comuna': data.get('comuna', ''),
        'pais': data.get('pais', '')
    }
    
    if datos['event_start'] >= datos['event_end']:
        return jsonify({"success": False, "error": "Check-out debe ser posterior a check-in"})
    
    reserva_id = data.get('id', '')
    resultado = db_service.guardar_reserva_manual(reserva_id, datos, get_audit_info())
    return jsonify(resultado)


@app.route('/admin/reserva', methods=['GET', 'POST'])
@login_required
def admin_reserva():
    """Página para crear/editar reservas (solo admin)."""
    from bson import ObjectId
    
    error = None
    success = None
    reserva = None
    
    # Obtener fecha del parámetro o reserva existente
    fecha = request.args.get('fecha', '')
    reserva_id = request.args.get('id', '')
    
    # Si hay ID, cargar la reserva existente
    if reserva_id:
        reserva = db_service.obtener_reserva_por_id(reserva_id)
        if reserva:
            fecha = reserva.get('event_start', fecha)
    
    # Si hay fecha, buscar si existe reserva en ese día
    if fecha and not reserva:
        reserva = db_service.buscar_reserva_por_fecha(fecha)
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'delete':
            # Eliminar reserva
            rid = request.form.get('reserva_id', '')
            if rid:
                resultado = db_service.eliminar_reserva(rid, get_audit_info())
                if resultado:
                    return redirect(url_for('home'))
                error = 'Error al eliminar la reserva'
        else:
            # Crear/actualizar reserva
            datos = {
                'event_start': request.form.get('event_start'),
                'event_end': request.form.get('event_end'),
                'estado': request.form.get('estado'),
                'summary': request.form.get('summary', ''),
                'reservation_url': request.form.get('reservation_url', '') or None,
                'readonly': request.form.get('readonly') == 'on',
                'source': 'admin'
            }
            
            # Validar fechas
            if datos['event_start'] >= datos['event_end']:
                error = 'La fecha de check-out debe ser posterior al check-in'
            else:
                rid = request.form.get('reserva_id', '')
                resultado = db_service.guardar_reserva_manual(rid, datos, get_audit_info())
                
                if resultado.get('success'):
                    return redirect(url_for('home'))
                else:
                    error = resultado.get('error', 'Error al guardar')
    
    now = datetime.now()
    return render_template('reserva_edit.html',
                         reserva=reserva,
                         fecha=fecha,
                         today=now.strftime('%Y-%m-%d'),
                         property_name=PROPERTY_NAME,
                         error=error,
                         success=success)


# ============================================================
# API GASTOS DE AGUA
# ============================================================

@app.route('/api/gastos/agua', methods=['GET'])
@login_required
def obtener_gastos_agua():
    """Obtiene gastos de agua del mes especificado."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    gastos = db_service.obtener_gastos_agua(year, month)
    return jsonify({"gastos": gastos})

@app.route('/api/gastos/agua', methods=['POST'])
@login_required
def guardar_gasto_agua():
    """Guarda un nuevo gasto de agua."""
    data = request.get_json()
    
    gasto = {
        'razon': data.get('razon', ''),
        'nombre': data.get('nombre', ''),
        'tipo': data.get('tipo', 'consumo'),
        'fecha_pago': data.get('fecha_pago', ''),
        'valor': data.get('valor', 0),
        'descripcion': data.get('descripcion', ''),
        'whatsapp': data.get('whatsapp', ''),
        'pagado': data.get('pagado', True),
        'proveedor_id': data.get('proveedor_id', '')
    }
    
    resultado = db_service.guardar_gasto_agua(gasto)
    return jsonify(resultado)

@app.route('/api/gastos/agua/<gasto_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_gasto_agua_id(gasto_id):
    """PATCH: alterna pagado. DELETE: elimina el gasto."""
    if request.method == 'PATCH':
        return jsonify(db_service.toggle_pagado_gasto('gastos_agua', gasto_id))
    return jsonify(db_service.eliminar_gasto('gastos_agua', gasto_id))

# ============================================================
# API GASTOS DE INTERNET
# ============================================================

@app.route('/api/gastos/internet', methods=['GET'])
@login_required
def obtener_gastos_internet():
    """Obtiene gastos de internet del mes especificado."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    gastos = db_service.obtener_gastos_internet(year, month)
    return jsonify({"gastos": gastos})

@app.route('/api/gastos/internet', methods=['POST'])
@login_required
def guardar_gasto_internet():
    """Guarda un nuevo gasto de internet."""
    data = request.get_json()
    
    gasto = {
        'razon': data.get('razon', ''),
        'nombre': data.get('nombre', ''),
        'tipo': data.get('tipo', 'mensualidad'),
        'fecha_pago': data.get('fecha_pago', ''),
        'valor': data.get('valor', 0),
        'descripcion': data.get('descripcion', ''),
        'whatsapp': data.get('whatsapp', ''),
        'pagado': data.get('pagado', True),
        'proveedor_id': data.get('proveedor_id', '')
    }
    
    resultado = db_service.guardar_gasto_internet(gasto)
    return jsonify(resultado)

@app.route('/api/gastos/internet/<gasto_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_gasto_internet_id(gasto_id):
    if request.method == 'PATCH':
        return jsonify(db_service.toggle_pagado_gasto('gastos_internet', gasto_id))
    return jsonify(db_service.eliminar_gasto('gastos_internet', gasto_id))

# ============================================================
# API GASTOS DE GASOLINA
# ============================================================

@app.route('/api/gastos/gasolina', methods=['GET'])
@login_required
def obtener_gastos_gasolina():
    """Obtiene gastos de gasolina del mes especificado."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    gastos = db_service.obtener_gastos_gasolina(year, month)
    return jsonify({"gastos": gastos})

@app.route('/api/gastos/gasolina', methods=['POST'])
@login_required
def guardar_gasto_gasolina():
    """Guarda un nuevo gasto de gasolina."""
    data = request.get_json()
    
    gasto = {
        'razon': data.get('razon', ''),
        'nombre': data.get('nombre', ''),
        'tipo': data.get('tipo', 'combustible'),
        'fecha_pago': data.get('fecha_pago', ''),
        'valor': data.get('valor', 0),
        'descripcion': data.get('descripcion', ''),
        'whatsapp': data.get('whatsapp', ''),
        'pagado': data.get('pagado', True),
        'proveedor_id': data.get('proveedor_id', '')
    }
    
    resultado = db_service.guardar_gasto_gasolina(gasto)
    return jsonify(resultado)

@app.route('/api/gastos/gasolina/<gasto_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_gasto_gasolina_id(gasto_id):
    if request.method == 'PATCH':
        return jsonify(db_service.toggle_pagado_gasto('gastos_gasolina', gasto_id))
    return jsonify(db_service.eliminar_gasto('gastos_gasolina', gasto_id))

# ============================================================
# API GASTOS DE ASEO
# ============================================================

@app.route('/api/gastos/aseo', methods=['GET'])
@login_required
def obtener_gastos_aseo():
    """Obtiene gastos de aseo del mes especificado."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    gastos = db_service.obtener_gastos_aseo(year, month)
    return jsonify({"gastos": gastos})

@app.route('/api/gastos/aseo', methods=['POST'])
@login_required
def guardar_gasto_aseo():
    """Guarda un nuevo gasto de aseo."""
    data = request.get_json()
    
    gasto = {
        'razon': data.get('razon', ''),
        'nombre': data.get('nombre', ''),
        'tipo': data.get('tipo', 'limpieza'),
        'fecha_pago': data.get('fecha_pago', ''),
        'valor': data.get('valor', 0),
        'descripcion': data.get('descripcion', ''),
        'whatsapp': data.get('whatsapp', ''),
        'pagado': data.get('pagado', True),
        'proveedor_id': data.get('proveedor_id', '')
    }
    
    resultado = db_service.guardar_gasto_aseo(gasto)
    return jsonify(resultado)

@app.route('/api/gastos/aseo/<gasto_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_gasto_aseo_id(gasto_id):
    if request.method == 'PATCH':
        return jsonify(db_service.toggle_pagado_gasto('gastos_aseo', gasto_id))
    return jsonify(db_service.eliminar_gasto('gastos_aseo', gasto_id))

# ============================================================
# API PROVEEDORES
# ============================================================

@app.route('/api/proveedores', methods=['GET'])
@login_required
def obtener_proveedores():
    """Obtiene lista de proveedores."""
    tipo = request.args.get('tipo', None)
    proveedores = db_service.obtener_proveedores(tipo)
    return jsonify({"proveedores": proveedores})

@app.route('/api/proveedores', methods=['POST'])
@login_required
def guardar_proveedor():
    """Guarda un nuevo proveedor."""
    data = request.get_json()
    resultado = db_service.guardar_proveedor(data)
    return jsonify(resultado)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
