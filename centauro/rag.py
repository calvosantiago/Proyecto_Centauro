import chromadb
from pathlib import Path
from .config import settings
from .llm_client import obtener_embedding

# Inicializar ChromaDB (Base de datos local)
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manual_conocimiento")

def leer_archivo(ruta: Path):
    """
    Lee el contenido de un archivo de texto.
    """
    try:
        return ruta.read_text(encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Error leyendo {ruta.name}: {e}")
        return ""

def indexar_documentacion():
    print("--- Indexando Documentación ---")
    archivos = list(settings.DOCS_DIR.glob("*.txt")) # Lee TXTs de la carpeta docs
    
    if not archivos:
        print("¡OJO! No hay manuales en inputs/docs/")
        return

    # Opcional: Limpiar colección anterior para evitar duplicados si re-indexas
    # collection.delete(where={}) 
    
    count_chunks = 0
    
    for archivo in archivos:
        texto = leer_archivo(archivo)
        if not texto: continue
        
        # Cortamos el texto en trozos (chunks)
        # TRUCO: Un pequeño solapamiento (overlap) ayuda a no cortar frases a la mitad,
        # pero para mantenerlo simple usamos corte directo por ahora.
        chunks = [texto[i:i+settings.CHUNK_SIZE] for i in range(0, len(texto), settings.CHUNK_SIZE)]
        
        ids = [f"{archivo.name}_{i}" for i in range(len(chunks))]
        
        # Solo generamos embeddings si hay chunks
        if chunks:
            embeddings = [obtener_embedding(chunk) for chunk in chunks] 
            
            collection.upsert(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=[{"fuente": archivo.name} for _ in chunks]
            )
            count_chunks += len(chunks)
            print(f"Procesado: {archivo.name} ({len(chunks)} fragmentos)")

    print(f"✅ Total indexado: {count_chunks} fragmentos de conocimiento.")

def buscar_contexto(query, k=7):
    """
    Busca los fragmentos más relevantes en la base de datos.
    
    Args:
        query (str): La pregunta o temas a buscar.
        k (int): Número de fragmentos a recuperar. 
                 Lo subimos a 7 por defecto para el 'Barrido Completo'.
    """
    count = collection.count()
    if count == 0:
        return "No hay manuales indexados."
        
    # Seguridad: No pedir más chunks de los que existen
    k_seguro = min(k, count)
    
    query_emb = obtener_embedding(query)
    
    resultados = collection.query(
        query_embeddings=[query_emb], 
        n_results=k_seguro
    )
    
    # Unimos los fragmentos recuperados con separadores claros
    contexto_unido = "\n\n--- FRAGMENTO DEL MANUAL ---\n".join(resultados['documents'][0])
    return contexto_unido