#!/usr/bin/env python3
"""
Migración v3.0.0: asigna calendario_id a reservas con source=airbnb.

Contexto:
- Antes de v3.0.0, las reservas de Airbnb se guardaban con source="airbnb" pero sin
  calendario_id (campo nuevo introducido en el refactor multi-calendario).
- Este script NO toca reservas con otros sources (admin, whatsapp, manual, etc.):
  esas son contratos directos y no tienen relación con calendarios iCal.

Comportamiento:
- Encuentra docs con source=airbnb y calendario_id nulo/ausente.
- Les asigna calendario_id="paraiso_los_quinquelles_1" (el primer calendario del JSON
  en tu .env actual).
- Es idempotente: si lo corres 2 veces, la segunda no hace nada.

Uso:
    python scripts/migrate_v3_calendario_id.py [--dry-run]

Opciones:
    --dry-run    Solo muestra qué modificaría, no escribe nada.

Antes del deploy: ejecutar con --dry-run para confirmar el alcance,
luego sin --dry-run para aplicar.
"""
import os
import sys
import argparse
from pathlib import Path

# Cargar .env desde la raíz del proyecto
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("❌ MONGODB_URI no configurado en .env")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Migración v3.0.0: calendario_id en reservas airbnb legacy")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no escribir")
    args = parser.parse_args()

    from pymongo import MongoClient

    # calendario_id destino: coincide con el primer calendario del JSON en .env actual.
    # Si cambias el orden o agregas más calendarios, ajusta aquí.
    target_calendario_id = "paraiso_los_quinquelles_1"

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")  # fail fast si no conecta

    db = client["airbnb-db"]
    reservas = db["reservas"]

    # Query: source=airbnb (no cache_*) y calendario_id ausente/null
    query = {
        "source": "airbnb",
        "$or": [
            {"calendario_id": None},
            {"calendario_id": {"$exists": False}},
        ]
    }

    total = reservas.count_documents(query)
    print(f"🔍 Reservas con source=airbnb y calendario_id nulo: {total}")

    if total == 0:
        print("✅ Nada que migrar. Ya están todos los docs con calendario_id.")
        return 0

    # Mostrar muestra antes de actuar
    print(f"\nMuestra de los primeros 5:")
    for doc in reservas.find(query).limit(5):
        nombre = doc.get("nombre_huesped", "(sin nombre)")
        print(f"  {doc['event_start']} -> {doc['event_end']}  {nombre[:30]}")

    if args.dry_run:
        print(f"\n[DRY-RUN] NO se escribió nada.")
        print(f"[DRY-RUN] Para aplicar: python scripts/migrate_v3_calendario_id.py")
        return 0

    # Aplicar: update_many
    result = reservas.update_many(
        query,
        {"$set": {"calendario_id": target_calendario_id}}
    )

    print(f"\n✅ Migrados: {result.modified_count} docs.")
    print(f"   calendario_id asignado: '{target_calendario_id}'")
    print(f"   Idempotente: correr de nuevo no hace nada.")

    # Verificar
    restantes = reservas.count_documents(query)
    print(f"   Quedan sin calendario_id: {restantes}")

    return 0


if __name__ == "__main__":
    sys.exit(main())