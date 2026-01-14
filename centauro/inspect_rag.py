import chromadb
from .config import settings

def inspeccionar_memoria():
    # Usamos TU variable exacta: settings.CHROMA_PATH
    ruta_db = settings.CHROMA_PATH
    
    print(f"🕵️‍♂️ INSPECTOR RAG: Buscando base de datos en: {ruta_db}")
    
    # Verificamos si la carpeta existe
    if not ruta_db.exists():
        print(f"❌ ERROR: La carpeta no existe en: {ruta_db}")
        print("   -> ¿Has ejecutado 'ingest.py' para cargar el manual?")
        return

    try:
        # Conectamos usando la ruta de tu config
        client = chromadb.PersistentClient(path=str(ruta_db))
        
        # 1. Listar colecciones
        colecciones = client.list_collections()
        nombres = [c.name for c in colecciones]
        print(f"📚 Colecciones encontradas: {nombres}")
        
        if not colecciones:
            print("⚠️ Conexión exitosa, pero no hay colecciones (Manual no cargado).")
            return

        # 2. Inspeccionar la primera colección
        nombre_coleccion = nombres[0]
        collection = client.get_collection(name=nombre_coleccion)
        
        cantidad = collection.count()
        print(f"✅ Total de fragmentos en '{nombre_coleccion}': {cantidad}")
        
        # 3. Mostrar muestra de datos
        if cantidad > 0:
            print("\n--- 🔍 MUESTRA DE CONTENIDO (Primeros 2 fragmentos) ---")
            datos = collection.peek(limit=10)
            
            ids = datos['ids']
            textos = datos['documents']
            metadatos = datos['metadatas']
            
            for i in range(len(ids)):
                print(f"\n📄 [ID: {ids[i]}]")
                print(f"📌 Metadatos: {metadatos[i]}")
                print(f"📝 Texto: {textos[i][:200]}...") # Mostramos solo el inicio
                print("-" * 50)
        else:
            print("⚠️ La colección existe pero está vacía.")
            
    except Exception as e:
        print(f"❌ Error crítico al leer Chroma: {e}")

if __name__ == "__main__":
    inspeccionar_memoria()