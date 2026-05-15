"""
CENTAURO BATCH PROCESSOR v1.0
==============================
Procesamiento automático de entrevistas sin interfaz de usuario.

Igual que el flujo de Chainlit (mismos agentes, mismos criterios, misma escritura
en Supabase), pero sin interacción humana y sin generar PDF.

CARPETA DE ENTRADA: inputs/batch/
  Deposita aquí los archivos de entrevista antes de ejecutar el script.
  Formatos soportados: .txt  .vtt  .docx  .mp3  .mp4

CONVENCIÓN DE NOMBRE DE ARCHIVO (obligatoria):
  <opportunity_id>_<NombreAsesor>[_descripcion].<ext>
  Ejemplo:  2024-001234_Alicia Ramos_MBA.mp4
            2024-001234_Alicia_Ramos.vtt
  El opportunity_id (YYYY-NNNNNN...) es necesario para la deduplicación.
  El nombre del asesor se extrae del texto restante con fuzzy matching.

EJECUCIÓN MANUAL:
  python batch_processor.py

PROGRAMAR CON WINDOWS TASK SCHEDULER:
  1. Abre "Programador de tareas" → "Crear tarea básica"
  2. Disparador: diario / cada hora según necesidad
  3. Acción → Programa: python.exe  (o la ruta completa del .venv)
     Argumentos: batch_processor.py
     Iniciar en: <ruta del proyecto>
  Alternativa PowerShell:
     .venv\\Scripts\\python.exe batch_processor.py

LOG DE EJECUCIONES: outputs/batch_log.txt
"""

import os
import re
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

# Cargar .env antes de importar módulos de centauro
load_dotenv(Path(__file__).resolve().parent / ".env")

from centauro.config import settings
from centauro.rag import indexar_si_necesario
from centauro.core import CentauroOrchestrator
from centauro.core.memoria import MemoryManager
from centauro.core.gestion_asesores import GestionAsesores
from centauro.core.database import get_database
from centauro.utils.validaciones import extraer_opportunity_id

# ── Configuración ────────────────────────────────────────────────────────────
BATCH_INPUT_DIR = settings.INPUTS_DIR / "batch"
SUPPORTED_EXTENSIONS = {".txt", ".vtt", ".docx", ".mp3", ".mp4"}


# ── Logging (consola + archivo) ──────────────────────────────────────────────
def _setup_logging() -> logging.Logger:
    log_file = settings.OUTPUTS_DIR / "batch_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("centauro_batch")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # evitar duplicados si se reimporta

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# ── Lectura de archivos ──────────────────────────────────────────────────────
def _leer_docx(ruta: Path) -> Optional[str]:
    """Extrae texto de transcripciones Teams en formato Word."""
    try:
        from docx import Document
    except ImportError:
        return None
    try:
        doc = Document(ruta)
        transcript = []
        current_speaker = None
        current_buffer: list[str] = []
        patron = re.compile(r"^(.*?)\s+(\d{1,2}:\d{2}(?::\d{2})?)$")

        for para in doc.paragraphs:
            for line in para.text.replace("\r", "\n").split("\n"):
                text = line.strip()
                if not text:
                    continue
                text_norm = re.sub(r"\s+", " ", text)
                m = patron.match(text_norm)
                if m:
                    if current_speaker and current_buffer:
                        transcript.append(
                            f"[{current_speaker}]: {' '.join(current_buffer)}"
                        )
                    current_speaker = m.group(1).strip()
                    current_buffer = []
                elif current_speaker:
                    current_buffer.append(text)

        if current_speaker and current_buffer:
            transcript.append(f"[{current_speaker}]: {' '.join(current_buffer)}")

        return "\n\n".join(transcript) or None
    except Exception:
        return None


# ── Extracción del nombre del asesor ─────────────────────────────────────────
def _extraer_nombre_de_filename(
    filename: str,
    gestion: GestionAsesores,
    logger: logging.Logger,
) -> Optional[str]:
    """
    Extrae el nombre del asesor del nombre de archivo por fuzzy matching.

    Estrategia:
      1. Quita el prefijo opportunity_id del stem
      2. Reemplaza _ y - por espacios
      3. Prueba ventanas deslizantes de 4 → 3 → 2 palabras contra Supabase
    """
    stem = Path(filename).stem
    opp_id = extraer_opportunity_id(filename)

    texto = stem
    if opp_id:
        texto = stem[len(opp_id) :].lstrip("_-.")

    if not texto:
        return None

    texto = texto.replace("_", " ").replace("-", " ").strip()
    palabras = texto.split()

    if not palabras:
        return None

    # Ventana deslizante: más palabras primero (más preciso)
    for size in range(min(len(palabras), 4), 1, -1):
        for i in range(len(palabras) - size + 1):
            candidato = " ".join(palabras[i : i + size])
            match = gestion.buscar_asesor_similar(candidato)
            if match:
                nombre, score = match
                logger.info(f"   Asesor detectado en filename: '{nombre}' (score: {score})")
                return nombre

    logger.warning(f"   No se pudo identificar asesor en filename: '{texto}'")
    return None


# ── Validación de calidad antes de generar PDF ───────────────────────────────
def _evaluacion_valida(reporte: dict) -> bool:
    """
    Devuelve True solo si el reporte tiene suficiente calidad para enviar al asesor.
    Si falla, la evaluación se guarda en Supabase pero no se genera ni envía PDF.
    """
    bloques = reporte.get("evaluacion_por_bloques", [])
    if len(bloques) < 6:
        return False
    if any(b.get("calificacion") is None for b in bloques if isinstance(b, dict)):
        return False
    if not reporte.get("calificacion_global"):
        return False
    return True


# ── Procesador principal ─────────────────────────────────────────────────────
class BatchProcessor:
    """
    Orquesta el procesamiento automático de entrevistas en inputs/batch/.

    Flujo por archivo:
      1. Validar opportunity_id (requerido para dedup)
      2. Comprobar si ya existe en Supabase → saltar si sí
      3. Extraer nombre del asesor del filename (fuzzy matching)
      4. Cargar texto (txt/vtt/docx/mp3/mp4)
      5. Ejecutar CentauroOrchestrator (mismos agentes que Chainlit)
      6. Guardar en Supabase vía MemoryManager.registrar_evaluacion()
         (sin PDF, sin JSON local)
    """

    def __init__(self) -> None:
        self.logger = _setup_logging()
        self.gestion = GestionAsesores()
        self.db = get_database()
        self.memory_manager = MemoryManager()
        self._orchestrator: Optional[CentauroOrchestrator] = None

    @property
    def orchestrator(self) -> CentauroOrchestrator:
        """Instancia lazy del orquestador (pesado, solo se crea si hay archivos)."""
        if self._orchestrator is None:
            self._orchestrator = CentauroOrchestrator()
        return self._orchestrator

    # ── Supabase Storage ─────────────────────────────────────────────────────
    def _subir_pdf_storage(self, pdf_path: Path, nombre_asesor: str, opp_id: str) -> Optional[str]:
        """
        Sube el PDF al bucket 'reportes' de Supabase Storage.
        Devuelve el nombre del archivo en Storage, o None si falla.
        El PDF es temporal: Power Automate lo borra tras enviar el email.
        """
        if not self.db.disponible:
            return None
        try:
            nombre_seguro = nombre_asesor.replace(" ", "_").replace("/", "-")
            storage_filename = f"{opp_id}_{nombre_seguro}.pdf"
            with open(pdf_path, "rb") as f:
                self.db._client.storage.from_("Reportes_PDF").upload(
                    path=storage_filename,
                    file=f,
                    file_options={"content-type": "application/pdf", "upsert": "true"},
                )
            return storage_filename
        except Exception as e:
            self.logger.error(f"   Error subiendo PDF a Supabase Storage: {e}")
            return None

    # ── Deduplicación ────────────────────────────────────────────────────────
    def _es_ya_procesado(self, opportunity_id: str) -> bool:
        """Devuelve True si ya existe una evaluación con este opportunity_id."""
        if not self.db.disponible:
            return False
        existing = self.db.buscar_evaluacion_por_oportunidad(opportunity_id)
        return existing is not None

    # ── Carga de texto ───────────────────────────────────────────────────────
    def _cargar_texto(self, archivo: Path) -> Optional[str]:
        ext = archivo.suffix.lower()

        if ext == ".mp4":
            return self._cargar_desde_video(archivo)
        if ext == ".mp3":
            return self._cargar_desde_audio(archivo)
        if ext == ".docx":
            texto = _leer_docx(archivo)
            if not texto:
                self.logger.error(f"   No se pudo extraer texto del DOCX: {archivo.name}")
            return texto

        # .txt / .vtt → leer crudo (el DiarizationAgent necesita el VTT sin limpiar)
        try:
            return archivo.read_text(encoding="utf-8")
        except Exception as e:
            self.logger.error(f"   Error leyendo {archivo.name}: {e}")
            return None

    def _cargar_desde_video(self, video_path: Path) -> Optional[str]:
        """MP4 → extrae MP3 en inputs/audios/ → transcribe → devuelve texto."""
        from centauro.tools.extract_audio import (
            extraer_audio,
            _ffmpeg_disponible,
            AUDIOS_DIR,
        )

        if not _ffmpeg_disponible():
            self.logger.error("   ffmpeg no disponible, no se puede procesar vídeo")
            return None

        AUDIOS_DIR.mkdir(parents=True, exist_ok=True)
        ok = extraer_audio(video_path)  # guarda en inputs/audios/
        if not ok:
            self.logger.error(f"   ffmpeg falló extrayendo audio de {video_path.name}")
            return None

        mp3_path = AUDIOS_DIR / f"{video_path.stem}.mp3"
        if not mp3_path.exists():
            self.logger.error(f"   MP3 no encontrado tras extracción: {mp3_path.name}")
            return None

        return self._cargar_desde_audio(mp3_path)

    def _cargar_desde_audio(self, mp3_path: Path) -> Optional[str]:
        """MP3 → transcribe con Groq Whisper → devuelve texto."""
        from centauro.tools.whisper_transcribe import (
            transcribir_audio,
            TRANSCRIPTS_DIR,
        )

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            self.logger.error("   GROQ_API_KEY no configurada en .env")
            return None

        # Si ya existe la transcripción Whisper, reutilizarla
        nombre_limpio = mp3_path.stem.replace("_", " ")
        whisper_txt = TRANSCRIPTS_DIR / f"{nombre_limpio}_whisper.txt"
        if whisper_txt.exists():
            self.logger.info(f"   Reutilizando transcripción existente: {whisper_txt.name}")
            return whisper_txt.read_text(encoding="utf-8")

        # Transcribir con Groq
        try:
            from groq import Groq

            client = Groq(api_key=api_key)
            transcribir_audio(client, mp3_path)  # guarda en TRANSCRIPTS_DIR
        except Exception as e:
            self.logger.error(f"   Error en transcripción Groq: {e}")
            return None

        if whisper_txt.exists():
            return whisper_txt.read_text(encoding="utf-8")

        self.logger.error(f"   Transcripción Whisper no generada: {whisper_txt.name}")
        return None

    # ── Procesamiento de un archivo ──────────────────────────────────────────
    def procesar_archivo(self, archivo: Path) -> bool:
        """
        Procesa un archivo de entrevista de extremo a extremo.
        Devuelve True si se procesó y guardó en Supabase correctamente.
        """
        SEP = "─" * 60
        self.logger.info(SEP)
        self.logger.info(f"ARCHIVO: {archivo.name}")
        self.logger.info(SEP)

        # 1. Opportunity ID
        opp_id = extraer_opportunity_id(archivo.name)
        if not opp_id:
            # Archivos del watcher de SharePoint no tienen opportunity_id en el nombre.
            # Generamos un ID temporal para no bloquear el procesamiento.
            import hashlib as _hl
            opp_id = "SP-" + _hl.md5(archivo.name.encode()).hexdigest()[:10]
            self.logger.warning(
                f"   Sin opportunity_id en filename → usando ID temporal: {opp_id}"
            )

        # 2. Deduplicación
        if self._es_ya_procesado(opp_id):
            self.logger.info(f"   Ya procesado en Supabase (opp_id: {opp_id}) → saltando")
            return False

        self.logger.info(f"   Opportunity ID: {opp_id}")

        # 3. Nombre del asesor desde el filename
        nombre_asesor = _extraer_nombre_de_filename(archivo.name, self.gestion, self.logger)

        # 4. Cargar texto
        self.logger.info("   Cargando transcripción...")
        texto = self._cargar_texto(archivo)
        if not texto or len(texto.strip()) < 100:
            self.logger.error("   Transcripción vacía o demasiado corta → saltando")
            return False

        # 5. Análisis multi-agente (idéntico al flujo Chainlit)
        self.logger.info("   Ejecutando análisis multi-agente...")
        inicio = time.time()
        try:
            reporte = self.orchestrator.analizar_entrevista_completa(
                nombre_archivo=archivo.stem,
                texto_crudo=texto,
                contexto_usuario=None,
                audio_features=None,
            )
        except Exception as e:
            self.logger.error(f"   Error en análisis: {e}")
            return False

        if not reporte:
            self.logger.error("   El orquestador no devolvió reporte")
            return False

        tiempo = time.time() - inicio
        self.logger.info(f"   Análisis completado en {tiempo / 60:.1f} min")

        # 6. Resolver nombre definitivo del asesor
        #    Prioridad: filename fuzzy match > orquestador > stem del archivo
        nombre_final = nombre_asesor or reporte.get("asesor") or archivo.stem
        cal_global = reporte.get("calificacion_global", "N/A")
        self.logger.info(f"   Asesor: {nombre_final}")
        self.logger.info(f"   Calificación global: {cal_global}")

        # 7. Generar PDF y subir a Supabase Storage (si la evaluación es válida)
        storage_path = None
        if _evaluacion_valida(reporte):
            from centauro.reports import generar_pdf
            pdf_filename = f"Reporte_{archivo.stem}_v3.pdf"
            pdf_dir = settings.OUTPUTS_DIR / "Reportes_PDF"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pdf_dir / pdf_filename
            try:
                datos_oportunidad = reporte.get("datos_oportunidad")
                generar_pdf(reporte, str(pdf_path), datos_oportunidad=datos_oportunidad)
                self.logger.info(f"   PDF generado: {pdf_filename}")

                storage_path = self._subir_pdf_storage(pdf_path, nombre_final, opp_id)
                if storage_path:
                    self.logger.info(f"   PDF subido a Storage: {storage_path}")
                    pdf_path.unlink(missing_ok=True)  # borrar local tras subir
                else:
                    self.logger.warning("   No se pudo subir PDF a Storage — evaluación guardada sin notificación")
            except Exception as e:
                self.logger.error(f"   Error generando/subiendo PDF: {e}")
        else:
            self.logger.warning(
                f"   Evaluación incompleta para '{nombre_final}' — no se genera PDF ni se envía email"
            )

        # 8. Guardar en Supabase
        try:
            stats = reporte.get("meta", {}).get("stats_optimizacion")
            self.memory_manager.registrar_evaluacion(
                nombre_asesor=nombre_final,
                resultado_evaluacion=reporte,
                transcripcion_path=str(archivo),
                opportunity_id=opp_id,
                archivo_origen=archivo.name,
                reporte_pdf_path=None,
                storage_path=storage_path,
                stats=stats,
            )
            self.logger.info("   Guardado en Supabase")
        except Exception as e:
            self.logger.error(f"   Error guardando en Supabase: {e}")
            return False

        return True

    # ── Ejecución principal ──────────────────────────────────────────────────
    def ejecutar(self) -> None:
        """Busca y procesa todos los archivos nuevos en inputs/batch/."""
        SEP = "=" * 70
        self.logger.info(SEP)
        self.logger.info(
            f"CENTAURO BATCH PROCESSOR — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.logger.info(SEP)

        # Asegurar que la carpeta de entrada existe
        BATCH_INPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Carpeta de entrada: {BATCH_INPUT_DIR}")

        # Verificar / actualizar índices RAG (solo reconstruye si hay cambios)
        self.logger.info("Verificando base de conocimiento RAG...")
        indexar_si_necesario()

        # Listar archivos soportados (solo nivel raíz, no subcarpetas)
        archivos = sorted(
            f
            for f in BATCH_INPUT_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        if not archivos:
            self.logger.info("No hay archivos en inputs/batch/ — nada que procesar.")
            return

        self.logger.info(f"Archivos encontrados: {len(archivos)}")

        procesados = saltados = errores = 0

        for archivo in archivos:
            try:
                ok = self.procesar_archivo(archivo)
                if ok:
                    procesados += 1
                else:
                    saltados += 1
            except Exception as e:
                self.logger.error(f"Error inesperado con {archivo.name}: {e}")
                errores += 1

        self.logger.info(SEP)
        self.logger.info(
            f"RESUMEN: {procesados} procesados | "
            f"{saltados} saltados | "
            f"{errores} errores"
        )
        self.logger.info(SEP)


# ── Punto de entrada ─────────────────────────────────────────────────────────
def main() -> None:
    processor = BatchProcessor()
    processor.ejecutar()


if __name__ == "__main__":
    main()
