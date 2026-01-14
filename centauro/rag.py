import os
import chromadb
import chromadb.utils.embedding_functions as embedding_functions
from .config import settings

# 1. Configurar la función de Embeddings (Nativa de Chroma + OpenAI)
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=settings.OPENAI_API_KEY,
    model_name=settings.MODELO_EMBEDDING
)

# 2. Inicializar el Cliente de ChromaDB
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))

# 3. Obtener o crear la colección
collection = chroma_client.get_or_create_collection(
    name="manual_conocimiento",
    embedding_function=openai_ef
)

def indexar_documentacion():
    """
    Lee los manuales .txt de la carpeta inputs/docs, los trocea y los guarda en la BD vectorial.
    """
    print("--- 📚 Iniciando Indexación RAG ---")
    
    # Restauramos TU ruta original: inputs/docs
    docs_dir = settings.INPUTS_DIR / "docs"
    
    # Crear carpeta si no existe
    if not docs_dir.exists():
        print(f"⚠️ La carpeta {docs_dir} no existe. Creándola...")
        os.makedirs(docs_dir, exist_ok=True)
        return

    archivos = list(docs_dir.glob("*.txt"))
    
    if not archivos:
        print(f"⚠️ Alerta: No hay archivos .txt en '{docs_dir}'. El sistema no tendrá conocimientos.")
        return

    count_chunks_total = 0
    
    for archivo in archivos:
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                texto = f.read()
                
            if not texto: continue
            
            # TU ESTRATEGIA DE CHUNKING ORIGINAL:
            chunk_size = 1000
            overlap = 250
            chunks = []
            
            for i in range(0, len(texto), chunk_size - overlap):
                chunks.append(texto[i : i + chunk_size])
            
            if not chunks: continue

            # Preparamos metadatos e IDs para Chroma
            ids = [f"{archivo.name}_{i}" for i in range(len(chunks))]
            metadatas = [{"fuente": archivo.name, "chunk_id": i} for i in range(len(chunks))]
            
            # UPSERT
            collection.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )
            
            count_chunks_total += len(chunks)
            print(f"   📄 Procesado: {archivo.name} ({len(chunks)} fragmentos)")
            
        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")

    print(f"✅ Indexación completada. Total fragmentos en memoria: {collection.count()}")

def buscar_contexto(query_texto, n_results=20):
    """
    Busca los fragmentos más relevantes.
    MODIFICACIÓN: n_results=20 para asegurar que gpt-4o-mini tenga todo el contexto.
    """
    total_docs = collection.count()
    if total_docs == 0:
        return ""
        
    # Seguridad: No pedir más resultados de los que existen
    k_seguro = min(n_results, total_docs)
    
    resultados = collection.query(
        query_texts=[query_texto],
        n_results=k_seguro
    )
    
    if not resultados['documents']:
        return ""

    lista_documentos = resultados['documents'][0]
    
    # Unimos los fragmentos
    contexto_unido = "\n\n--- FRAGMENTO DEL MANUAL ---\n".join(lista_documentos)
    
    return contexto_unido