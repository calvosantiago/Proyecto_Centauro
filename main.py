"""
MAIN.PY - Sistema Multi-Agente v3.0 - Pipeline Completo Automático

Pipeline completo en un solo comando:
  1. Vídeos nuevos en inputs/videollamadas/ → extrae audio con ffmpeg
  2. MP3 sin transcripción en inputs/audios/ → transcribe con Groq Whisper
  3. Transcripciones en inputs/transcripts/ → valida calidad (Plan B automático)
  4. Analiza con sistema multi-agente
  5. Genera PDF + JSON en outputs/
"""
import os
import re
import time
import json
from pathlib import Path

try:
    from docx import Document
except ImportError:
    Document = None

from centauro.config import settings
from centauro.rag import indexar_si_necesario
from centauro.reports import generar_pdf

# ===== CAMBIO PRINCIPAL: Nuevo orquestador =====
from centauro.core import CentauroOrchestrator
# ================================================

from centauro.core.memoria import MemoryManager
from centauro.utils.validaciones import extraer_opportunity_id
memory_manager = MemoryManager()

# ---------------------------------------------------------------------------
# PIPELINE AUTOMÁTICO: Vídeo → Audio → Transcripción
# ---------------------------------------------------------------------------

def _paso_extraer_audios_de_videos():
    """
    Paso 1: Detecta vídeos en inputs/videollamadas/ que no tienen MP3 en inputs/audios/
    y los convierte automáticamente con ffmpeg.
    """
    from centauro.tools.extract_audio import extraer_audio, _ffmpeg_disponible, VIDEO_EXTENSIONS

    videos_dir = settings.INPUTS_DIR / "videollamadas"
    audios_dir = settings.INPUTS_DIR / "audios"

    if not videos_dir.exists():
        return

    # Buscar vídeos sin MP3 correspondiente
    videos_pendientes = []
    for ext in VIDEO_EXTENSIONS:
        for video in videos_dir.glob(f"*{ext}"):
            mp3_esperado = audios_dir / f"{video.stem}.mp3"
            if not mp3_esperado.exists():
                videos_pendientes.append(video)

    if not videos_pendientes:
        print("   ✓ No hay vídeos nuevos que procesar")
        return

    print(f"   🎬 {len(videos_pendientes)} vídeo(s) nuevo(s) detectado(s)")

    if not _ffmpeg_disponible():
        print("   ❌ ffmpeg no disponible, saltando extracción de audio")
        return

    audios_dir.mkdir(parents=True, exist_ok=True)
    for video in sorted(videos_pendientes):
        extraer_audio(video)


def _paso_transcribir_audios():
    """
    Paso 2: Para cada MP3 en inputs/audios/ decide si necesita transcripción Groq:

    - Si ya existe _whisper.txt          → saltar (ya procesado)
    - Si existe transcripción y es BUENA → saltar (Teams/Word suficiente)
    - Si existe transcripción y es MALA  → transcribir con Groq (Plan B real)
    - Si no existe ninguna transcripción → transcribir con Groq (audio nuevo)
    """
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")

    from centauro.tools.transcript_validator import validar_transcripcion

    audios_dir = settings.INPUTS_DIR / "audios"
    transcripts_dir = settings.INPUTS_DIR / "transcripts"

    if not audios_dir.exists():
        return

    mp3_pendientes = []  # (path, motivo)

    for mp3 in sorted(audios_dir.glob("*.mp3")):
        nombre_limpio = mp3.stem.replace("_", " ")

        # 1. ¿Ya existe _whisper.txt? → saltar
        whisper_txt = transcripts_dir / f"{nombre_limpio}_whisper.txt"
        if whisper_txt.exists():
            print(f"   ⏭️  {mp3.name}: ya tiene _whisper.txt, saltando")
            continue

        # 2. Buscar transcripción existente (Teams/Word/VTT)
        transcript_existente = None
        for ext in [".txt", ".vtt", ".docx"]:
            candidato = transcripts_dir / f"{nombre_limpio}{ext}"
            if candidato.exists():
                transcript_existente = candidato
                break
            # También buscar con guiones bajos
            candidato_guion = transcripts_dir / f"{mp3.stem}{ext}"
            if candidato_guion.exists():
                transcript_existente = candidato_guion
                break

        # 3. Sin transcripción → audio nuevo, transcribir
        if not transcript_existente:
            print(f"   🆕 {mp3.name}: sin transcripción, se transcribirá")
            mp3_pendientes.append((mp3, "sin transcripción previa"))
            continue

        # 4. Transcripción existente → validar calidad
        try:
            if transcript_existente.suffix == ".docx":
                texto = leer_word(transcript_existente) or ""
            else:
                texto = transcript_existente.read_text(encoding="utf-8")
        except Exception:
            texto = ""

        resultado = validar_transcripcion(texto, nombre_archivo=transcript_existente.name)

        if resultado.es_valida:
            print(f"   ✅ {mp3.name}: transcripción existente válida (score: {resultado.score:.2f}), saltando Groq")
        else:
            problemas_str = " | ".join(resultado.problemas)
            print(f"   ❌ {mp3.name}: transcripción de baja calidad (score: {resultado.score:.2f}) → {problemas_str}")
            mp3_pendientes.append((mp3, "transcripción de baja calidad"))

    if not mp3_pendientes:
        print("   ✓ No hay audios que requieran transcripción con Groq Whisper")
        return

    print(f"\n   🎙️  {len(mp3_pendientes)} audio(s) pendiente(s) de transcripción:")
    for mp3, motivo in mp3_pendientes:
        print(f"      • {mp3.name} ({motivo})")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("   ❌ GROQ_API_KEY no encontrada, saltando transcripción automática")
        print("   💡 Añade GROQ_API_KEY a tu .env para transcripción automática")
        return

    try:
        from groq import Groq
        from centauro.tools.whisper_transcribe import transcribir_audio
        from centauro.tools.audio_features import extraer_metricas_audio
        client = Groq(api_key=api_key)
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        for mp3, _ in mp3_pendientes:
            transcribir_audio(client, mp3)
            # Extraer y guardar métricas de audio como sidecar JSON
            try:
                metricas = extraer_metricas_audio(mp3)
                nombre_limpio = mp3.stem.replace("_", " ")
                sidecar = transcripts_dir / f"{nombre_limpio}_audio_features.json"
                import json as _json
                sidecar.write_text(_json.dumps(metricas, ensure_ascii=False), encoding="utf-8")
                if metricas.get("disponible"):
                    print(f"  📊 Métricas de audio guardadas: {sidecar.name}")
                else:
                    print(f"  ⚠️  Métricas de audio no disponibles: {metricas.get('motivo', '')}")
            except Exception as e_af:
                print(f"  ⚠️  No se pudieron extraer métricas de audio: {e_af}")
    except Exception as e:
        print(f"   ❌ Error en transcripción automática: {e}")


# --- FUNCIONES DE LECTURA (SIN CAMBIOS) ---

def limpiar_formato_vtt(texto_crudo):
    """Elimina metadatos técnicos de archivos VTT"""
    texto = texto_crudo.replace("WEBVTT", "")
    texto = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}', '', texto)
    texto = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(-\d+)?', '', texto)
    texto = re.sub(r'<[^>]+>', '', texto)
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    texto_limpio = " ".join(lineas)
    return texto_limpio

def leer_word(ruta_archivo):
    """Extrae texto de archivos Word (Teams)"""
    if not Document:
        print("❌ ERROR: Falta librería 'python-docx'.")
        return ""
    
    try:
        doc = Document(ruta_archivo)
        transcript = []
        current_speaker = None
        current_text_buffer = []
        patron_teams = re.compile(r"^(.*?)\s+(\d{1,2}:\d{2}(?::\d{2})?)$")
        lines_found = 0 

        for para in doc.paragraphs:
            bloque_texto = para.text.replace('\r', '\n')
            sub_lineas = bloque_texto.split('\n')

            for linea in sub_lineas:
                texto = linea.strip()
                if not texto:
                    continue 
                texto_norm = re.sub(r'\s+', ' ', texto)
                match = patron_teams.match(texto_norm)

                if match:
                    lines_found += 1
                    if lines_found <= 3:
                        print(f"   🎯 Match: {match.group(1)}")

                    if current_speaker and current_text_buffer:
                        contenido = " ".join(current_text_buffer)
                        transcript.append(f"[{current_speaker}]: {contenido}")
                    
                    current_speaker = match.group(1).strip() 
                    current_text_buffer = [] 
                else:
                    if current_speaker:
                        current_text_buffer.append(texto)

        if current_speaker and current_text_buffer:
            contenido = " ".join(current_text_buffer)
            transcript.append(f"[{current_speaker}]: {contenido}")

        full_text = "\n\n".join(transcript)
        
        if not full_text:
            print("   ❌ FALLO: No se extrajo texto.")
        else:
            print(f"   ✅ ÉXITO: {lines_found} intervenciones detectadas.")

        return full_text

    except Exception as e:
        print(f"❌ Error leyendo Word {ruta_archivo}: {e}")
        return ""

def cargar_transcripcion(ruta_archivo):
    """Detector inteligente de formato (Word, VTT, TXT)"""
    # VALIDACIÓN CRÍTICA: Verificar longitud de nombre de archivo
    try:
        from centauro.utils import validar_archivo_para_procesamiento, generar_mensaje_error_usuario

        validacion = validar_archivo_para_procesamiento(ruta_archivo)

        if not validacion:
            # Generar mensaje de error amigable
            mensaje_error = generar_mensaje_error_usuario(validacion, "análisis de conversación")
            print("\n" + "="*60)
            print(mensaje_error)
            print("="*60 + "\n")
            return None
    except ImportError:
        # Si no existe el módulo de validaciones, continuar sin validar
        pass

    ext = ruta_archivo.suffix.lower()

    if ext == ".docx":
        print(f"   📄 Leyendo documento Word...")
        return leer_word(ruta_archivo)

    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            texto = f.read()

        # NOTA: Ya NO limpiamos VTT aquí. El agente de diarización
        # necesita el texto crudo para detectar UUIDs de speakers.
        # La limpieza se hace DESPUÉS de la diarización si es necesario.
        if ext == ".vtt" or "WEBVTT" in texto[:50]:
            print(f"   📄 Archivo VTT detectado (se procesará en diarización)")

        return texto

    except Exception as e:
        print(f"❌ Error leyendo archivo {ruta_archivo}: {e}")
        return None

# --- MAIN (CON NUEVO ORQUESTADOR) ---

def main():
    print("🦄 INICIANDO PROYECTO CENTAURO v3.0 (Pipeline Completo Automático)...")
    print("="*70)

    # 1. Asegurar directorios
    os.makedirs(settings.INPUTS_DIR / "docs", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "audios", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "videollamadas", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "transcripts", exist_ok=True)
    os.makedirs(settings.OUTPUTS_DIR, exist_ok=True)

    # 2. Indexar Manuales (RAG) — solo si hay cambios
    print("\n📚 Paso 1: Verificando base de conocimiento...")
    indexar_si_necesario()

    # 3. Vídeos → Audio (ffmpeg)
    print("\n🎬 Paso 2: Extracción de audio de vídeos nuevos...")
    _paso_extraer_audios_de_videos()

    # 4. Audio → Transcripción (Groq Whisper)
    print("\n🎙️  Paso 3: Transcripción de audios nuevos...")
    _paso_transcribir_audios()

    # 5. Buscar todas las transcripciones disponibles
    carpeta = settings.INPUTS_DIR / "transcripts"
    archivos_transcripcion = (
        list(carpeta.glob("*.txt")) +
        list(carpeta.glob("*.vtt")) +
        list(carpeta.glob("*.docx"))
    )

    if not archivos_transcripcion:
        print("\n⚠️ No hay transcripciones disponibles para analizar.")
        print("   Puedes añadir:")
        print("   • Vídeos en:         inputs/videollamadas/")
        print("   • Audios en:         inputs/audios/")
        print("   • Transcripciones en: inputs/transcripts/")
        return

    print(f"\n🚀 Paso 4: Analizando {len(archivos_transcripcion)} entrevista(s)...")
    print("="*70)

    # ===== CREAR ORQUESTADOR =====
    orchestrator = CentauroOrchestrator()
    # ==============================

    # 4. Bucle de Procesamiento
    for idx, archivo in enumerate(archivos_transcripcion, 1):
        print(f"\n{'='*70}")
        print(f"📂 [{idx}/{len(archivos_transcripcion)}] {archivo.name}")
        print(f"{'='*70}")
        
        # Cargar transcripción
        texto = cargar_transcripcion(archivo)
        if not texto:
            print("   ⚠️ Archivo vacío o no legible, saltando...")
            continue

        # ===== VALIDACIÓN DE CALIDAD + PLAN B AUTOMÁTICO =====
        try:
            from centauro.tools.transcript_validator import validar_transcripcion, activar_plan_b_whisper

            resultado_val = validar_transcripcion(texto, nombre_archivo=archivo.name)

            if resultado_val.es_valida:
                if resultado_val.advertencias:
                    print(f"   ✅ Transcripción válida (score: {resultado_val.score:.2f})")
                    for adv in resultado_val.advertencias:
                        print(f"      🟡 {adv}")
                else:
                    print(f"   ✅ Transcripción válida (score: {resultado_val.score:.2f})")
            else:
                print(f"   ❌ Transcripción de baja calidad (score: {resultado_val.score:.2f})")
                for prob in resultado_val.problemas:
                    print(f"      🔴 {prob}")
                print(f"   🔄 Activando Plan B: Groq Whisper...")
                texto_whisper = activar_plan_b_whisper(archivo.stem)
                if texto_whisper:
                    texto = texto_whisper
                    print(f"   ✅ Plan B completado, usando transcripción de Whisper")
                else:
                    print(f"   ⚠️ Plan B falló, continuando con transcripción original")

        except Exception as e:
            print(f"   ⚠️ Validador no disponible, continuando sin validar: {e}")
        # ======================================================

        # Iniciar cronómetro
        inicio_reloj = time.time()
        print("   ⏳ Analizando con sistema multi-agente...")

        # ===== CARGAR CONTEXTO DEL USUARIO (si existe) =====
        # Busca un archivo con el mismo nombre + extensión .ctx
        # Ejemplo: "entrevista_01.txt" → busca "entrevista_01.ctx"
        contexto_usuario = None
        archivo_ctx = archivo.with_suffix('.ctx')
        if archivo_ctx.exists():
            try:
                with open(archivo_ctx, 'r', encoding='utf-8') as f_ctx:
                    contexto_usuario = f_ctx.read().strip()
                if contexto_usuario:
                    print(f"   📝 Contexto del usuario cargado desde: {archivo_ctx.name}")
            except Exception as e:
                print(f"   ⚠️ Error leyendo contexto {archivo_ctx.name}: {e}")

        # ===== CARGAR MÉTRICAS DE AUDIO (si existen) =====
        audio_features = None
        sidecar_af = archivo.with_name(archivo.stem + "_audio_features.json")
        if sidecar_af.exists():
            try:
                with open(sidecar_af, "r", encoding="utf-8") as f_af:
                    audio_features = json.load(f_af)
                if audio_features.get("disponible"):
                    print(f"   📊 Métricas de audio cargadas ({audio_features.get('duracion_seg', '?')} seg)")
            except Exception as e_af:
                print(f"   ⚠️ No se pudieron leer métricas de audio: {e_af}")

        # ===== EJECUTAR ANÁLISIS CON ORQUESTADOR =====
        try:
            reporte = orchestrator.analizar_entrevista_completa(
                nombre_archivo=archivo.stem,
                texto_crudo=texto,
                contexto_usuario=contexto_usuario,
                audio_features=audio_features
            )
        except Exception as e:
            print(f"\n   ❌ ERROR en análisis: {e}")
            print(f"   💡 Tip: Revisa que tu API key de OpenAI sea válida")
            continue
        # ==============================================
        
        # Cronómetro
        fin_reloj = time.time()
        tiempo_total = fin_reloj - inicio_reloj
        minutos = int(tiempo_total // 60)
        segundos = int(tiempo_total % 60)

        print(f"\n   ⏱️ Tiempo de análisis: {minutos} min {segundos} seg")
        
        # Generar outputs
        if reporte:
            # JSON
            json_path = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{archivo.stem}_v2.json"
            json_path.parent.mkdir(exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(reporte, f, indent=2, ensure_ascii=False)
            print(f"   💾 JSON guardado: {json_path.name}")
            
            # PDF
            print("   🎨 Generando PDF...")
            nombre_pdf = f"Reporte_{archivo.stem}_v2.pdf"
            generar_pdf(reporte, nombre_pdf)

            # ===== GUARDAR PERFIL DEL ASESOR =====
            try:
                nombre_asesor = reporte.get("asesor") or archivo.stem
                opp_id = extraer_opportunity_id(archivo.name)
                if opp_id:
                    print(f"   🔗 Opportunity ID detectado: {opp_id}")

                pdf_path = settings.OUTPUTS_DIR / "Reportes_PDF" / nombre_pdf

                perfil = memory_manager.registrar_evaluacion(
                    nombre_asesor=nombre_asesor,
                    resultado_evaluacion=reporte,
                    transcripcion_path=str(archivo),
                    opportunity_id=opp_id,
                    archivo_origen=archivo.name,
                    reporte_json_path=str(json_path),
                    reporte_pdf_path=str(pdf_path),
                )
                print(f"   🧠 Perfil actualizado: {nombre_asesor} "
                      f"({perfil.total_evaluaciones} evaluación(es) registradas)")
            except Exception as e:
                print(f"   ⚠️ No se pudo guardar perfil del asesor: {e}")
            # =====================================

            # Estadísticas de optimización
            if "meta" in reporte and "stats_optimizacion" in reporte["meta"]:
                stats = reporte["meta"]["stats_optimizacion"]
                print(f"\n   📊 Estadísticas:")
                print(f"      • Llamadas API: {stats.get('llamadas_api', 'N/A')}")
                print(f"      • Cache hits: {stats.get('cache_hits', 'N/A')}")
                print(f"      • Tokens ahorrados: ~{stats.get('tokens_ahorrados', 0):,}")
        else:
            print("   ❌ El análisis falló, no se generó reporte.")

    print(f"\n{'='*70}")
    print("✅ PROCESO COMPLETADO")
    print(f"{'='*70}")
    print(f"📁 Revisa tus reportes en: {settings.OUTPUTS_DIR}")
    print("   • PDFs en: outputs/Reportes_PDF/")
    print("   • JSONs en: outputs/Reportes_JSON/")
    print()

if __name__ == "__main__":
    main()