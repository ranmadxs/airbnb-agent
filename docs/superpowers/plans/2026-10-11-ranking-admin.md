# Ranking Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar pantalla /ranking solo admin con 2 tabs (anual + global), top 10 por ingresos brutos, link desde Total del Mes.

**Architecture:** Reusar `_calcular_ingresos_mes_reservas`, `_calcular_ingresos_por_calendario`, `obtener_gastos_agregados_anio` y `obtener_eventos_formato_ical` en `app.py`; nuevo template `ranking.html` clonando patrón tabs de `desempeno.html`; CSS copas en `style.css`; rutas protegidas con `login_required`.

**Tech Stack:** Flask, Jinja2, vanilla JS, pytest, MongoDB (mock en tests).

**Spec:** Conversación brainstorming 2026-10-11 (sin doc formal): ranking solo admins, hipervínculo Total del Mes -> otra pantalla; Tab1 anual año actual + flechas, 3 paneles top 10 ingresos brutos (meses / calendarios recinto-casa-depto / clientes arriendo+tinaja); Tab2 global todos los años top 10 mejores meses + ranking global establecimiento; filas Ingresos - Gastos = Neto (gastos rojo), clientes Arriendo + Extras; copas 1 oro 2 plata 3 bronce con número al medio, resto números bonitos mismo estilo; tinaja siempre sumada al ingreso.

## Global Constraints

- Solo admin: ruta y API con `@login_required`, widget/link solo si `is_logged_in`, anónimo recibe 401 en API y redirect a /login en página.
- Ingreso bruto = `precio prorrateado + extra_valor prorrateado (tinaja)` según `_calcular_ingresos_mes_reservas`; tinaja nunca separada del total.
- Top 10 en todos los paneles (pisa top 12 inicial).
- Año anual por defecto = año actual, flechas cambian año; global = todos los años sin filtro año.
- Versión semántica en `pyproject.toml`: bump minor 3.7.0 -> 3.8.0 por feature.

## Review Focus

- Año sin reservas ni gastos retorna listas vacías, no divide por cero ni 500 — espera top vacío con mensaje.
- Reserva cruzada entre meses prorratea por días igual que calendario — espera 50/50 en corte de mes.
- Evento sin `calendario_id` cae en `__legacy__` y no se pierde — espera incluido en global establecimiento.
- Cliente sin `nombre_huesped` agrupa como `Huésped`/`summary` y no rompe ranking clientes — espera fila agrupada.
- Acceso anónimo a /ranking y /api/ranking* denegado — espera redirect login y 401 JSON.

---

### Task 1: API ranking anual

**Files:**
- Modify: `airbnb_agent/app.py:1092-1150` (vecindad `api_estadisticas_total_mes`, agregar helpers + 1 ruta)
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: `_calcular_ingresos_mes_reservas(all_events, year, month) -> (arriendo, tinaja, pagado, proximos)`, `_calcular_ingresos_por_calendario(all_events, year, month) -> dict`, `db_service.obtener_eventos_formato_ical() -> list`, `db_service.obtener_gastos_agregados_anio(year) -> dict`, `obtener_todos_calendarios() -> list`
- Produces: `GET /api/ranking?year=<int> -> {year, meses_top:[{mes, nombre_mes, ingresos, gastos, neto}], calendarios_top:[{calendario_id, nombre, ingresos, gastos_prorrateado, neto}], clientes_top:[{cliente, arriendo, extras, ingresos}]}` ordenados desc por ingresos, max 10; `_ranking_anual(year, all_events, gastos_por_mes) -> dict` (helper testeable)

- [ ] **Step 1: Write the failing test**

```python
def test_api_ranking_anual_top10_por_ingresos_brutos(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"start": "2026-01-05", "end": "2026-01-07", "estado": "reservado", "precio": 300000, "extra_valor": 50000, "calendario_id": "casa_costa", "nombre_huesped": "Juan"},
        {"start": "2026-05-10", "end": "2026-05-12", "estado": "reservado", "precio": 500000, "extra_valor": 0, "calendario_id": "depto_centro", "nombre_huesped": "Ana"},
    ]
    app_module.db_service.obtener_gastos_agregados_anio.return_value = {m: {"agua": 10000, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    r = logged_in_flask_client.get("/api/ranking?year=2026")
    assert r.status_code == 200
    j = r.get_json()
    assert j["meses_top"][0]["mes"] == 5
    assert j["meses_top"][0]["ingresos"] == 500000
    assert j["clientes_top"][0]["ingresos"] == 500000

def test_api_ranking_requiere_login(flask_client, app_module):
    r = flask_client.get("/api/ranking?year=2026")
    assert r.status_code == 401

def test_ranking_anual_vacio_y_legacy():
    from airbnb_agent.app import _ranking_anual
    vacio = _ranking_anual(2026, [], {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)})
    assert vacio["meses_top"] == [] and vacio["calendarios_top"] == [] and vacio["clientes_top"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ranking.py::test_api_ranking_anual_top10_por_ingresos_brutos -v`
Expected: FAIL with "404" o "No matching route"

- [ ] **Step 3: Implement `GET /api/ranking` + `_ranking_anual()` en `airbnb_agent/app.py`**

Reusar prorrateo diario existente; gastos mensuales por `obtener_gastos_agregados_anio`; para calendarios prorratear gastos proporcional a ingresos del mes (o 0 si sin ingresos) para obtener neto; clientes agrupan por `nombre_huesped or summary or 'Huésped'` sumando `precio+extra` prorrateado, separando `arriendo` vs `extras`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ranking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airbnb_agent/app.py tests/test_ranking.py
git commit -m "feat: api ranking anual top10 por ingresos brutos"
```

### Task 2: API ranking global todos los años

**Files:**
- Modify: `airbnb_agent/app.py` (agregar `GET /api/ranking-global`)
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: `GET /api/ranking` helper `_ranking_anual`, `db_service.obtener_gastos_agregados_anio(year)` por cada año presente en eventos
- Produces: `GET /api/ranking-global -> {meses_top:[{anio, mes, nombre_mes, ingresos, gastos, neto}], establecimientos_top:[{calendario_id, nombre, ingresos, neto}]}` top 10 global desc por ingresos

- [ ] **Step 1: Write the failing test**

```python
def test_api_ranking_global_todos_los_anios(logged_in_flask_client, app_module):
    app_module.db_service.obtener_eventos_formato_ical.return_value = [
        {"start": "2025-01-05", "end": "2025-01-06", "estado": "reservado", "precio": 900000, "extra_valor": 0, "calendario_id": "casa_costa"},
        {"start": "2026-05-10", "end": "2026-05-11", "estado": "reservado", "precio": 100000, "extra_valor": 0, "calendario_id": "depto_centro"},
    ]
    def gastos(year):
        return {m: {"agua": 0, "internet": 0, "gasolina": 0, "aseo": 0, "otros": 0, "electricidad": 0} for m in range(1, 13)}
    app_module.db_service.obtener_gastos_agregados_anio.side_effect = gastos
    r = logged_in_flask_client.get("/api/ranking-global")
    assert r.status_code == 200
    assert r.get_json()["meses_top"][0]["anio"] == 2025
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ranking.py::test_api_ranking_global_todos_los_anios -v`
Expected: FAIL with 404

- [ ] **Step 3: Implement `GET /api/ranking-global` en `airbnb_agent/app.py`**

Detectar años distintos desde `start` de eventos + pagos arriendo si admin; iterar `_ranking_anual` por año y fusionar meses y calendarios sumando ingresos/gastos/neto; ordenar desc y cortar 10.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ranking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airbnb_agent/app.py tests/test_ranking.py
git commit -m "feat: api ranking global todos los anios"
```

### Task 3: Página /ranking + link desde Total del Mes

**Files:**
- Create: `airbnb_agent/templates/ranking.html`
- Modify: `airbnb_agent/app.py` (agregar `GET /ranking` con `@login_required`)
- Modify: `airbnb_agent/templates/calendar.html:125-132` (widget Total del Mes -> `<a href="/ranking">`)
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: `GET /api/ranking?year`, `GET /api/ranking-global`
- Produces: `GET /ranking -> HTML` con tabs Anual/Global, flechas año, 3 paneles anual + 2 paneles global, fetch JS con `credentials: include`

- [ ] **Step 1: Write the failing test**

```python
def test_pagina_ranking_solo_admin(logged_in_flask_client, flask_client):
    assert logged_in_flask_client.get("/ranking").status_code == 200
    r = flask_client.get("/ranking", follow_redirects=False)
    assert r.status_code in (302, 401)
    assert "/login" in r.headers.get("Location", "") or r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ranking.py::test_pagina_ranking_solo_admin -v`
Expected: FAIL 404

- [ ] **Step 3: Implement `desempeno()`-style route `/ranking` + `ranking.html` en archivos indicados**

Clonar estructura tabs de `desempeno.html:283-290`; header con back a `/`; Tab Anual con `← año →`, contenedores `ranking-meses`, `ranking-calendarios`, `ranking-clientes`; Tab Global con `ranking-global-meses`, `ranking-global-est`; JS fetch a ambas APIs y render filas `Enero 2026 Ingresos $xxx Egresos $xxx Neto $xxx`; en `calendar.html` envolver `widget-total-mes` en `<a href="/ranking" class="ranking-link">` sin romper `id="widget-total-mes"` ni JS existente.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ranking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airbnb_agent/app.py airbnb_agent/templates/ranking.html airbnb_agent/templates/calendar.html tests/test_ranking.py
git commit -m "feat: pagina ranking admin + link desde Total del Mes"
```

### Task 4: Estilo top copas oro/plata/bronce

**Files:**
- Modify: `airbnb_agent/static/css/style.css`
- Modify: `airbnb_agent/templates/ranking.html` (clases filas)

**Interfaces:**
- Consumes: clases `.ranking-row.pos-1/2/3`, `.copa-oro/.copa-plata/.copa-bronce`, `.ranking-num`
- Produces: visual top 1 copa oro, 2 plata, 3 bronce con número al medio, 4-10 números bonitos mismo estilo

- [ ] **Step 1: Write the failing test (visual pin)**

```python
def test_ranking_css_copas_existe():
    css = open("airbnb_agent/static/css/style.css", encoding="utf-8").read()
    assert ".copa-oro" in css and ".copa-plata" in css and ".copa-bronce" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ranking.py::test_ranking_css_copas_existe -v`
Expected: FAIL assert ".copa-oro"

- [ ] **Step 3: Implement CSS en `airbnb_agent/static/css/style.css`**

Círculo 44px con gradiente oro `#FFD700/#B8860B`, plata `#E5E7EB/#9CA3AF`, bronce `#F59E0B/#92400E`, emoji 🏆 + número centrado blanco con sombra; `.ranking-num` 4-10 mismo tamaño, fondo `#F3F4F6`, borde `2px solid #E5E7EB`, font-weight 800; fila con Ingresos verde, Gastos rojo, Neto bold.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ranking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airbnb_agent/static/css/style.css airbnb_agent/templates/ranking.html tests/test_ranking.py
git commit -m "feat: estilo top copas oro plata bronce ranking"
```

### Task 5: Versión semántica + PR

**Files:**
- Modify: `pyproject.toml:3` (`version = "3.7.0"` -> `"3.8.0"`)
- Modify: `CHANGELOG.md` (nueva entrada 3.7.0)
- Test: verificación manual + suite

**Interfaces:**
- Consumes: tasks 1-4 pasando
- Produces: rama `feat/ranking-admin-3.8.0`, PR a `main` con checklist verificación

- [ ] **Step 1: Bump versión y changelog**

Cambiar solo línea version en `pyproject.toml`; agregar entrada CHANGELOG 3.8.0 con ranking admin, link Total del Mes, tabs anual/global, copas.

- [ ] **Step 2: Run verificación completa**

Run: `pytest -q`
Expected: PASS sin fallos; luego `python -m py_compile airbnb_agent/app.py`

- [ ] **Step 3: Crear rama y PR**

```bash
git checkout -b feat/ranking-admin-3.8.0
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version a 3.8.0 ranking admin"
git push -u origin feat/ranking-admin-3.8.0
gh pr create --title "feat: ranking admin 3.8.0" --body "Ranking solo admin desde Total del Mes, tabs anual/global top10, copas oro/plata/bronce"
```

- [ ] **Step 4: Commit final si falta**

Solo si verificación pide ajuste menor; si no, no commitear vacío.
