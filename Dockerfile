FROM python:3.13

# Instalar Poetry
RUN pip install poetry

# Configurar el entorno de trabajo
WORKDIR /app

# Copiar archivos del proyecto
COPY . .

# Instalar dependencias usando Poetry
RUN poetry install --no-interaction --no-ansi

# Comando para ejecutar la aplicación con Gunicorn
CMD ["poetry", "run", "gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:80", "airbnb_agent.app:app"]
