#!/usr/bin/env python3
"""
Script para rellenar codigo_reserva en reservas existentes.
Extrae el código de reservation_url (?code=XXX o último segmento de la URL).
"""
import os
import re
from pathlib import Path

# Cargar .env desde la raíz del proyecto
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("❌ MONGODB_URI no configurado en .env")
    exit(1)


def extraer_codigo_de_url(url: str) -> str | None:
    """Extrae código de reserva de la URL: ?code=XXX o último segmento."""
    if not url or not isinstance(url, str):
        return None
    # Primero ?code=XXX
    match = re.search(r'[?&]code=([^&\s]+)', url)
    if match:
        return match.group(1)
    # Último segmento después del último /
    parts = url.rstrip('/').split('/')
    if parts:
        last = parts[-1]
        if last and not last.startswith('?'):
            code = last.split('?')[0]
            if code:
                return code
    return None


def main():
    from pymongo import MongoClient

    print("Conectando a MongoDB...")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client["airbnb-db"]
    reservas = db["reservas"]

    # Reservas con URL pero sin codigo_reserva (o codigo vacío)
    cursor = reservas.find({"reservation_url": {"$exists": True, "$ne": None, "$ne": ""}})
    total = 0
    actualizados = 0

    for doc in cursor:
        total += 1
        url = doc.get("reservation_url") or ""
        if not url:
            continue
        codigo_actual = doc.get("codigo_reserva")
        codigo_nuevo = extraer_codigo_de_url(url)

        if codigo_nuevo:
            if codigo_actual != codigo_nuevo:
                reservas.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"codigo_reserva": codigo_nuevo}}
                )
                actualizados += 1
                print(f"  ✓ {doc.get('event_start')}–{doc.get('event_end')}: {codigo_nuevo}")
        else:
            url_preview = (url or "")[:60] if url else "(vacío)"
            print(f"  ⚠ Sin código extraíble: {url_preview}...")

    print(f"\n✅ Listo. {actualizados} de {total} reservas actualizadas con codigo_reserva.")


if __name__ == "__main__":
    main()
