# Tests — airbnb-agent

Suite de tests unitarios para `airbnb_agent`. Los tests no requieren
MongoDB ni servicios externos: todo se mockea en `conftest.py` y en
cada fixture/monkeypatch local.

## Estructura

```
tests/
├── conftest.py              # Fixtures globales (app_module, flask_client, logged_in_flask_client)
├── test_app_helpers.py      # Tests de helpers puros de app.py: ingresos, filtro ?cal=, webhook MP
├── test_airbnb_calendar.py  # Tests de CalendarService: _slugify, _parse_value, _load_calendars, get_stats
└── test_database.py         # Tests de DatabaseService: query Mongo con calendario_ids + legacy
```

## Cómo correr

```bash
poetry install --with dev
poetry run pytest
poetry run pytest --cov=airbnb_agent --cov-report=term-missing --cov-report=xml:coverage.xml
```

## Convenciones

- Tests en clases (`TestX`) agrupados por feature.
- Mocks via `monkeypatch` (preferido) o `unittest.mock.MagicMock`.
- Cobertura excluye `templates/`, `static/` y `__init__.py` (ver `[tool.coverage]` en `pyproject.toml`).
- Coverage mínimo actual: **25%**. Si baja, el build de Jenkins falla.

## CI

- **GitHub Actions**: `.github/workflows/pr.yml` corre `pytest + coverage` en cada PR y comenta el porcentaje.
- **Jenkins**: `Jenkinsfile` con stages `Checkout → Setup → Install dependencies → Unit Tests → Coverage`. El stage Coverage usa el plugin Cobertura para mostrar el % en la UI.