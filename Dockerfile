FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias necesarias para psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY barberia/ .
COPY docker/start.sh /app/start.sh

RUN useradd -m barberia && chown -R barberia:barberia /app

USER barberia

EXPOSE 8000

# Define que se ejecuta al arrancar el contenedor
CMD ["sh", "/app/start.sh"]