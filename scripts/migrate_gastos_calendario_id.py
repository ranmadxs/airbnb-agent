#!/usr/bin/env python3
"""
Migración v3.7.0: asigna calendario_id a gastos legacy (sin el campo).

Contexto:
- Antes de v3.7.0, los gastos (agua, internet, gasolina/transporte, aseo,
  otros, electricidad) se guardaban sin calendario_id.
- Todos los gastos del sistema a la fecha pertenecen al calendario
  "Paraiso los quinquelles 1" (slug: paraiso_los_quinquelles_1).
- Este script les asigna ese calendario_id. Es idempotente: correrlo 2 veces
  no hace nada la segunda.

Uso:
    python scripts/migrate_gastos_calendario_id.py [--dry-run]

Opciones:
    --dry-run    Solo muestra qué modificaría, no escribe nada.

Antes del deploy con filtro por calendario: ejecutar con --dry-run para
confirmar el alcance, luego sin --dry-run para aplicar.
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

GASTOS_COLECCIONES = (
    "gastos_agua",
    "gastos_internet",
    "gastos_gasolina",
    "gastos_aseo",
    "gastos_otros",
    "gastos_electricidad",
)

TARGET_CALENDARIO_ID = "paraiso_los_quinquelles_1"


def legacy_query():
    return {
        "$or": [
            {"calendario_id": None},
            {"calendario_id": {"$exists": False}},
            {"calendario_id": ""},
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Migración v3.7.0: calendario_id en gastos legacy")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no escribir")
    args = parser.parse_args()

    from pymongo import MongoClient

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")  # fail fast si no conecta

    db = client["airbnb-db"]

    total_global = 0
    for coll_name in GASTOS_COLECCIONES:
        coll = db[coll_name]
        total = coll.count_documents(legacy_query())
        total_global += total
        print(f"🔍 {coll_name}: {total} docs sin calendario_id")

    if total_global == 0:
        print("✅ Nada que migrar. Todos los gastos ya tienen calendario_id.")
        return 0

    # Mostrar muestra antes de actuar
    print("\nMuestra (primeros 3 de gastos_otros si hay):")
    try:
        for doc in db["gastos_otros"].find(legacy_query()).limit(3):
            print(f"  {doc.get('fecha_pago', '?')}  ${doc.get('valor', 0)}  {(doc.get('razon') or '')[:40]}")
    except Exception:
        pass

    if args.dry_run:
        print("\n[DRY-RUN] NO se escribió nada.")
        print("[DRY-RUN] Para aplicar: python scripts/migrate_gastos_calendario_id.py")
        return 0

    migrados = 0
    for coll_name in GASTOS_COLECCIONES:
        result = db[coll_name].update_many(
            legacy_query(),
            {"$set": {"calendario_id": TARGET_CALENDARIO_ID}},
        )
        migrados += result.modified_count
        print(f"✅ {coll_name}: migrados {result.modified_count}")

    print(f"\n✅ Total migrados: {migrados} docs.")
    print(f"   calendario_id asignado: '{TARGET_CALENDARIO_ID}'")
    print("   Idempotente: correr de nuevo no hace nada.")

    restantes = sum(db[c].count_documents(legacy_query()) for c in GASTOS_COLECCIONES)
    print(f"   Quedan sin calendario_id: {restantes}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
