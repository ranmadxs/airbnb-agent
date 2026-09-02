"""
Airbnb Agent - Calendario Visual de Reservas
Solo endpoints Flask - lógica en services/
"""
import hashlib
import json
import os
import calendar
import tomllib
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

# Secret key FIJA: en serverless (Vercel) cada cold start = nuevo proceso.
# Si SECRET_KEY cambia, la cookie firmada no se puede verificar → logout inesperado.
# Fallback determinista para que la sesión persista entre cold starts.
app.secret_key = os.getenv('SECRET_KEY') or hashlib.sha256(b"airbnb-agent-session-v1").hexdigest()
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = bool(os.getenv('VERCEL'))  # HTTPS en Vercel
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Autenticación
AUTH_USERNAME = os.getenv('AUTH_USERNAME', 'admin')
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD', 'admin')

# Leer versión desde pyproject.toml
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
PROPERTY_NAME = os.getenv('PROPERTY_NAME', 'Posada del Bosque')
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN', '')
MERCADOPAGO_PUBLIC_KEY = os.getenv('MERCADOPAGO_PUBLIC_KEY', '')
MERCADOPAGO_WEBHOOK_SECRET = os.getenv('MERCADOPAGO_WEBHOOK_SECRET', '')
MERCADOPAGO_LINK = os.getenv('MERCADOPAGO_LINK', 'https://link.mercadopago.cl/posadaenelbosque')
# Botones con valores fijos (modelo híbrido): valor,link por botón. JSON: [{"valor":19500,"link":"https://mpago.la/1sRuP77"},...]
_mp_botones_default = [
    {"valor": 19500, "link": "https://mpago.la/1sRuP77"},
    {"valor": 22400, "link": "https://mpago.la/23E1Z2w"},
    {"valor": 19000, "link": "https://mpago.la/2e9WCsu"},
]
try:
    MERCADOPAGO_BOTONES = json.loads(os.getenv('MERCADOPAGO_BOTONES', '[]')) or _mp_botones_default
except Exception:
    MERCADOPAGO_BOTONES = _mp_botones_default
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


def _calcular_ingresos_por_calendario(all_events: list, year: int, month: int) -> dict:
    """Subtotales de ingresos por calendario_id (para widget de Ingresos).

    Returns:
        {calendario_id_o_'__legacy__': {'arriendo': int, 'tinaja': int, 'total': int}}
    """
    inicio_mes = date(year, month, 1)
    fin_mes = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    by_cal = {}
    for ev in all_events:
        if ev.get('estado') != 'reservado':
            continue
        try:
            ev_start = date.fromisoformat(ev.get('start', ''))
            ev_end = date.fromisoformat(ev.get('end', ''))
            if ev_start >= fin_mes or ev_end < inicio_mes:
                continue
            dias_totales = max(1, (ev_end - ev_start).days + 1)
            ev_end_excl = ev_end + timedelta(days=1)
            overlap_start = max(ev_start, inicio_mes)
            overlap_end = min(ev_end_excl, fin_mes)
            dias_en_mes = max(0, (overlap_end - overlap_start).days)
            proporcion = dias_en_mes / dias_totales
            precio = round((ev.get('precio', 0) or 0) * proporcion)
            extra = round((ev.get('extra_valor', 0) or 0) * proporcion)
        except Exception:
            continue

        # Llave: calendario_id si existe, si no '__legacy__'
        cid = ev.get('calendario_id') or '__legacy__'
        slot = by_cal.setdefault(cid, {'arriendo': 0, 'tinaja': 0, 'total': 0})
        slot['arriendo'] += precio
        slot['tinaja'] += extra
        slot['total'] += precio + extra

    return by_cal


def get_audit_info() -> dict:
    """Obtiene info de auditoría del request."""
    try:
        return {
            "user_origin": request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown'),
            "user_agent": request.headers.get('User-Agent', 'unknown')
        }
    except:
        return {"user_origin": "system", "user_agent": "system"}


def get_month_calendar(year: int, month: int, include_events: bool = False,
                       calendario_ids: list = None) -> dict:
    """Genera datos del calendario para un mes.

    Args:
        calendario_ids: Lista de calendario_id a incluir (None = todos).
                       '__legacy__' incluye docs sin calendario_id.
    """
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

        all_events = db_service.obtener_eventos_formato_ical(calendario_ids=calendario_ids)
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
        # v3.0.0: subtotales por calendario
        result['ingresos_por_calendario'] = _calcular_ingresos_por_calendario(all_events, year, month)

    return result


def get_month_calendar_tinaja(year: int, month: int, include_events: bool = False) -> dict:
    """Genera datos del calendario para un mes, solo con reservas que pagaron tinaja (extra_valor > 0)."""
    cal = calendar.Calendar(firstweekday=0)
    result = {
        'year': year,
        'month': month,
        'month_name': MESES_ES[month],
        'days': list(cal.itermonthdays2(year, month))
    }

    if include_events:
        inicio_mes = date(year, month, 1)
        fin_mes = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        all_events = db_service.obtener_eventos_formato_ical()
        events_tinaja = [
            ev for ev in all_events
            if ev.get('estado') == 'reservado'
            and (ev.get('extra_valor') or 0) > 0
        ]

        events_mes = []
        for ev in events_tinaja:
            try:
                ev_start = date.fromisoformat(ev.get('start', ''))
                ev_end = date.fromisoformat(ev.get('end', ''))
                if ev_start < fin_mes and ev_end >= inicio_mes:
                    events_mes.append(ev)
            except Exception:
                pass
        result['events'] = events_mes

        _, tinaja_ingreso, _, _ = _calcular_ingresos_mes_reservas(events_tinaja, year, month)
        result['ingresos'] = {'tinaja': tinaja_ingreso, 'total': tinaja_ingreso}

    return result


def login_required(f):
    """Decorador para proteger rutas que requieren autenticación."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'No autorizado'}), 401
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
    next_url = request.args.get('next', '').strip()
    if next_url and not next_url.startswith('/'):
        next_url = ''
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == AUTH_USERNAME and password == AUTH_PASSWORD:
            session.permanent = True
            session['logged_in'] = True
            session['username'] = username
            next_from_form = request.form.get('next', '').strip()
            if next_from_form and next_from_form.startswith('/'):
                return redirect(next_from_form)
            if next_url:
                return redirect(next_url)
            return redirect(url_for('home'))
        else:
            error = 'Usuario o contraseña incorrectos'
    
    return render_template('login.html',
                         error=error,
                         version=APP_VERSION,
                         next_url=next_url,
                         property_name=PROPERTY_NAME)


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
    # v3.0.1: Respetar ?cal=... del query string para deep links
    # (ej. https://.../?cal=santiago_magno). Si está, filtramos los
    # eventos desde el render inicial. Si no, dejamos todos.
    cal_param = request.args.get('cal', '').strip()
    calendario_ids_inicial = None
    include_legacy_inicial = False
    if cal_param:
        raw_ids = [c.strip() for c in cal_param.split(',') if c.strip()]
        # Filtrar solo ids válidos contra los calendarios configurados
        valid_ids = {c['calendario_id'] for c in airbnb_service.calendars}
        valid_raw = [cid for cid in raw_ids if cid != '__legacy__' and cid in valid_ids]
        include_legacy_inicial = '__legacy__' in raw_ids
        # Mantener `__legacy__` dentro de la lista para que
        # `obtener_eventos_formato_ical()` lo maneje en su query Mongo.
        calendario_ids_inicial = valid_raw + (['__legacy__'] if include_legacy_inicial else [])

    # 1. Leer MongoDB PRIMERO para evitar race condition con el sync en background.
    #    Si se leyera DESPUÉS de disparar el sync, el thread podría estar escribiendo
    #    simultáneamente y el render mostraría datos inconsistentes.
    events = db_service.obtener_eventos_formato_ical(calendario_ids=calendario_ids_inicial)

    # 2. Sincronizar desde iCal en background (actualiza MongoDB para la PRÓXIMA carga)
    ical_events = airbnb_service.fetch_events()
    if ical_events is not None:
        db_service.sync_en_background(ical_events, get_audit_info())

    # 3. Fallback a iCal solo si MongoDB está vacío y el fetch fue exitoso.
    #    Si había filtro activo, aplicarlo también al fallback.
    if not events and ical_events:
        events = ical_events
        if cal_param:
            eventos_filtrados = []
            for ev in ical_events:
                cid = ev.get('calendario_id')
                if cid is None or cid == '':
                    if include_legacy_inicial:
                        eventos_filtrados.append(ev)
                elif calendario_ids_inicial is None or cid in calendario_ids_inicial:
                    eventos_filtrados.append(ev)
            events = eventos_filtrados

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


@app.route('/reservatinaja-ingresar')
@login_required
def reservatinaja_ingresar():
    """Página admin: ingresar código para obtener link de pago tinaja."""
    return render_template('reservatinaja_ingresar.html',
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME)


@app.route('/reservatinaja/<codigo_reserva>')
def reservatinaja(codigo_reserva):
    """Página pública: tutorial 3 pasos para reservar tinaja por código de reserva."""
    reserva = db_service.obtener_reserva_por_codigo(codigo_reserva)
    # Reintentar una vez si falla (p. ej. conexión MongoDB no lista en cold start)
    if not reserva:
        db_service.get_status()  # fuerza reconexión si hace falta
        reserva = db_service.obtener_reserva_por_codigo(codigo_reserva)
    if not reserva or reserva.get('estado') != 'reservado':
        return render_template('reservatinaja.html',
                             reserva=None,
                             fechas=[],
                             error='Reserva no encontrada o no disponible',
                             tinaja_reservada=False,
                             puede_cancelar=False,
                             version=APP_VERSION,
                             property_name=PROPERTY_NAME,
                             mercadopago_botones=MERCADOPAGO_BOTONES,
                             mercadopago_link=MERCADOPAGO_LINK,
                             )

    start = date.fromisoformat(reserva['event_start'])
    end = date.fromisoformat(reserva['event_end'])
    noches = (end - start).days
    fechas_todas = [start + timedelta(days=i) for i in range(noches)]

    # Fecha tope: 1 día antes del check-in (último día para reservar)
    fecha_tope = start - timedelta(days=1)
    # Fecha tope para cancelar: 2 días antes del check-in
    fecha_cancelar_tope = start - timedelta(days=2)
    hoy = _now_local().date()  # Usar zona horaria de la propiedad (evita desfase UTC)

    # Si ya tiene tinaja reservada (extra_valor > 0): mostrar estado y opción de cancelar
    tinaja_reservada = (reserva.get('extra_valor') or 0) > 0
    puede_cancelar = tinaja_reservada and hoy <= fecha_cancelar_tope

    if tinaja_reservada:
        return render_template('reservatinaja.html',
                             reserva=reserva,
                             fechas=[],
                             noches=noches,
                             tinaja_reservada=True,
                             puede_cancelar=puede_cancelar,
                             fecha_cancelar_tope=fecha_cancelar_tope.strftime('%Y-%m-%d'),
                             fecha_tope=fecha_tope.strftime('%Y-%m-%d'),
                             hoy=hoy.strftime('%Y-%m-%d'),
                             puede_reservar=False,
                             version=APP_VERSION,
                             property_name=PROPERTY_NAME,
                             mercadopago_botones=MERCADOPAGO_BOTONES,
                             mercadopago_link=MERCADOPAGO_LINK,
                             )

    # No permitir reservar si ya pasó la fecha tope
    if hoy > fecha_tope:
        return render_template('reservatinaja.html',
                             reserva=reserva,
                             fechas=[],
                             noches=noches,
                             fecha_tope=fecha_tope.strftime('%Y-%m-%d'),
                             hoy=hoy.strftime('%Y-%m-%d'),
                             puede_reservar=False,
                             tinaja_reservada=False,
                             puede_cancelar=False,
                             error=None,
                             version=APP_VERSION,
                             property_name=PROPERTY_NAME,
                             mercadopago_botones=MERCADOPAGO_BOTONES,
                             mercadopago_link=MERCADOPAGO_LINK,
                             )

    # Filtrar fechas pasadas (solo noches futuras o de hoy)
    fechas = [f for f in fechas_todas if f >= hoy]

    DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    fechas_info = []
    for f in fechas:
        fechas_info.append({
            'fecha': f.strftime('%Y-%m-%d'),
            'dia': f.day,
            'mes': MESES_ES[f.month],
            'anio': f.year,
            'dia_semana': DIAS_SEMANA[f.weekday()],
        })

    return render_template('reservatinaja.html',
                         reserva=reserva,
                         fechas=fechas_info,
                         noches=noches,
                         paso=1,
                         fecha_tope=fecha_tope.strftime('%Y-%m-%d'),
                         hoy=hoy.strftime('%Y-%m-%d'),
                         puede_reservar=True,
                         tinaja_reservada=False,
                         puede_cancelar=False,
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME,
                         mercadopago_botones=MERCADOPAGO_BOTONES,
                         mercadopago_link=MERCADOPAGO_LINK,
                         )


def _validar_firma_webhook_mp(payment_id: str, x_signature: str, x_request_id: str, secret: str) -> bool:
    """Valida x-signature de MercadoPago. Manifest: id:{id};request-id:{req_id};ts:{ts};"""
    if not secret:
        return True  # Sin secret configurado, no validar
    if not x_signature:
        return False
    import hmac
    import hashlib
    parts = {p.split('=')[0]: p.split('=', 1)[1] for p in x_signature.split(',') if '=' in p}
    ts = parts.get('ts', '')
    v1 = parts.get('v1', '')
    if not ts or not v1:
        return False
    manifest = f"id:{payment_id};request-id:{x_request_id};ts:{ts};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@app.route('/api/mercadopago/webhook', methods=['POST'])
def api_mercadopago_webhook():
    """
    Webhook para notificaciones de MercadoPago (payment.created, payment.updated).
    Configurar en Tus integraciones > Webhooks > Pagos.
    URL: https://tudominio.com/api/mercadopago/webhook
    Clave secreta: MERCADOPAGO_WEBHOOK_SECRET en .env
    Logs: webhook_logs (debugging) y mercadopago_webhooks (historial de payload crudo).
    """
    raw_body = request.get_json() or {}
    payment_id = request.args.get('data.id') or raw_body.get('data', {}).get('id')
    if not payment_id:
        return jsonify({"ok": False, "error": "No payment id"}), 400

    # Historial: guardar payload crudo en mercadopago_webhooks (sin relaciones)
    query_params = dict(request.args) if request.args else {}
    headers_sel = {
        "x-signature": request.headers.get("x-signature", ""),
        "x-request-id": request.headers.get("x-request-id", ""),
        "content-type": request.headers.get("content-type", ""),
    }
    db_service.guardar_webhook_mercadopago(
        mp_payment_id=str(payment_id),
        raw_payload=raw_body,
        query_params=query_params,
        headers=headers_sel,
    )

    if MERCADOPAGO_WEBHOOK_SECRET:
        x_sig = request.headers.get('x-signature', '')
        x_req = request.headers.get('x-request-id', '')
        if not _validar_firma_webhook_mp(payment_id, x_sig, x_req, MERCADOPAGO_WEBHOOK_SECRET):
            return jsonify({"ok": False, "error": "Firma inválida"}), 401
    if not MERCADOPAGO_ACCESS_TOKEN:
        db_service.log_webhook_mp(payment_id, raw_body, {}, None, False, "MERCADOPAGO_ACCESS_TOKEN no configurado")
        return jsonify({"ok": True}), 200
    try:
        import mercadopago
        sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)
        result = sdk.payment().get(payment_id)
        payment = result.get("response", {})
        status = payment.get("status")
        if status != "approved":
            db_service.log_webhook_mp(payment_id, raw_body, payment, status or "empty", False, f"status={status}")
            return jsonify({"ok": True, "status": status}), 200
        valor = int(payment.get("transaction_amount", 0) or 0)
        external_ref = (payment.get("external_reference") or "").strip()
        payer = payment.get("payer", {})
        email = (payer.get("email") or "").strip()
        res = db_service.confirmar_pago_mercadopago(
            valor=valor,
            email=email or None,
            external_reference=external_ref or None,
            mp_payment_id=str(payment_id),
        )
        if res.get("success"):
            db_service.log_webhook_mp(payment_id, raw_body, payment, status, True)
            return jsonify({"ok": True, "matched": True, "reserva_id": res.get("reserva_id")}), 200
        err = res.get("error", "No match")
        db_service.log_webhook_mp(payment_id, raw_body, payment, status, False, err)
        return jsonify({"ok": True, "matched": False, "msg": err}), 200
    except Exception as e:
        print(f"❌ Webhook MP error: {e}")
        db_service.log_webhook_mp(payment_id, raw_body, {}, None, False, str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/reservatinaja/<codigo_reserva>/cancelar', methods=['POST'])
def api_reservatinaja_cancelar(codigo_reserva):
    """API: Cancela la tinaja de una reserva. Solo si hoy <= check-in - 2 días."""
    reserva = db_service.obtener_reserva_por_codigo(codigo_reserva)
    if not reserva or reserva.get('estado') != 'reservado':
        return jsonify({"success": False, "error": "Reserva no encontrada"})
    if not reserva.get('extra_pago_confirmado') or (reserva.get('extra_valor') or 0) <= 0:
        return jsonify({"success": False, "error": "No hay tinaja reservada para cancelar"})
    start = date.fromisoformat(reserva['event_start'])
    fecha_cancelar_tope = start - timedelta(days=2)
    if _now_local().date() > fecha_cancelar_tope:
        return jsonify({"success": False, "error": "Ya no puedes cancelar. El plazo era hasta 2 días antes del check-in."})
    resultado = db_service.cancelar_tinaja_reserva(str(reserva['_id']))
    return jsonify(resultado)


@app.route('/api/reservatinaja/<codigo_reserva>/confirmar', methods=['POST'])
def api_reservatinaja_confirmar(codigo_reserva):
    """API: Confirma y registra el pago de tinaja: crea/busca persona, transacción, actualiza reserva."""
    data = request.get_json() or {}
    valor = int(data.get('valor', 0) or 0)
    if valor <= 0:
        return jsonify({"success": False, "error": "Valor inválido"})

    reserva = db_service.obtener_reserva_por_codigo(codigo_reserva)
    if not reserva or reserva.get('estado') != 'reservado':
        return jsonify({"success": False, "error": "Reserva no encontrada"})

    email = (data.get('email') or '').strip()
    whatsapp = (data.get('whatsapp') or '').strip()
    forma_pago = data.get('forma_pago') or 'transferencia'
    if forma_pago not in ('airbnb', 'transferencia', 'mercadopago'):
        forma_pago = 'transferencia'

    if not email and not whatsapp:
        return jsonify({"success": False, "error": "Indica al menos email o WhatsApp"})

    # 1. Crear o buscar persona (contacto)
    persona_id = db_service.crear_o_buscar_persona(
        email=email or None,
        whatsapp=whatsapp or None,
        nombre=reserva.get('nombre_huesped')
    )
    if not persona_id:
        return jsonify({"success": False, "error": "No se pudo crear el contacto"})

    # 2. Crear transacción
    res_tx = db_service.registrar_transaccion_tinaja(
        reserva_id=str(reserva['_id']),
        persona_id=persona_id,
        valor=valor,
        concepto=data.get('concepto', 'Tinaja'),
        forma_pago=forma_pago,
        extra_email=email or None,
        extra_whatsapp=whatsapp or None,
    )
    if not res_tx.get('success'):
        return jsonify(res_tx)

    # 3. Actualizar reserva (extra_valor, extra_email, extra_whatsapp)
    resultado = db_service.actualizar_tinaja_reserva(
        str(reserva['_id']), valor, data.get('concepto', 'Tinaja'),
        email=email or None, whatsapp=whatsapp or None
    )
    return jsonify(resultado)


@app.route('/tinaja')
def tinaja():
    """Página pública: calendario de reservas con tinaja (solo las que pagaron extra)."""
    events = db_service.obtener_eventos_formato_ical()
    events_tinaja = [
        ev for ev in events
        if ev.get('estado') == 'reservado' and (ev.get('extra_valor') or 0) > 0
    ]

    now = _now_local()
    current = get_month_calendar_tinaja(now.year, now.month)
    _, tinaja_ingreso, _, _ = _calcular_ingresos_mes_reservas(events_tinaja, now.year, now.month)
    ingresos_mes_actual = {'tinaja': tinaja_ingreso, 'total': tinaja_ingreso}

    return render_template('tinaja.html',
                         events=events_tinaja,
                         current=current,
                         ingresos_mes_actual=ingresos_mes_actual,
                         version=APP_VERSION,
                         property_name=PROPERTY_NAME,
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

    ical_events = airbnb_service.fetch_events()
    if ical_events is not None:
        db_service.sync_en_background(ical_events, get_audit_info())

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
        gasto_otros = g.get('otros', 0)
        gasto_electricidad = g.get('electricidad', 0)
        gasto_pagado = g.get('pagado', 0)
        gasto_proximos = g.get('proximos', 0)

        total_ingresos = ingreso_arriendo + ingreso_tinaja
        total_gastos = gasto_agua + gasto_internet + gasto_gasolina + gasto_aseo + gasto_otros + gasto_electricidad

        # Contar reservas y personas por mes de CHECKIN (evita doble conteo en reservas cruzadas)
        mes_str = f'{year}-{str(mes).zfill(2)}'
        num_reservas = 0
        num_reservas_tinaja = 0
        total_adultos = 0
        total_ninos = 0
        total_mascotas = 0
        for ev in all_events:
            if ev.get('estado') != 'reservado':
                continue
            if (ev.get('start') or '').startswith(mes_str):
                num_reservas += 1
                if (ev.get('extra_valor', 0) or 0) > 0:
                    num_reservas_tinaja += 1
                total_adultos += ev.get('adultos', 0) or 0
                total_ninos += ev.get('ninos', 0) or 0
                total_mascotas += ev.get('mascotas', 0) or 0

        meses_data.append({
            'mes': mes,
            'anio': year,
            'arriendo': ingreso_arriendo,
            'tinaja': ingreso_tinaja,
            'agua': gasto_agua,
            'internet': gasto_internet,
            'gasolina': gasto_gasolina,
            'aseo': gasto_aseo,
            'otros': gasto_otros,
            'electricidad': gasto_electricidad,
            'num_reservas': num_reservas,
            'num_reservas_tinaja': num_reservas_tinaja,
            'adultos': total_adultos,
            'ninos': total_ninos,
            'mascotas': total_mascotas,
            'ingreso_pagado': ingreso_pagado,
            'ingreso_proximos': ingreso_proximos,
            'gasto_pagado': gasto_pagado,
            'gasto_proximos': gasto_proximos,
            'total_ingresos': total_ingresos,
            'total_gastos': total_gastos,
            'neto': total_ingresos - total_gastos,
        })

    return jsonify({'meses': meses_data, 'year': year})


@app.route('/api/desempeno-dias')
@login_required
def api_desempeno_dias():
    """API: Eventos diarios de ingresos (checkout) y gastos (fecha_pago) para un mes."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    inicio_mes = f"{year}-{str(month).zfill(2)}-01"
    fin_mes = f"{year + 1}-01-01" if month == 12 else f"{year}-{str(month + 1).zfill(2)}-01"

    eventos = []

    all_events = db_service.obtener_eventos_formato_ical()
    for ev in all_events:
        if ev.get('estado') != 'reservado':
            continue
        ev_end = ev.get('end', '')
        if ev_end and inicio_mes <= ev_end < fin_mes:
            precio = ev.get('precio', 0) or 0
            extra = ev.get('extra_valor', 0) or 0
            if precio + extra > 0:
                eventos.append({'dia': ev_end, 'tipo': 'ingreso', 'concepto': 'reserva', 'valor': precio + extra})

    gastos_mes = db_service.obtener_gastos_mes(year, month)
    for concepto, lista in gastos_mes.items():
        for g in lista:
            fp = g.get('fecha_pago', '')
            if fp and inicio_mes <= fp < fin_mes:
                val = g.get('valor', 0) or 0
                if val > 0:
                    eventos.append({'dia': fp, 'tipo': 'gasto', 'concepto': concepto, 'valor': val})

    return jsonify({'eventos': eventos, 'year': year, 'month': month})


@app.route('/api/transacciones-mes')
@login_required
def api_transacciones_mes():
    """API: Transacciones BCI de un mes (ingresos/abonos y egresos/cargos)."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    transacciones = db_service.obtener_transacciones_mes(year, month)
    
    return jsonify({
        'transacciones': transacciones,
        'year': year,
        'month': month
    })


def _parse_calendario_ids() -> list | None:
    """Lee ?calendario_ids=a,b,c y devuelve ['a','b','c'] o None si no se envía."""
    raw = request.args.get('calendario_ids', '').strip()
    if not raw:
        return None
    return [c.strip() for c in raw.split(',') if c.strip()]


@app.route('/api/month')
def api_month():
    """API: Datos de un mes específico con eventos.

    Query params:
        year, month: año/mes a consultar (default: mes actual)
        calendario_ids: lista separada por comas de calendario_id a incluir
                        (None = todos). '__legacy__' incluye docs sin calendario_id.
    """
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    calendario_ids = _parse_calendario_ids()
    return jsonify(get_month_calendar(year, month, include_events=True,
                                      calendario_ids=calendario_ids))


@app.route('/api/month/tinaja')
def api_month_tinaja():
    """API: Datos de un mes con solo reservas que pagaron tinaja (extra_valor > 0)."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    return jsonify(get_month_calendar_tinaja(year, month, include_events=True))


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


@app.route('/api/estadisticas-total-mes')
@login_required
def api_estadisticas_total_mes():
    """API: Estadísticas de balance por mes para colores y ranking MVP (mean, std, 1° y 2° lugar)."""
    import math
    year = request.args.get('year', date.today().year, type=int)

    all_events = db_service.obtener_eventos_formato_ical()
    gastos_por_mes = db_service.obtener_gastos_agregados_anio(year)

    balances = []
    gastos_list = []
    ingresos_list = []
    for mes in range(1, 13):
        arriendo, tinaja, _, _ = _calcular_ingresos_mes_reservas(all_events, year, mes)
        g = gastos_por_mes.get(mes, {})
        total_gastos = (
            g.get('agua', 0) + g.get('internet', 0) + g.get('gasolina', 0)
            + g.get('aseo', 0) + g.get('otros', 0) + g.get('electricidad', 0)
        )
        balance = (arriendo + tinaja) - total_gastos
        balances.append({'mes': mes, 'anio': year, 'balance': balance})
        gastos_list.append({'mes': mes, 'anio': year, 'total_gastos': total_gastos})
        ingresos_list.append({'mes': mes, 'anio': year, 'total_ingresos': arriendo + tinaja})

    valores = [b['balance'] for b in balances]
    n = len(valores)
    media = sum(valores) / n if n else 0
    varianza = sum((v - media) ** 2 for v in valores) / n if n else 0
    std = math.sqrt(varianza) if varianza > 0 else 0

    # Ranking por balance descendente (mayor ingreso neto = 1°)
    ordenado = sorted(balances, key=lambda x: x['balance'], reverse=True)
    ranking = [{'mes': b['mes'], 'anio': b['anio'], 'posicion': i + 1} for i, b in enumerate(ordenado)]

    hoy = date.today()

    def mes_finalizado(m, a):
        return a < hoy.year or (a == hoy.year and m < hoy.month)

    # Ranking por gastos ascendente (menor gasto = mayor eficiencia = 1°), solo meses finalizados
    gastos_finalizados = [g for g in gastos_list if mes_finalizado(g['mes'], g['anio'])]
    ordenado_gastos = sorted(gastos_finalizados, key=lambda x: x['total_gastos'])
    ranking_gastos = [{'mes': b['mes'], 'anio': b['anio'], 'posicion': i + 1} for i, b in enumerate(ordenado_gastos)]

    # Ranking por ingresos descendente (mayor ingreso = 1°), solo meses finalizados
    ingresos_finalizados = [i for i in ingresos_list if mes_finalizado(i['mes'], i['anio'])]
    ordenado_ingresos = sorted(ingresos_finalizados, key=lambda x: x['total_ingresos'], reverse=True)
    ranking_ingresos = [{'mes': b['mes'], 'anio': b['anio'], 'posicion': i + 1} for i, b in enumerate(ordenado_ingresos)]

    return jsonify({
        'year': year,
        'balances': {b['mes']: b['balance'] for b in balances},
        'mean': round(media),
        'std': round(std),
        'ranking': ranking,
        'ranking_gastos': ranking_gastos,
        'ranking_ingresos': ranking_ingresos,
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


@app.route('/api/calendarios')
def api_calendarios():
    """API: Lista de calendarios configurados en .env + los legacy sin calendario_id.

    El frontend usa esto para pintar la barra de filtros del header.
    Refresca el estado de conexión antes de responder (para que `connected` esté actualizado).
    """
    # Refrescar estado leyendo de los calendarios configurados
    per_cal_status = airbnb_service.get_status().get('per_calendar', {})
    configured = [
        {
            "calendario_id": c['calendario_id'],
            "nombre": c['nombre'],
            "source": c['source'],
            # Por defecto unknown si nunca se hizo fetch; si hubo, refleja el último estado.
            "connected": per_cal_status.get(c['calendario_id'], {}).get('connected', None),
            "imagen": c.get('imagen') or '',
            "thumbnail": c.get('thumbnail') or '',
            "logo": c.get('logo') or '',
        }
        for c in airbnb_service.calendars
    ]
    # Detectar si hay docs legacy (sin calendario_id) en reservas airbnb
    has_legacy = False
    if db_service.connect():
        has_legacy = db_service.reservas.count_documents({
            "source": "airbnb",
            "$or": [{"calendario_id": None}, {"calendario_id": {"$exists": False}}]
        }) > 0
    return jsonify({
        "configured": configured,
        "has_legacy": has_legacy,
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
    if events is None:
        return jsonify({"mensaje": "iCal no disponible, sync abortado", "eventos_airbnb": 0})
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


@app.route('/api/reserva/<reserva_id>/cancelar', methods=['POST'])
@login_required
def api_cancelar_reserva(reserva_id):
    """API: Cancela reserva y genera gasto de devolución."""
    resultado = db_service.cancelar_reserva(reserva_id, get_audit_info())
    return jsonify(resultado)


def _reserva_to_json(reserva) -> dict:
    """Convierte reserva de BD al formato JSON para API/frontend."""
    return {
        "found": True,
        "id": str(reserva.get('_id', '')),
        "event_start": reserva.get('event_start', ''),
        "event_end": reserva.get('event_end', ''),
        "estado": reserva.get('estado', 'bloqueado'),
        "summary": reserva.get('summary', ''),
        "codigo_reserva": reserva.get('codigo_reserva', ''),
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
        "extra_pago_confirmado": reserva.get('extra_pago_confirmado', False),
        "comuna": reserva.get('comuna', ''),
        "pais": reserva.get('pais', '')
    }


@app.route('/api/reserva/<reserva_id>')
@login_required
def api_reserva_por_id(reserva_id):
    """API: Obtener reserva por ID."""
    reserva = db_service.obtener_reserva_por_id(reserva_id)
    if reserva:
        return jsonify(_reserva_to_json(reserva))
    return jsonify({"found": False, "error": "Reserva no encontrada"}), 404


@app.route('/api/reserva/por-fecha/<fecha>')
@login_required
def api_reserva_por_fecha(fecha):
    """API: Obtener reserva por fecha (singular, compat con frontend existente)."""
    reserva = db_service.buscar_reserva_por_fecha(fecha)
    if reserva:
        return jsonify(_reserva_to_json(reserva))
    return jsonify({"found": False, "fecha": fecha})


@app.route('/api/reservas/por-fecha/<fecha>')
@login_required
def api_reservas_por_fecha(fecha):
    """API: Obtener TODAS las reservas que tocan la fecha (multi-calendario).

    Retorna {"count": N, "reservas": [...]}. Excluye cache_* y eliminadas.
    Usado por el frontend cuando caen múltiples eventos el mismo día.
    """
    reservas = db_service.buscar_reservas_por_fecha(fecha)
    return jsonify({
        "count": len(reservas),
        "reservas": [_reserva_to_json(r) for r in reservas]
    })


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
        'codigo_reserva': (data.get('codigo_reserva') or '').strip() or None,
        'reservation_url': (data.get('reservation_url') or '').strip() or None,
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
        'extra_pago_confirmado': data.get('extra_pago_confirmado', False),
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
            rid = request.form.get('reserva_id', '')
            existente = db_service.obtener_reserva_por_id(rid) if rid else None

            def _get(field, default=''):
                val = request.form.get(field)
                if val is not None and str(val).strip() != '':
                    return val
                return existente.get(field, default) if existente else default

            datos = {
                'event_start': request.form.get('event_start') or (existente.get('event_start') if existente else ''),
                'event_end': request.form.get('event_end') or (existente.get('event_end') if existente else ''),
                'estado': request.form.get('estado') or (existente.get('estado', 'bloqueado') if existente else 'bloqueado'),
                'summary': _get('summary', ''),
                'codigo_reserva': (request.form.get('codigo_reserva') or '').strip() or (existente.get('codigo_reserva') if existente else None),
                'reservation_url': request.form.get('reservation_url') or (existente.get('reservation_url') if existente else None),
                'readonly': request.form.get('readonly') == 'on',
                'source': existente.get('source', 'admin') if existente else 'admin',
                'hora_checkin': _get('hora_checkin', ''),
                'hora_checkout': _get('hora_checkout', ''),
                'nombre_huesped': _get('nombre_huesped', ''),
                'adultos': int(_get('adultos', 0) or 0),
                'ninos': int(_get('ninos', 0) or 0),
                'mascotas': int(_get('mascotas', 0) or 0),
                'notas': _get('notas', ''),
                'precio': int(_get('precio', 0) or 0),
                'extra_concepto': _get('extra_concepto', ''),
                'extra_valor': int(_get('extra_valor', 0) or 0),
                'extra_pago_confirmado': request.form.get('extra_pago_confirmado') == 'on',
                'comuna': _get('comuna', ''),
                'pais': _get('pais', ''),
            }
            # reservation_url: si el form envía vacío, mantener existente al editar
            if existente and (not request.form.get('reservation_url') or request.form.get('reservation_url', '').strip() == ''):
                datos['reservation_url'] = existente.get('reservation_url')
            else:
                datos['reservation_url'] = request.form.get('reservation_url', '') or None

            # Validar fechas
            if datos['event_start'] >= datos['event_end']:
                error = 'La fecha de check-out debe ser posterior al check-in'
            else:
                resultado = db_service.guardar_reserva_manual(rid, datos, get_audit_info())
                
                if resultado.get('success'):
                    return redirect(url_for('home'))
                else:
                    error = resultado.get('error', 'Error al guardar')
    
    now = datetime.now()
    codigo_inicial = ''
    if not reserva:
        codigo_inicial = f"RES-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
    return render_template('reserva_edit.html',
                         reserva=reserva,
                         fecha=fecha,
                         codigo_inicial=codigo_inicial,
                         today=now.strftime('%Y-%m-%d'),
                         property_name=PROPERTY_NAME,
                         error=error,
                         success=success)


# ============================================================
# API GASTOS (todos en un endpoint)
# ============================================================

@app.route('/api/gastos', methods=['GET'])
@login_required
def obtener_gastos_mes():
    """Obtiene todos los gastos del mes (agua, internet, gasolina, aseo, otros, electricidad) en un solo llamado."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    return jsonify(db_service.obtener_gastos_mes(year, month))

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
# API GASTOS OTROS (devoluciones, etc.)
# ============================================================

@app.route('/api/gastos/otros', methods=['GET'])
@login_required
def obtener_gastos_otros():
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    gastos = db_service.obtener_gastos_otros(year, month)
    return jsonify({"gastos": gastos})

@app.route('/api/gastos/otros', methods=['POST'])
@login_required
def guardar_gasto_otros():
    data = request.get_json()
    gasto = {
        'razon': data.get('razon', ''),
        'nombre': data.get('nombre', ''),
        'tipo': data.get('tipo', 'devolucion'),
        'fecha_pago': data.get('fecha_pago', ''),
        'valor': data.get('valor', 0),
        'descripcion': data.get('descripcion', ''),
        'whatsapp': data.get('whatsapp', ''),
        'pagado': data.get('pagado', True),
        'proveedor_id': data.get('proveedor_id', '')
    }
    resultado = db_service.guardar_gasto_otros(gasto)
    return jsonify(resultado)

@app.route('/api/gastos/otros/<gasto_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_gasto_otros_id(gasto_id):
    if request.method == 'PATCH':
        return jsonify(db_service.toggle_pagado_gasto('gastos_otros', gasto_id))
    return jsonify(db_service.eliminar_gasto('gastos_otros', gasto_id))

# ============================================================
# API GASTOS ELECTRICIDAD
# ============================================================

@app.route('/api/gastos/electricidad', methods=['GET'])
@login_required
def obtener_gastos_electricidad():
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    gastos = db_service.obtener_gastos_electricidad(year, month)
    return jsonify({"gastos": gastos})

@app.route('/api/gastos/electricidad', methods=['POST'])
@login_required
def guardar_gasto_electricidad():
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
    resultado = db_service.guardar_gasto_electricidad(gasto)
    return jsonify(resultado)

@app.route('/api/gastos/electricidad/<gasto_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_gasto_electricidad_id(gasto_id):
    if request.method == 'PATCH':
        return jsonify(db_service.toggle_pagado_gasto('gastos_electricidad', gasto_id))
    return jsonify(db_service.eliminar_gasto('gastos_electricidad', gasto_id))

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


db_service.seed_proveedores_otros()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
