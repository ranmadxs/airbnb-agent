#!/usr/bin/env python3
"""
Revisa la reserva de marzo 2026 (checkin 11, checkout 13) en MongoDB.
Uso: python scripts/check_reserva_marzo.py
"""
import os
import sys

# Cargar desde raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient

def main():
    uri = os.getenv("MONGODB_URI", "")
    if not uri:
        print("❌ MONGODB_URI no configurado en .env")
        return 1

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=15000)
        client.admin.command("ping")
    except Exception as e:
        print(f"❌ No se pudo conectar a MongoDB: {e}")
        return 1

    db = client["airbnb-db"]
    reservas = db["reservas"]

    # Buscar reserva marzo 2026
    for event_end in ["2026-03-13", "2026-03-14"]:
        r = reservas.find_one({"event_start": "2026-03-11", "event_end": event_end})
        if r:
            break
    else:
        # Listar reservas en marzo 2026
        print("No se encontró reserva exacta. Reservas en marzo 2026:")
        for x in reservas.find({"event_start": {"$regex": "^2026-03"}}).sort("event_start", 1):
            print(f"  {x.get('event_start')} → {x.get('event_end')} | checkout={x.get('checkout')} | estado={x.get('estado')}")
        return 0

    print("Reserva encontrada:")
    print(f"  event_start: {r.get('event_start')}")
    print(f"  event_end:   {r.get('event_end')}")
    print(f"  checkout:    {r.get('checkout')}  {'← PROBLEMA si está definido (causa FINALIZADA)' if r.get('checkout') else '(OK)'}")
    print(f"  estado:      {r.get('estado')}")
    print(f"  summary:     {r.get('summary', '')[:50]}...")

    if r.get("checkout"):
        print("\n¿Quitar checkout incorrecto? Ejecuta:")
        print(f"  db.reservas.updateOne({{'_id': ObjectId('{r['_id']}')}}, {{$unset: {{checkout: ''}}}})")
        print("\nO desde Python:")
        resp = input("¿Ejecutar $unset checkout ahora? (s/n): ").strip().lower()
        if resp == "s":
            reservas.update_one({"_id": r["_id"]}, {"$unset": {"checkout": ""}})
            print("✓ Checkout eliminado.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
