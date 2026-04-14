"""
Configuración centralizada del sistema Centauro v4.0

Este archivo contiene TODOS los parámetros configurables del sistema.
Elimina "magic numbers" y facilita experimentación y mantenimiento.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    """Configuración base del sistema"""
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # Directorios
    INPUTS_DIR: Path = BASE_DIR / "inputs"
    OUTPUTS_DIR: Path = BASE_DIR / "outputs"
    CHROMA_PATH: Path = BASE_DIR / "chroma_db"

    # Configuración OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL_NAME: str = "gpt-4o-mini"
    MODELO_EMBEDDING: str = "text-embedding-3-small"

    # Configuración Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    class Config:
        env_file = ".env"
        extra = "ignore"


class CentauroConfig:
    """
    Configuración avanzada del sistema Centauro.

    Todos los thresholds, límites y parámetros del sistema están aquí.
    Cambiar estos valores afecta el comportamiento global del sistema.
    """

    # ==================== VALIDACIÓN DE ARCHIVOS ====================

    # Límite de longitud para nombres de archivo (Windows MAX_PATH = 260)
    MAX_FILENAME_LENGTH = 100  # caracteres
    MAX_PATH_LENGTH = 240  # caracteres (deja margen para operaciones)

    # Extensiones permitidas para transcripciones
    ALLOWED_EXTENSIONS = [".txt", ".vtt", ".docx"]


    # ==================== SISTEMA ANTI-ALUCINACIONES (SHERIFF) ====================

    # Umbral de similitud fuzzy para validar evidencias citadas
    # 85 = balance entre rigidez (90+) y permisividad (70-)
    SHERIFF_FUZZY_THRESHOLD = 85  # porcentaje (0-100)

    # Penalización por evidencia no verificable
    SHERIFF_CONFIDENCE_PENALTY_NO_EVIDENCE = 0.3  # reduce confianza en 30%


    # ==================== RAG: CHUNKING Y INDEXACIÓN ====================

    # Tamaño de chunks para dividir documentos
    # 1000 = ~250 palabras, balance entre contexto y granularidad
    RAG_CHUNK_SIZE = 1000  # caracteres

    # Overlap entre chunks para mantener contexto
    # 250 = 25% overlap, previene pérdida de información en límites
    RAG_CHUNK_OVERLAP = 250  # caracteres

    # Número de fragmentos a recuperar en búsquedas generales
    # Reducido de 20 a 5 para optimizar tokens
    RAG_TOP_K_GENERAL = 5  # fragmentos

    # Número de ejemplos de buenas prácticas a recuperar
    # v4.3: Subido a 3 para mejor calibración de puntuaciones
    RAG_TOP_K_BUENAS_PRACTICAS = 3  # ejemplos completos

    # Umbral de relevancia semántica para filtrar fragmentos
    # 0.3 = mínimo 30% de overlap de palabras clave
    RAG_RELEVANCE_THRESHOLD = 0.3  # ratio (0.0-1.0)

    # Máximo de fragmentos finales después de filtrado
    RAG_MAX_FRAGMENTS_FINAL = 3  # fragmentos


    # ==================== RAG: MUESTREO INTELIGENTE ====================

    # Umbrales para detectar llamadas largas y aplicar muestreo
    TRANSCRIPTION_SHORT_THRESHOLD = 6000  # chars (~20 min)
    TRANSCRIPTION_LONG_THRESHOLD = 12000  # chars (~40 min)

    # Número de muestras distribuidas para análisis
    TRANSCRIPTION_SAMPLES_SHORT = 4  # muestras para llamadas 20-40 min
    TRANSCRIPTION_SAMPLES_LONG = 6  # muestras para llamadas 40+ min

    # Tamaño de cada muestra
    TRANSCRIPTION_SAMPLE_SIZE_START = 2500  # chars (inicio/fin)
    TRANSCRIPTION_SAMPLE_SIZE_MIDDLE = 2000  # chars (secciones intermedias)


    # ==================== LLM: PARÁMETROS DE GENERACIÓN ====================

    # Temperatura para evaluaciones (determinista)
    LLM_TEMPERATURE_EVALUACION = 0.0  # sin creatividad, máxima consistencia

    # Temperatura para recomendaciones (ligeramente creativo)
    LLM_TEMPERATURE_RECOMENDACIONES = 0.3  # balance

    # Temperatura para extracción de patrones (buenas prácticas)
    LLM_TEMPERATURE_PATRONES = 0.2  # semi-determinista


    # ==================== EVALUACIÓN: CALIFICACIÓN ORDINAL ====================

    # Valores válidos para calificación ordinal
    CALIFICACIONES_VALIDAS = {"MALO", "MEJORABLE", "BUENO"}

    # ==================== EVALUACIÓN: CONFIANZA ====================

    # Penalizaciones para cálculo de confianza
    CONFIDENCE_PENALTY_SHORT_EVIDENCE = 0.3  # evidencia <20 chars
    CONFIDENCE_PENALTY_VAGUE_EVIDENCE = 0.3  # "no se pudo evaluar"
    CONFIDENCE_PENALTY_SHORT_REASONING = 0.2  # razonamiento <50 chars
    CONFIDENCE_PENALTY_LOW_OBSERVABILITY = 0.2  # observabilidad BAJA

    # Longitudes mínimas para considerar respuesta válida
    MIN_EVIDENCE_LENGTH = 20  # caracteres
    MIN_REASONING_LENGTH = 50  # caracteres


    # ==================== BUENAS PRÁCTICAS ====================

    # Máximo de items por categoría en extracción de temas
    MAX_ITEMS_POR_CATEGORIA = 8  # temas/objeciones/necesidades

    # Longitud máxima de ejemplo antes de truncar en prompt
    # v4.3: Subido a 2000 para incluir ejemplos completos (~1400 chars)
    MAX_EJEMPLO_LENGTH_IN_PROMPT = 2000  # caracteres


    # ==================== MEMORIA Y APRENDIZAJE ====================

    # Límite de conversaciones históricas en RAG
    # Evita saturación: solo las mejores conversaciones
    MAX_CONVERSACIONES_EN_RAG = 500  # conversaciones

    # Calificación mínima para añadir al RAG histórico
    # Solo llamadas BUENAS se usan como ejemplos de aprendizaje
    MIN_CALIFICACION_PARA_APRENDIZAJE = "BUENO"

    # Ventana temporal para conversaciones históricas (días)
    # Rolling window: solo últimos 6 meses relevantes
    ROLLING_WINDOW_DIAS = 180  # días (~6 meses)

    # Número de evaluaciones recientes para análisis de tendencias
    EVALUACIONES_PARA_TENDENCIA = 10  # últimas evaluaciones

    # Umbral de cambio para detección de tendencias (en escala ordinal 0=MALO, 1=MEJORABLE, 2=BUENO)
    THRESHOLD_CAMBIO_SIGNIFICATIVO = 0.5  # unidades en escala 0-2


    # ==================== NOMBRES DE COLECCIONES CHROMADB ====================

    COLLECTION_MANUALES = "manuales_generales"
    COLLECTION_BUENAS_PRACTICAS = "buenas_practicas"
    COLLECTION_EVALUACIONES = "evaluaciones_historicas"
    COLLECTION_DOSSIERS = "dossiers_programas"
    COLLECTION_COACHING = "coaching_ventas"  # NUEVO: Libros y técnicas de ventas
    COLLECTION_DICCIONARIO_DATOS = "diccionario_datos"  # Diccionario del modelo semántico PBI

    # ==================== COACHING: LIBROS DE VENTAS ====================

    # Número de fragmentos de coaching a recuperar por recomendación
    RAG_TOP_K_COACHING = 2  # fragmentos de libros

    # Longitud máxima de cita de libro en feedback
    MAX_COACHING_QUOTE_LENGTH = 300  # caracteres


    # ==================== CHAT INTERACTIVO (CHAINLIT) ====================

    # Número de resultados para consultas de chat
    CHAT_RAG_TOP_K = 5  # fragmentos

    # Modo de búsqueda: "general" | "buenas_practicas" | "evaluaciones"
    CHAT_DEFAULT_MODE = "general"

    # Historial de conversación (mensajes)
    CHAT_MAX_HISTORY = 10  # mensajes anteriores en contexto


# Instancia global de configuración
settings = Settings()
centauro_config = CentauroConfig()

# Crear directorios necesarios
settings.INPUTS_DIR.mkdir(parents=True, exist_ok=True)
(settings.INPUTS_DIR / "docs").mkdir(parents=True, exist_ok=True)
(settings.INPUTS_DIR / "docs" / "buenas_practicas").mkdir(parents=True, exist_ok=True)
(settings.INPUTS_DIR / "docs" / "coaching_ventas").mkdir(parents=True, exist_ok=True)  # NUEVO
settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_PATH.mkdir(parents=True, exist_ok=True)
