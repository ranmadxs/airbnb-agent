#!/usr/bin/env python3
"""
Script para verificar que la base de datos MongoDB concuerda con el esquema esperado por airbnb-agent.
Ejecutar desde la raíz del proyecto: python scripts/verificar_mongodb.py
"""
import os
import sys
from pathlib import Path

# Añadir el proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "")


def main():
    if not MONGODB_URI:
        print("❌ MONGODB_URI no configurado en .env")
        return 1

    try:
        from pymongo import MongoClient
    except ImportError:
        print("❌ pymongo no instalado. Ejecuta: pip install pymongo")
        return 1

    print("=" * 60)
    print("Verificación de MongoDB - airbnb-agent")
    print("=" * 60)

    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("✅ Conexión exitosa\n")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return 1

    db = client["airbnb-db"]

    # 1. Colecciones esperadas
    colecciones_esperadas = [
        "reservas",
        "dias",
        "personas",
        "transacciones",
        "gastos_agua",
        "gastos_internet",
        "gastos_gasolina",
        "gastos_aseo",
        "gastos_otros",
        "gastos_electricidad",
        "proveedores",
    ]
    colecciones_existentes = db.list_collection_names()

    print("1. COLECCIONES")
    print("-" * 40)
    for coll in colecciones_esperadas:
        existe = coll in colecciones_existentes
        status = "✅" if existe else "⚠️ (no existe, se creará al usar)"
        print(f"  {coll}: {status}")
    print()

    # 2. Colección reservas
    print("2. COLECCIÓN RESERVAS")
    print("-" * 40)
    reservas = db["reservas"]
    total = reservas.count_documents({})
    print(f"  Total documentos: {total}")

    if total > 0:
        # Muestra un documento de ejemplo
        sample = reservas.find_one()
        campos_esperados = [
            "event_start", "event_end", "estado", "codigo_reserva",
            "extra_concepto", "extra_valor", "extra_pago_confirmado",
            "precio", "nombre_huesped", "source"
        ]
        print("\n  Campos en primer documento:")
        for c in campos_esperados:
            tiene = c in sample
            valor = sample.get(c, "—")
            if c == "extra_pago_confirmado" and not tiene:
                print(f"    {c}: ⚠️ FALTA (documentos antiguos)")
            else:
                print(f"    {c}: {valor}")

        # Contar docs sin extra_pago_confirmado
        sin_extra_pago = reservas.count_documents({"extra_pago_confirmado": {"$exists": False}})
        if sin_extra_pago > 0:
            print(f"\n  ⚠️ {sin_extra_pago} documento(s) sin campo 'extra_pago_confirmado'")
            print("     (El código usa .get('extra_pago_confirmado', False) así que funciona)")
    print()

    # 3. Índices reservas
    print("3. ÍNDICES RESERVAS")
    print("-" * 40)
    for idx in reservas.list_indexes():
        print(f"  - {idx['name']}: {list(idx['key'].keys())}")
    print()

    # 4. Colección dias
    print("4. COLECCIÓN DIAS")
    print("-" * 40)
    dias = db["dias"]
    total_dias = dias.count_documents({})
    print(f"  Total documentos: {total_dias}")
    if total_dias > 0:
        sample_dia = dias.find_one()
        print(f"  Campos: {list(sample_dia.keys())}")
    print()

    # 5. Gastos - verificar estructura
    print("5. COLECCIONES DE GASTOS")
    print("-" * 40)
    for coll_name in ["gastos_agua", "gastos_internet", "gastos_gasolina", "gastos_aseo", "gastos_otros", "gastos_electricidad"]:
        if coll_name in colecciones_existentes:
            coll = db[coll_name]
            n = coll.count_documents({})
            if n > 0:
                s = coll.find_one()
                campos = list(s.keys())
                tiene_fecha = "fecha_pago" in campos
                tiene_valor = "valor" in campos
                status = "✅" if (tiene_fecha and tiene_valor) else "⚠️"
                print(f"  {coll_name}: {n} docs {status}")
            else:
                print(f"  {coll_name}: 0 docs (vacía)")
        else:
            print(f"  {coll_name}: no existe")
    print()

    # 6. Estados en reservas
    print("6. ESTADOS EN RESERVAS")
    print("-" * 40)
    pipeline = [{"$group": {"_id": "$estado", "count": {"$sum": 1}}}]
    for r in reservas.aggregate(pipeline):
        print(f"  {r['_id'] or '(null)'}: {r['count']}")
    print()

    print("=" * 60)
    print("Verificación completada")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
