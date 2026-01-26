"""
Sistema RAG v4.0 - Múltiples Colecciones Especializadas

CAMBIOS PRINCIPALES:
- Arquitectura multi-colección para mejor organización
- Colecciones separadas: manuales, buenas_practicas, evaluaciones, dossiers
- Mejor rendimiento: búsquedas más rápidas en colecciones específicas
- Mantenimiento simplificado: actualizar una colección no afecta otras
"""
import os
from typing import List, Dict, Optional
import chromadb
import chromadb.utils.embedding_functions as embedding_functions
from .config import settings, centauro_config

# ==================== INICIALIZACIÓN ====================

# Función de embeddings compartida
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=settings.OPENAI_API_KEY,
    model_name=settings.MODELO_EMBEDDING
)

# Cliente ChromaDB persistente
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))


# ==================== COLECCIONES ESPECIALIZADAS ====================

def get_collection(collection_name: str):
    """
    Obtiene o crea una colección específica.

    Args:
        collection_name: Nombre de la colección (usar constantes de centauro_config)

    Returns:
        Colección de ChromaDB
    """
    return chroma_client.get_or_create_collection(
        name=collection_name,
        embedding_function=openai_ef
    )


# Colecciones principales
collection_manuales = get_collection(centauro_config.COLLECTION_MANUALES)
collection_buenas_practicas = get_collection(centauro_config.COLLECTION_BUENAS_PRACTICAS)
collection_evaluaciones = get_collection(centauro_config.COLLECTION_EVALUACIONES)
collection_dossiers = get_collection(centauro_config.COLLECTION_DOSSIERS)

# Colección legacy para compatibilidad hacia atrás
collection = collection_manuales  # Default para código legacy


# ==================== INDEXACIÓN: MANUALES GENERALES ====================

def indexar_manuales_generales():
    """
    Indexa manuales generales (01_fase_investigacion.txt, etc.)
    en la colección 'manuales_generales'.

    Estos documentos contienen las reglas base del sistema.
    """
    print("--- 📚 Indexando Manuales Generales ---")

    docs_dir = settings.INPUTS_DIR / "docs"

    if not docs_dir.exists():
        print(f"⚠️ La carpeta {docs_dir} no existe. Creándola...")
        os.makedirs(docs_dir, exist_ok=True)
        return

    # Solo archivos .txt en raíz (excluir subcarpetas)
    archivos = [f for f in docs_dir.glob("*.txt") if f.is_file()]

    if not archivos:
        print(f"⚠️ No hay manuales .txt en '{docs_dir}'")
        return

    count_chunks_total = 0

    for archivo in archivos:
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                texto = f.read()

            if not texto:
                continue

            # Chunking con configuración centralizada
            chunk_size = centauro_config.RAG_CHUNK_SIZE
            overlap = centauro_config.RAG_CHUNK_OVERLAP
            chunks = []

            for i in range(0, len(texto), chunk_size - overlap):
                chunks.append(texto[i : i + chunk_size])

            if not chunks:
                continue

            # IDs y metadatos
            ids = [f"{archivo.name}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "fuente": archivo.name,
                    "chunk_id": i,
                    "tipo": "manual_general"
                }
                for i in range(len(chunks))
            ]

            # Upsert en colección de manuales
            collection_manuales.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            count_chunks_total += len(chunks)
            print(f"   📄 {archivo.name} ({len(chunks)} fragmentos)")

        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")

    print(f"✅ Manuales indexados: {collection_manuales.count()} fragmentos totales")


# ==================== INDEXACIÓN: BUENAS PRÁCTICAS ====================

def indexar_buenas_practicas():
    """
    Indexa ejemplos de buenas prácticas en colección separada.

    Permite búsquedas específicas sin mezclar con manuales generales.
    """
    print("\n--- 📚 Indexando Buenas Prácticas ---")

    bp_dir = settings.INPUTS_DIR / "docs" / "buenas_practicas"

    if not bp_dir.exists():
        print(f"⚠️ La carpeta {bp_dir} no existe.")
        return

    archivos = list(bp_dir.glob("*.txt"))

    if not archivos:
        print(f"⚠️ No hay ejemplos .txt en '{bp_dir}'")
        return

    count_chunks_total = 0

    for archivo in archivos:
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                texto = f.read()

            if not texto:
                continue

            # Chunking
            chunk_size = centauro_config.RAG_CHUNK_SIZE
            overlap = centauro_config.RAG_CHUNK_OVERLAP
            chunks = []

            for i in range(0, len(texto), chunk_size - overlap):
                chunks.append(texto[i : i + chunk_size])

            if not chunks:
                continue

            # Metadatos enriquecidos para buenas prácticas
            ids = [f"bp_{archivo.name}_{i}" for i in range(len(chunks))]

            # Extraer sección del nombre de archivo (admision_economica_ejemplo_001.txt)
            seccion = archivo.name.split("_ejemplo_")[0] if "_ejemplo_" in archivo.name else "general"

            metadatas = [
                {
                    "fuente": archivo.name,
                    "chunk_id": i,
                    "tipo": "buena_practica",
                    "seccion": seccion
                }
                for i in range(len(chunks))
            ]

            # Upsert en colección de buenas prácticas
            collection_buenas_practicas.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            count_chunks_total += len(chunks)

        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")

    print(f"✅ Buenas prácticas indexadas: {collection_buenas_practicas.count()} fragmentos totales")


# ==================== INDEXACIÓN: DOSSIERS (SI EXISTEN) ====================

def indexar_dossiers():
    """
    Indexa dossiers de programas si fueron procesados.

    Opcional: solo si existe outputs/dossiers_procesados/
    """
    print("\n--- 📚 Indexando Dossiers de Programas ---")

    dossiers_dir = settings.OUTPUTS_DIR / "dossiers_procesados"

    if not dossiers_dir.exists():
        print(f"   ℹ️ No hay dossiers procesados (carpeta no existe)")
        return

    archivos = list(dossiers_dir.glob("*.txt"))

    if not archivos:
        print(f"   ℹ️ No hay dossiers .txt procesados")
        return

    count_chunks_total = 0

    for archivo in archivos:
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                texto = f.read()

            if not texto:
                continue

            # Chunking
            chunk_size = centauro_config.RAG_CHUNK_SIZE
            overlap = centauro_config.RAG_CHUNK_OVERLAP
            chunks = []

            for i in range(0, len(texto), chunk_size - overlap):
                chunks.append(texto[i : i + chunk_size])

            if not chunks:
                continue

            ids = [f"dossier_{archivo.stem}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "fuente": archivo.name,
                    "chunk_id": i,
                    "tipo": "dossier",
                    "programa": archivo.stem  # Nombre del programa
                }
                for i in range(len(chunks))
            ]

            collection_dossiers.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            count_chunks_total += len(chunks)

        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")

    if count_chunks_total > 0:
        print(f"✅ Dossiers indexados: {collection_dossiers.count()} fragmentos totales")


# ==================== FUNCIÓN PRINCIPAL ====================

def indexar_documentacion():
    """
    Indexa TODOS los documentos en sus colecciones correspondientes.

    Esta función reemplaza la indexación monolítica anterior.
    """
    print("\n" + "="*70)
    print("🚀 SISTEMA RAG v4.0 - INDEXACIÓN MULTI-COLECCIÓN")
    print("="*70 + "\n")

    indexar_manuales_generales()
    indexar_buenas_practicas()
    indexar_dossiers()

    print("\n" + "="*70)
    print("📊 RESUMEN DE INDEXACIÓN:")
    print(f"   • Manuales generales: {collection_manuales.count()} fragmentos")
    print(f"   • Buenas prácticas: {collection_buenas_practicas.count()} fragmentos")
    print(f"   • Evaluaciones históricas: {collection_evaluaciones.count()} fragmentos")
    print(f"   • Dossiers programas: {collection_dossiers.count()} fragmentos")
    print("="*70 + "\n")


# ==================== BÚSQUEDA SIMPLIFICADA ====================

def buscar_contexto(
    query_texto: str,
    collection_name: str = None,
    n_results: int = None
) -> str:
    """
    Busca fragmentos relevantes en una colección específica.

    Args:
        query_texto: Texto de búsqueda
        collection_name: Nombre de colección (None = manuales_generales)
        n_results: Número de resultados (None = usar config)

    Returns:
        Contexto concatenado
    """
    # Determinar colección
    if collection_name is None:
        col = collection_manuales
    elif collection_name == centauro_config.COLLECTION_MANUALES:
        col = collection_manuales
    elif collection_name == centauro_config.COLLECTION_BUENAS_PRACTICAS:
        col = collection_buenas_practicas
    elif collection_name == centauro_config.COLLECTION_EVALUACIONES:
        col = collection_evaluaciones
    elif collection_name == centauro_config.COLLECTION_DOSSIERS:
        col = collection_dossiers
    else:
        col = collection_manuales  # Fallback

    # Determinar n_results
    if n_results is None:
        n_results = centauro_config.RAG_TOP_K_GENERAL

    total_docs = col.count()
    if total_docs == 0:
        return ""

    k_seguro = min(n_results, total_docs)

    resultados = col.query(
        query_texts=[query_texto],
        n_results=k_seguro
    )

    if not resultados['documents']:
        return ""

    lista_documentos = resultados['documents'][0]
    contexto_unido = "\n\n--- FRAGMENTO DEL MANUAL ---\n".join(lista_documentos)

    return contexto_unido


def buscar_en_coleccion(
    query: str,
    collection_name: str,
    k: int = 5,
    filtro_metadata: Dict = None
) -> List[Dict]:
    """
    Búsqueda avanzada con filtros de metadata.

    Args:
        query: Texto de búsqueda
        collection_name: Nombre de colección
        k: Número de resultados
        filtro_metadata: Filtros adicionales (ej: {"seccion": "cierre"})

    Returns:
        Lista de diccionarios con 'text' y 'metadata'
    """
    # Obtener colección
    if collection_name == centauro_config.COLLECTION_MANUALES:
        col = collection_manuales
    elif collection_name == centauro_config.COLLECTION_BUENAS_PRACTICAS:
        col = collection_buenas_practicas
    elif collection_name == centauro_config.COLLECTION_EVALUACIONES:
        col = collection_evaluaciones
    elif collection_name == centauro_config.COLLECTION_DOSSIERS:
        col = collection_dossiers
    else:
        return []

    total_docs = col.count()
    if total_docs == 0:
        return []

    k_seguro = min(k, total_docs)

    # Búsqueda con o sin filtro
    if filtro_metadata:
        resultados = col.query(
            query_texts=[query],
            n_results=k_seguro,
            where=filtro_metadata
        )
    else:
        resultados = col.query(
            query_texts=[query],
            n_results=k_seguro
        )

    if not resultados['documents'] or not resultados['documents'][0]:
        return []

    docs = resultados['documents'][0]
    metadatas = resultados.get('metadatas', [[{}] * len(docs)])[0]

    resultados_estructurados = []
    for doc, metadata in zip(docs, metadatas):
        resultados_estructurados.append({
            'text': doc,
            'metadata': metadata
        })

    return resultados_estructurados
