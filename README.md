# Airbnb Calendar Agent

Agente visual que muestra el calendario de reservas de tu propiedad Airbnb.

## 🚀 Inicio Rápido

### 1. Instalación
```bash
poetry install
```

### 2. Configuración
Crea un archivo `.env`:
```env
AIRBNB_CALENDAR_URL="tu_url_ical_de_airbnb"
```

### 3. Ejecutar
```bash
# Desarrollo
poetry run python -m airbnb_agent.app

# Producción
poetry run gunicorn -w 1 --threads 4 -b 0.0.0.0:8000 airbnb_agent.app:app
```

## 📊 Características

- 📅 Visualización de calendario mensual
- 🏠 Muestra días reservados y disponibles
- 📈 Estadísticas de ocupación
- 📋 Lista de próximas reservas
- 🎨 Diseño estilo Airbnb

## 📁 Estructura

```
airbnb-agent/
├── airbnb_agent/
│   ├── app.py              # Aplicación Flask
│   ├── templates/
│   │   └── calendar.html   # Template del calendario
│   └── static/
│       └── css/
│           └── style.css   # Estilos
├── .env                    # Configuración
└── pyproject.toml          # Dependencias
```

## 🔗 API Endpoints

| Endpoint | Descripción |
|----------|-------------|
| `/` | Página principal con calendario |
| `/api/events` | Lista de eventos JSON |
| `/api/stats` | Estadísticas JSON |

## 📜 Licencia

MIT
