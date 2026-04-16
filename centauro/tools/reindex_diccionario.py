"""
Reindexar solo la colección 'diccionario_datos' en ChromaDB.

Uso:
    python centauro/tools/reindex_diccionario.py

Equivale a borrar manualmente chroma_db/ y re-indexar todo,
pero sin tocar las otras 5 colecciones (manuales, buenas_practicas, etc.).
"""
import sys
from pathlib import Path

# Asegurar que el proyecto esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from centauro.config import centauro_config
from centauro.rag import get_collection, indexar_diccionario_datos


def main():
    nombre_coleccion = centauro_config.COLLECTION_DICCIONARIO_DATOS
    print(f"Borrando colección '{nombre_coleccion}' de ChromaDB...")

    col = get_collection(nombre_coleccion)
    total_antes = col.count()
    print(f"   Entradas antes: {total_antes}")

    # Obtener todos los IDs y borrarlos
    if total_antes > 0:
        resultado = col.get()
        ids = resultado["ids"]
        col.delete(ids=ids)
        print(f"   Eliminadas {len(ids)} entradas.")
    else:
        print("   La colección ya estaba vacía.")

    print("\nRe-indexando diccionario del modelo semántico...")
    indexar_diccionario_datos()

    total_despues = col.count()
    print(f"\nListo. Entradas en colección: {total_despues}")


if __name__ == "__main__":
    main()
