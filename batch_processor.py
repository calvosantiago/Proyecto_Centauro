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
ASSEMBLYAI_COST_PER_SECOND = 0.0002  # $0.012/min (transcripción + diarización)


# ── AssemblyAI helpers (misma lógica que app.py) ─────────────────────────────
def _get_transcripcion_cache_path(audio_path: Path) -> Path:
    cache_dir = settings.OUTPUTS_DIR / "transcripciones_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{audio_path.stem}.txt"


def _registrar_gasto_assemblyai(referencia: str, duracion_seg: float) -> None:
    import datetime
    try:
        from centauro.llm_client import _append_cost_row
        coste = duracion_seg * ASSEMBLYAI_COST_PER_SECOND
        now = datetime.datetime.now()
        row = {
            "Timestamp": now.isoformat(timespec="seconds"),
            "Fecha": now.strftime("%Y-%m-%d"),
            "Hora": now.strftime("%H:%M:%S"),
            "Usuario": "batch",
            "Archivo/Referencia": referencia,
            "Operacion": "transcripcion_assemblyai",
            "Endpoint": "assemblyai/v2/transcript",
            "Modelo": "assemblyai-best",
            "Prompt Tokens": "", "Prompt Tokens Cacheados": "",
            "Prompt Tokens No Cacheados": "", "Completion Tokens": "",
            "Embedding Tokens": "", "Total Tokens": "",
            "Coste Input (USD)": "", "Coste Input Cacheado (USD)": "",
            "Coste Output (USD)": "", "Coste Embedding (USD)": "",
            "Coste Total (USD)": f"{duracion_seg * ASSEMBLYAI_COST_PER_SECOND:.6f}",
            "Request ID": "",
        }
        _append_cost_row(row)
    except Exception:
        pass


def _transcribir_con_assemblyai(audio_path: Path, api_key: str, referencia: str = "") -> str:
    cache_stem = Path(referencia).stem if referencia else audio_path.stem
    cache_path = _get_transcripcion_cache_path(Path(cache_stem))
    if cache_path.exists():
        print(f"   💾 Transcripción en caché: {cache_path.name}")
        return cache_path.read_text(encoding="utf-8")

    import assemblyai as aai
    aai.settings.api_key = api_key
    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_code="es",
        speech_models=["universal-3-pro"],
    )
    print("   📡 Enviando a AssemblyAI (transcripción + diarización)...")
    transcript = aai.Transcriber().transcribe(str(audio_path), config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")

    if not transcript.utterances:
        print("   ⚠️ AssemblyAI no devolvió utterances, usando texto plano")
        return transcript.text or ""

    duracion_seg = transcript.utterances[-1].end / 1000
    _registrar_gasto_assemblyai(referencia or audio_path.name, duracion_seg)

    lineas = [f"[Speaker_{utt.speaker}]: {utt.text}" for utt in transcript.utterances]
    resultado = "\n\n".join(lineas)
    print(f"   ✅ AssemblyAI: {len(transcript.utterances)} utterances, {duracion_seg/60:.1f} min")

    try:
        cache_path.write_text(resultado, encoding="utf-8")
    except Exception:
        pass

    return resultado


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
      4. Cargar texto: AssemblyAI para MP4/MP3, lectura directa para txt/vtt/docx
      5. Ejecutar CentauroOrchestrator (mismos agentes que Chainlit)
      6. Generar PDF y subir a Supabase Storage (si evaluación válida)
      7. Guardar en Supabase vía MemoryManager.registrar_evaluacion()
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
    def _cargar_texto(self, archivo: Path) -> tuple[Optional[str], Optional[dict]]:
        """Devuelve (texto, audio_features). audio_features es None para formatos no-audio."""
        ext = archivo.suffix.lower()

        if ext in (".mp4", ".mp3"):
            return self._cargar_desde_multimedia(archivo)
        if ext == ".docx":
            texto = _leer_docx(archivo)
            if not texto:
                self.logger.error(f"   No se pudo extraer texto del DOCX: {archivo.name}")
            return texto, None

        # .txt / .vtt → leer crudo (el DiarizationAgent necesita el VTT sin limpiar)
        try:
            return archivo.read_text(encoding="utf-8"), None
        except Exception as e:
            self.logger.error(f"   Error leyendo {archivo.name}: {e}")
            return None, None

    def _cargar_desde_multimedia(self, archivo: Path) -> tuple[Optional[str], Optional[dict]]:
        """MP4/MP3 → AssemblyAI (transcripción + diarización nativa) + métricas acústicas."""
        import subprocess
        import tempfile
        from centauro.tools.extract_audio import FFMPEG_PATH

        api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not api_key:
            self.logger.error("   ASSEMBLYAI_API_KEY no configurada en .env")
            return None, None

        audio_path = archivo

        # MP4 → extraer MP3 con ffmpeg (igual que app.py)
        if archivo.suffix.lower() == ".mp4":
            if not FFMPEG_PATH.exists():
                self.logger.error(f"   ffmpeg no encontrado en {FFMPEG_PATH}")
                return None, None
            mp3_tmp = Path(tempfile.gettempdir()) / f"centauro_{archivo.stem}.mp3"
            resultado = subprocess.run(
                [str(FFMPEG_PATH), "-i", str(archivo), "-vn", "-c:a", "libmp3lame",
                 "-b:a", "32k", "-ac", "1", "-ar", "16000", "-y", str(mp3_tmp)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
            )
            if resultado.returncode != 0:
                self.logger.error(f"   ffmpeg falló: {resultado.stderr[-200:]}")
                return None, None
            audio_path = mp3_tmp

        # Métricas acústicas (opcional — no bloquea si falla)
        audio_features = None
        try:
            from centauro.tools.audio_features import extraer_metricas_audio
            audio_features = extraer_metricas_audio(audio_path)
        except Exception:
            pass

        # Transcripción + diarización con AssemblyAI
        try:
            texto = _transcribir_con_assemblyai(audio_path, api_key, archivo.name)
            return texto, audio_features
        except Exception as e:
            self.logger.error(f"   Error en AssemblyAI: {e}")
            return None, None

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

        # 4. Cargar texto + audio_features
        self.logger.info("   Cargando transcripción...")
        texto, audio_features = self._cargar_texto(archivo)
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
                audio_features=audio_features,
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
        #    Prioridad: filename fuzzy match > propietario en oportunidades > orquestador > stem
        if not nombre_asesor and self.db.disponible:
            opp = self.db.obtener_oportunidad(opp_id)
            propietario = opp.get("propietario") if opp else None
            if propietario:
                match = self.gestion.buscar_asesor_similar(propietario)
                if match:
                    nombre_asesor = match[0]
                    self.logger.info(f"   Asesor resuelto desde oportunidad: '{nombre_asesor}' (propietario: '{propietario}')")
                else:
                    self.logger.warning(f"   Propietario '{propietario}' no reconocido en Supabase")

        nombre_final = nombre_asesor or reporte.get("asesor") or archivo.stem
        cal_global = reporte.get("calificacion_global", "N/A")
        self.logger.info(f"   Asesor: {nombre_final}")
        self.logger.info(f"   Calificación global: {cal_global}")

        # Inyectar nombre resuelto en el reporte para que el PDF lo muestre correctamente
        reporte["asesor"] = nombre_final

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
                realizado_por="batch",
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
