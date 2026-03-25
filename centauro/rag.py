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
from openai import OpenAI
from .config import settings, centauro_config
from .llm_client import registrar_gasto_embedding

# ==================== INICIALIZACIÓN ====================

class LoggingOpenAIEmbeddingFunction:
    """
    Embedding function compatible con Chroma que registra coste/uso en control_gastos.csv.
    """

    def __init__(self, api_key: str, model_name: str):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
        self.api_key = api_key

    @staticmethod
    def name() -> str:
        return "logging_openai_embedding"

    def get_config(self) -> Dict[str, str]:
        return {
            "api_key": self.api_key,
            "model_name": self.model_name,
        }

    @staticmethod
    def build_from_config(config: Dict[str, str]) -> "LoggingOpenAIEmbeddingFunction":
        return LoggingOpenAIEmbeddingFunction(
            api_key=config["api_key"],
            model_name=config["model_name"],
        )

    def __call__(self, input: List[str]) -> List[List[float]]:
        texts = [str(t) for t in input]
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts
        )
        if response.usage:
            registrar_gasto_embedding(
                referencia=f"chroma_embedding_batch_{len(texts)}",
                total_tokens=getattr(response.usage, "total_tokens", 0),
                model_name=self.model_name,
                request_id=getattr(response, "id", ""),
            )
        return [item.embedding for item in response.data]

    def embed_query(self, input: List[str]) -> List[List[float]]:
        """Compatibilidad con ChromaDB 1.x (requiere embed_query además de __call__)."""
        return self.__call__(input)


# Función de embeddings compartida
openai_ef = LoggingOpenAIEmbeddingFunction(
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
    try:
        return chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=openai_ef
        )
    except ValueError as e:
        # Compatibilidad con colecciones existentes creadas con otra EF persistida.
        # IMPORTANTE: get_collection sin embedding_function falla con UUID inexistente;
        # hay que volver a pasar openai_ef para que ChromaDB resuelva correctamente.
        if "embedding function already exists" in str(e):
            return chroma_client.get_or_create_collection(
                name=collection_name,
                embedding_function=openai_ef
            )
        raise


# Colecciones principales
collection_manuales = get_collection(centauro_config.COLLECTION_MANUALES)
collection_buenas_practicas = get_collection(centauro_config.COLLECTION_BUENAS_PRACTICAS)
collection_evaluaciones = get_collection(centauro_config.COLLECTION_EVALUACIONES)
collection_dossiers = get_collection(centauro_config.COLLECTION_DOSSIERS)
collection_coaching = get_collection(centauro_config.COLLECTION_COACHING)  # NUEVO
collection_diccionario_datos = get_collection(centauro_config.COLLECTION_DICCIONARIO_DATOS)

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

# Mapeo de nombres de subcarpeta a nombres de bloque del sistema
SECCION_TO_BLOQUE = {
    "investigacion": "Investigación",
    "propuesta_valor": "Propuesta de valor Institución y Programa",
    "admision_economica": "Proceso de Admisión y Propuesta Económica",
    "cierre": "Cierre y próximos pasos",
    "objeciones": "Manejo de objeciones",
    "estilo": "Estilo y comunicación"
}

def indexar_buenas_practicas():
    """
    Indexa ejemplos de buenas prácticas organizados por subcarpetas.

    Estructura esperada:
        buenas_practicas/
            investigacion/
                ejemplo_001.txt
            propuesta_valor/
                ejemplo_002.txt
            admision_economica/
                ejemplo_003.txt
            cierre/
                ejemplo_004.txt
            objeciones/
                ejemplo_005.txt

    La sección se detecta por el nombre de la subcarpeta.
    """
    print("\n--- Indexando Buenas Practicas por Seccion ---")

    bp_dir = settings.INPUTS_DIR / "docs" / "buenas_practicas"

    if not bp_dir.exists():
        print(f"La carpeta {bp_dir} no existe.")
        return

    count_chunks_total = 0
    secciones_indexadas = {}

    # Buscar en subcarpetas
    for subcarpeta in bp_dir.iterdir():
        if not subcarpeta.is_dir():
            continue

        seccion_key = subcarpeta.name.lower()
        seccion_bloque = SECCION_TO_BLOQUE.get(seccion_key, seccion_key)

        archivos = list(subcarpeta.glob("*.txt"))
        if not archivos:
            continue

        seccion_chunks = 0

        for archivo in archivos:
            try:
                with open(archivo, "r", encoding="utf-8") as f:
                    texto = f.read()

                if not texto:
                    continue

                # v4.3: Indexar cada ejemplo COMPLETO (sin chunking)
                # Los ejemplos son ~1000-1800 chars, se benefician de
                # indexarse enteros para que el RAG recupere el ejemplo
                # completo con todas sus técnicas y patrones.
                doc_id = f"bp_{seccion_key}_{archivo.stem}"
                metadata = {
                    "fuente": archivo.name,
                    "chunk_id": 0,
                    "tipo": "buena_practica",
                    "seccion": seccion_bloque,
                    "seccion_key": seccion_key
                }

                collection_buenas_practicas.upsert(
                    ids=[doc_id],
                    documents=[texto],
                    metadatas=[metadata]
                )

                seccion_chunks += 1
                count_chunks_total += 1

            except Exception as e:
                print(f"   Error procesando {archivo.name}: {e}")

        if seccion_chunks > 0:
            secciones_indexadas[seccion_bloque] = seccion_chunks
            print(f"   {seccion_bloque}: {seccion_chunks} fragmentos")

    if count_chunks_total > 0:
        print(f"Buenas practicas indexadas: {count_chunks_total} fragmentos totales")
    else:
        print("   No se encontraron archivos en las subcarpetas.")
        print("   Estructura esperada: buenas_practicas/[seccion]/*.txt")
        print("   Secciones validas: investigacion, propuesta_valor, admision_economica, cierre, objeciones")


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


# ==================== INDEXACIÓN: COACHING / LIBROS DE VENTAS ====================

def indexar_coaching_ventas():
    """
    Indexa libros y materiales de coaching de ventas.

    Carpeta: inputs/docs/coaching_ventas/
    Formato recomendado de archivos:
        - spin_selling_rackham.txt
        - never_split_difference_voss.txt
        - challenger_sale_dixon.txt
        etc.

    Cada archivo debe contener fragmentos estructurados con:
        - Nombre de la técnica
        - Autor/Libro de referencia
        - Explicación de la técnica
        - Ejemplo de aplicación
    """
    print("\n--- 📖 Indexando Coaching / Libros de Ventas ---")

    coaching_dir = settings.INPUTS_DIR / "docs" / "coaching_ventas"

    if not coaching_dir.exists():
        print(f"   ℹ️ Carpeta {coaching_dir} no existe aún. Se creará cuando añadas libros.")
        return

    archivos = list(coaching_dir.glob("*.txt"))

    if not archivos:
        print(f"   ℹ️ No hay libros .txt en '{coaching_dir}'")
        print(f"   💡 Añade fragmentos de libros de ventas aquí para enriquecer el coaching")
        return

    count_chunks_total = 0

    for archivo in archivos:
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                texto = f.read()

            if not texto:
                continue

            # Extraer autor/libro del nombre de archivo
            # Formato esperado: tecnica_autor.txt o libro_autor.txt
            nombre_base = archivo.stem
            partes = nombre_base.rsplit("_", 1)
            if len(partes) == 2:
                tema, autor = partes
            else:
                tema = nombre_base
                autor = "desconocido"

            # CHUNKING SEMÁNTICO: Respetar secciones de técnicas
            # Soporta dos formatos de separador:
            #   - SPIN style:       ================ (10+ signos =) antes del header
            #   - Influencia style: === TÉCNICA: ... (header directo sin separador largo)
            # El lookahead (?=\n=== ) parte justo antes de cada nueva técnica
            # sin consumir el header; los chunks vacíos se filtran por len < 50
            import re
            secciones = re.split(r'={10,}|(?=\n=== )', texto)

            chunks = []
            for seccion in secciones:
                seccion = seccion.strip()
                if not seccion or len(seccion) < 50:
                    continue

                # Si la sección es muy grande (>3000 chars), subdividirla
                if len(seccion) > 3000:
                    # Subdividir respetando párrafos
                    parrafos = seccion.split('\n\n')
                    chunk_actual = ""
                    for parrafo in parrafos:
                        if len(chunk_actual) + len(parrafo) > 2500 and chunk_actual:
                            chunks.append(chunk_actual.strip())
                            chunk_actual = parrafo
                        else:
                            chunk_actual += "\n\n" + parrafo if chunk_actual else parrafo
                    if chunk_actual.strip():
                        chunks.append(chunk_actual.strip())
                else:
                    chunks.append(seccion)

            if not chunks:
                continue

            ids = [f"coaching_{archivo.stem}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "fuente": archivo.name,
                    "chunk_id": i,
                    "tipo": "coaching",
                    "tema": tema.replace("_", " ").title(),
                    "autor": autor.replace("_", " ").title()
                }
                for i in range(len(chunks))
            ]

            collection_coaching.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            count_chunks_total += len(chunks)
            print(f"   📖 {archivo.name} ({len(chunks)} técnicas) - Autor: {autor}")

        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")

    if count_chunks_total > 0:
        print(f"✅ Coaching indexado: {collection_coaching.count()} fragmentos totales")


# ==================== INDEXACIÓN: DICCIONARIO MODELO SEMÁNTICO ====================

def indexar_diccionario_datos():
    """
    Indexa el diccionario del modelo semántico de Power BI para el RAG de consultas DAX.

    Carpeta: inputs/docs/diccionario_datos/
    Formato: Entradas delimitadas por '===' en línea propia.
    Cada entrada se indexa completa (sin chunking) para mantener contexto.
    """
    import re as _re

    print("\n--- 📊 Indexando Diccionario del Modelo Semántico ---")

    diccionario_dir = settings.INPUTS_DIR / "docs" / "diccionario_datos"

    if not diccionario_dir.exists():
        print(f"   ℹ️ Carpeta {diccionario_dir} no existe. Diccionario PBI no disponible.")
        return

    archivos = list(diccionario_dir.glob("*.txt"))
    if not archivos:
        print(f"   ℹ️ No hay archivos .txt en '{diccionario_dir}'")
        return

    count_entries = 0

    for archivo in archivos:
        try:
            texto = archivo.read_text(encoding="utf-8")
            if not texto:
                continue

            # Partir por delimitador ===
            entradas_raw = _re.split(r'\n===\s*\n', texto)
            entradas = []
            for e in entradas_raw:
                e = e.strip()
                # Filtrar cabecera del archivo y entradas vacías
                if not e or len(e) < 30 or e.startswith("DICCIONARIO DEL MODELO"):
                    continue
                entradas.append(e)

            if not entradas:
                continue

            ids = [f"dict_{archivo.stem}_{i}" for i in range(len(entradas))]
            metadatas = []
            for i, entry in enumerate(entradas):
                # Extraer tipo de la entrada (MEDIDA, TABLA, GLOSARIO, etc.)
                tipo_match = _re.search(r'TIPO:\s*(\S+)', entry)
                tipo = tipo_match.group(1) if tipo_match else "general"
                # Extraer nombre/término
                nombre_match = _re.search(r'(?:Nombre|Término):\s*(.+)', entry)
                nombre = nombre_match.group(1).strip() if nombre_match else f"entry_{i}"
                metadatas.append({
                    "fuente": archivo.name,
                    "tipo": f"diccionario_{tipo.lower()}",
                    "nombre": nombre,
                    "chunk_id": i,
                })

            collection_diccionario_datos.upsert(
                ids=ids,
                documents=entradas,
                metadatas=metadatas,
            )

            count_entries += len(entradas)
            print(f"   📊 {archivo.name} ({len(entradas)} entradas)")

        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")

    if count_entries > 0:
        print(f"✅ Diccionario datos indexado: {collection_diccionario_datos.count()} entradas totales")


# ==================== ESTADÍSTICAS DE TOKENS ====================

def _contar_tokens_colecciones() -> dict:
    """
    Cuenta tokens aproximados en todas las colecciones de documentación.
    Recupera los textos almacenados en ChromaDB y suma sus caracteres.
    Aproximación: 4 chars = 1 token (válido para español/inglés con OpenAI).

    Returns:
        dict con stats por colección y totales. Ej:
        {
            "manuales":        {"fragmentos": 70, "tokens": 17000},
            "buenas_practicas":{"fragmentos": 42, "tokens": 13500},
            "coaching":        {"fragmentos": 90, "tokens": 89000},
            "dossiers":        {"fragmentos":  0, "tokens":     0},
            "_total":          {"fragmentos":202, "tokens":119500},
        }
    """
    colecciones_map = {
        "manuales":         collection_manuales,
        "buenas_practicas": collection_buenas_practicas,
        "coaching":         collection_coaching,
        "dossiers":         collection_dossiers,
        "diccionario_datos": collection_diccionario_datos,
    }

    stats = {}
    total_chars = 0
    total_frags = 0

    for nombre, col in colecciones_map.items():
        n = col.count()
        if n == 0:
            stats[nombre] = {"fragmentos": 0, "tokens": 0}
            continue

        chars = 0
        offset = 0
        batch = 500
        while offset < n:
            resultado = col.get(limit=batch, offset=offset, include=["documents"])
            for doc in resultado["documents"]:
                if doc:
                    chars += len(doc)
            offset += batch

        tokens = chars // 4
        stats[nombre] = {"fragmentos": n, "tokens": tokens}
        total_chars += chars
        total_frags += n

    stats["_total"] = {"fragmentos": total_frags, "tokens": total_chars // 4}
    return stats


def _imprimir_resumen_tokens(stats: dict) -> None:
    """Imprime tabla de tokens por colección con coste estimado de re-indexación."""
    total = stats.get("_total", {})
    tokens_total = total.get("tokens", 0)
    coste = (tokens_total / 1_000_000) * 0.02  # text-embedding-3-small: $0.02/1M tokens

    print("\n   Tokens en base de conocimiento (aprox. 4 chars/token):")
    for nombre, s in stats.items():
        if nombre == "_total":
            continue
        frags = s["fragmentos"]
        tok   = s["tokens"]
        barra = "#" * min(tok // 2000, 20)
        print(f"   • {nombre:<20} {frags:>4} frags   ~{tok:>7,} tokens  {barra}")

    print(f"   {'─'*52}")
    print(f"   {'TOTAL':<20} {total.get('fragmentos',0):>4} frags   ~{tokens_total:>7,} tokens")
    print(f"   Coste re-indexar: ${coste:.4f} USD (text-embedding-3-small)")


# ==================== FUNCIÓN PRINCIPAL ====================

def indexar_documentacion():
    """
    Indexa TODOS los documentos en sus colecciones correspondientes.

    Esta función reemplaza la indexación monolítica anterior.
    """
    print("\n" + "="*70)
    print("SISTEMA RAG v4.1 - INDEXACION MULTI-COLECCION + COACHING")
    print("="*70 + "\n")

    indexar_manuales_generales()
    indexar_buenas_practicas()
    indexar_coaching_ventas()  # NUEVO
    indexar_dossiers()
    indexar_diccionario_datos()

    print("\n" + "="*70)
    print("📊 RESUMEN DE INDEXACIÓN:")
    print(f"   • Manuales generales: {collection_manuales.count()} fragmentos")
    print(f"   • Buenas prácticas: {collection_buenas_practicas.count()} fragmentos")
    print(f"   • Coaching/Libros: {collection_coaching.count()} fragmentos")
    print(f"   • Evaluaciones históricas: {collection_evaluaciones.count()} fragmentos")
    print(f"   • Dossiers programas: {collection_dossiers.count()} fragmentos")
    print(f"   • Diccionario datos PBI: {collection_diccionario_datos.count()} entradas")
    _imprimir_resumen_tokens(_contar_tokens_colecciones())
    print("="*70 + "\n")


# ==================== INDEXACIÓN INTELIGENTE CON HASH ====================

def _calcular_hash_inputs() -> str:
    """
    Calcula un hash MD5 de todos los archivos de documentación.
    Usa nombre + mtime + tamaño de cada archivo (sin leer contenido),
    lo que lo hace muy rápido (~1ms para cientos de archivos).
    """
    import hashlib

    hasher = hashlib.md5()

    # Monitorizar todos los .txt bajo inputs/docs/ (manuales, buenas_practicas, coaching)
    docs_dir = settings.INPUTS_DIR / "docs"
    archivos = sorted(docs_dir.rglob("*.txt")) if docs_dir.exists() else []

    for archivo in archivos:
        stat = archivo.stat()
        hasher.update(str(archivo).encode())
        hasher.update(str(stat.st_mtime).encode())
        hasher.update(str(stat.st_size).encode())

    return hasher.hexdigest()


def _leer_hash_guardado() -> str:
    """Lee el hash guardado de la última indexación."""
    hash_file = settings.CHROMA_PATH / ".index_hash"
    if hash_file.exists():
        return hash_file.read_text(encoding="utf-8").strip()
    return ""


def _guardar_hash(hash_value: str) -> None:
    """Guarda el hash de la indexación actual."""
    settings.CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    hash_file = settings.CHROMA_PATH / ".index_hash"
    hash_file.write_text(hash_value, encoding="utf-8")


def _limpiar_colecciones_documentacion() -> None:
    """
    Elimina y recrea las colecciones de documentación estática.
    NO toca collection_evaluaciones (historial de evaluaciones del sistema).
    """
    global collection_manuales, collection_buenas_practicas, \
           collection_coaching, collection_dossiers, collection_diccionario_datos, collection

    colecciones_a_limpiar = [
        centauro_config.COLLECTION_MANUALES,
        centauro_config.COLLECTION_BUENAS_PRACTICAS,
        centauro_config.COLLECTION_COACHING,
        centauro_config.COLLECTION_DOSSIERS,
        centauro_config.COLLECTION_DICCIONARIO_DATOS,
    ]

    for nombre in colecciones_a_limpiar:
        try:
            chroma_client.delete_collection(nombre)
            print(f"   🗑️  Colección '{nombre}' limpiada")
        except Exception:
            pass  # No existía, no hay problema

    # Recrear referencias globales con colecciones vacías
    collection_manuales = get_collection(centauro_config.COLLECTION_MANUALES)
    collection_buenas_practicas = get_collection(centauro_config.COLLECTION_BUENAS_PRACTICAS)
    collection_coaching = get_collection(centauro_config.COLLECTION_COACHING)
    collection_dossiers = get_collection(centauro_config.COLLECTION_DOSSIERS)
    collection_diccionario_datos = get_collection(centauro_config.COLLECTION_DICCIONARIO_DATOS)
    collection = collection_manuales  # alias legacy


def indexar_si_necesario() -> dict:
    """
    Indexa la documentación solo si los archivos han cambiado.

    Compara un hash MD5 de todos los archivos de inputs/docs/ con el
    guardado en chroma_db/.index_hash. Si son iguales y las colecciones
    tienen datos, no hace nada. Si hay diferencias, re-indexa desde cero.

    Ventajas frente al check 'total_docs == 0':
    - Detecta archivos nuevos, modificados o eliminados automáticamente
    - No requiere borrar chroma_db/ manualmente
    - Cero coste en arranques normales (solo un stat() por archivo)

    Returns:
        dict con claves: re_indexado (bool), manuales, buenas_practicas,
        coaching, motivo (str)
    """
    hash_actual = _calcular_hash_inputs()
    hash_guardado = _leer_hash_guardado()

    # Contar docs actuales en colecciones
    try:
        n_manuales = collection_manuales.count()
        n_bp = collection_buenas_practicas.count()
        n_coaching = collection_coaching.count()
        total_actual = n_manuales + n_bp + n_coaching
    except Exception:
        total_actual = 0

    # Condiciones para saltar indexación
    if hash_actual == hash_guardado and total_actual > 0:
        print(f"✅ Base de conocimiento sin cambios "
              f"({n_manuales} manuales + {n_bp} buenas prácticas + {n_coaching} coaching)")
        _imprimir_resumen_tokens(_contar_tokens_colecciones())
        return {
            "re_indexado": False,
            "manuales": n_manuales,
            "buenas_practicas": n_bp,
            "coaching": n_coaching,
            "motivo": "sin_cambios"
        }

    # Determinar motivo
    if total_actual == 0:
        motivo = "primera_vez"
        print("📚 Primera indexación (base de conocimiento vacía)...")
    else:
        motivo = "archivos_cambiados"
        print("🔄 Cambios detectados en documentación, re-indexando...")
        _limpiar_colecciones_documentacion()

    # Re-indexar todo
    indexar_documentacion()

    # Guardar nuevo hash
    _guardar_hash(hash_actual)

    return {
        "re_indexado": True,
        "manuales": collection_manuales.count(),
        "buenas_practicas": collection_buenas_practicas.count(),
        "coaching": collection_coaching.count(),
        "motivo": motivo
    }


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
    elif collection_name == centauro_config.COLLECTION_COACHING:
        col = collection_coaching
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
