import chromadb
from pathlib import Path
from .config import settings
from .llm_client import obtener_embedding

# Inicializar ChromaDB (Base de datos local)
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manual_conocimiento")

def leer_archivo(ruta: Path):
    # Simplificado para TXT por ahora. Si usas PDF real avísame para darte el código extra.
    try:
        return ruta.read_text(encoding="utf-8")
    except:
        return ""

def indexar_documentacion():
    print("--- Indexando Documentación ---")
    archivos = list(settings.DOCS_DIR.glob("*.txt")) # Lee TXTs de la carpeta docs
    
    if not archivos:
        print("¡OJO! No hay manuales en inputs/docs/")
        return

    for archivo in archivos:
        texto = leer_archivo(archivo)
        # Cortamos el texto en trozos de 1000 caracteres (chunks)
        chunks = [texto[i:i+settings.CHUNK_SIZE] for i in range(0, len(texto), settings.CHUNK_SIZE)]
        
        ids = [f"{archivo.name}_{i}" for i in range(len(chunks))]
        embeddings = [obtener_embedding(chunk) for chunk in chunks] # Usamos OpenAI para vectorizar
        
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"fuente": archivo.name} for _ in chunks]
        )
        print(f"Procesado: {archivo.name}")

def buscar_contexto(query):
    query_emb = obtener_embedding(query)
    resultados = collection.query(query_embeddings=[query_emb], n_results=settings.TOP_K_RETRIEVAL)
    return "\n\n".join(resultados['documents'][0])