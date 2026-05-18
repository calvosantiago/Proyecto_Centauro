"""
CENTAURO v4.0 - Interfaz Chainlit
Sistema de evaluación automatizada de llamadas comerciales con chat interactivo
NUEVO en v4.0:
- Chat interactivo para consultas al RAG
- Sistema de memoria y perfiles de asesores
- Múltiples colecciones ChromaDB
Ejecutar con: chainlit run app.py -w
"""
import re
import chainlit as cl
import asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
from centauro.core import CentauroOrchestrator
from centauro.core.chat_handler import ChatHandler
from centauro.core.memoria import memory_manager
from centauro.rag import indexar_si_necesario
from centauro.privacy import redact_pii
from centauro.reports import generar_pdf
from centauro.config import settings
from centauro.utils.validaciones import extraer_opportunity_id
from centauro.auth import autenticar
from centauro.llm_client import set_usuario_activo
from centauro.core.queue_manager import ejecutar_con_cola, adquirir_slot
import json
# Importar funciones de lectura desde main.py (raíz del proyecto)
from main import leer_word, limpiar_formato_vtt


# ---------------------------------------------------------------------------
# EXTRACCIÓN DE NOMBRE DE ASESOR CON LLM
# ---------------------------------------------------------------------------

def _extraer_nombre_y_limpiar_contexto(texto: str) -> dict:
    """
    Usa GPT-4o-mini para extraer el nombre del asesor del mensaje del usuario
    y devuelve también el contexto limpio (sin la mención del asesor).

    Mucho más robusto que regex: entiende cualquier formato sin mantenimiento.
    Ejemplos que maneja:
      "Asesor: Ivan Canale"         → nombre='Ivan Canale'
      "asesora es Ivonne Rose"      → nombre='Ivonne Rose'
      "esto lo lleva Pedro García"  → nombre='Pedro García'
      "llamada de Juan, MBA online" → nombre='Juan' (si parece nombre de asesor)
      "lead de México, programa X"  → nombre=null

    Returns:
        {"nombre": "Nombre Apellido" | None, "contexto_limpio": "texto sin mención del asesor"}
    """
    from centauro.llm_client import consultar_gpt

    prompt_sistema = (
        "Analiza el mensaje de un jefe de equipo que está subiendo una entrevista de ventas.\n"
        "Tu única tarea:\n"
        "1. Detecta si menciona el nombre del asesor o asesora (en cualquier formato).\n"
        "2. Devuelve el mensaje limpiado, eliminando SOLO la parte que identifica al asesor.\n\n"
        "Ejemplos de menciones a detectar:\n"
        "  'Asesor: Ivan Canale'              → nombre='Ivan Canale'\n"
        "  'Asesora: Ivonne Rose'             → nombre='Ivonne Rose'\n"
        "  'asesora es Ivonne Rose'           → nombre='Ivonne Rose'\n"
        "  'esto lo lleva Pedro García'       → nombre='Pedro García'\n"
        "  'la llamada es de Juan Pérez'      → nombre='Juan Pérez'\n"
        "  'se llama María de la Torre'       → nombre='María de la Torre'\n"
        "  'MBA online, lead de México'       → nombre=null\n"
        "  'lead interesado en Marketing'     → nombre=null\n\n"
        "Reglas:\n"
        "- El nombre es de una persona real (nombre + apellido mínimo).\n"
        "- NO incluyas títulos, cargos ni prefijos en el nombre.\n"
        "- Si no hay nombre de asesor, nombre=null.\n"
        "- contexto_limpio: el mensaje original sin la frase que menciona al asesor.\n\n"
        "Devuelve SOLO JSON sin texto adicional:\n"
        '{"nombre": "Nombre Apellido" | null, "contexto_limpio": "mensaje limpio"}'
    )

    try:
        resultado = consultar_gpt(
            prompt_sistema,
            texto,
            referencia_log="extraccion_nombre_mensaje",
            force_json=True,
            max_tokens=150,
        )
        data = json.loads(resultado)
        nombre = data.get("nombre") or None
        # Normalizar: Title Case y quitar espacios extra
        if nombre:
            nombre = " ".join(nombre.strip().split()).title()
        return {
            "nombre": nombre,
            "contexto_limpio": (data.get("contexto_limpio") or "").strip(),
        }
    except Exception:
        return {"nombre": None, "contexto_limpio": texto}


# ---------------------------------------------------------------------------
# AUTENTICACIÓN — Chainlit invoca este callback en cada intento de login
# ---------------------------------------------------------------------------

def _generar_msg_stats_semana(
    nombre_asesor: str,
    stats_semana: dict,
    bloques_evaluacion_actual: list,
) -> str:
    """
    Genera el mensaje de estadísticas semanales con síntesis LLM del Top 3 a mejorar.
    El Top 3 se basa en los razonamientos de los peores bloques de la semana.
    """
    from centauro.llm_client import consultar_gpt

    total = stats_semana["total_entrevistas"]
    bloques_debiles = stats_semana["bloques_debiles"]
    evaluaciones = stats_semana["evaluaciones"]

    EMOJI = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}

    lineas = [
        f"## 📊 Tendencia semanal — {nombre_asesor}",
        f"🗓️ **Entrevistas evaluadas esta semana:** {total}",
        "",
    ]

    # Apartados a revisar: bloques con más del 40% de evaluaciones no BUENO
    bloques_a_revisar = [(b, pct, c) for b, pct, c in bloques_debiles if pct > 0.4]
    if bloques_a_revisar:
        lineas.append("### ⚠️ Apartados a revisar")
        for bloque, _pct, conteo in bloques_a_revisar[:4]:
            total_b = sum(conteo.values())
            partes_cal = []
            for cal in ("MALO", "MEJORABLE", "BUENO"):
                if conteo.get(cal, 0) > 0:
                    partes_cal.append(f"{EMOJI[cal]} {cal}: {conteo[cal]}/{total_b}")
            lineas.append(f"- **{bloque}**: " + " | ".join(partes_cal))
        lineas.append("")

    # Top 3 bloques más débiles de la semana para síntesis
    top3_bloques = [b for b, _pct, _c in bloques_debiles[:3]]

    # Recopilar razonamientos de los bloques débiles desde las evaluaciones de la semana
    razonamientos_por_bloque: dict = {}
    for ev in evaluaciones:
        for b in ev.get("_bloques", []):
            nombre_b = b.get("bloque", "")
            cal = b.get("calificacion", "")
            razon = (b.get("razonamiento") or "").strip()
            if nombre_b in top3_bloques and cal in ("MALO", "MEJORABLE") and razon:
                razonamientos_por_bloque.setdefault(nombre_b, []).append(razon)

    # Fallback: usar razonamientos de la evaluación actual si no hay datos históricos suficientes
    for b in bloques_evaluacion_actual:
        nombre_b = b.get("bloque", "")
        cal = b.get("calificacion", "")
        razon = (b.get("razonamiento") or "").strip()
        if nombre_b in top3_bloques and cal in ("MALO", "MEJORABLE") and razon:
            razonamientos_por_bloque.setdefault(nombre_b, []).append(razon)

    if not top3_bloques:
        lineas.append("✅ _Sin áreas críticas esta semana. ¡Buen ritmo!_")
        return "\n".join(lineas)

    # Síntesis LLM con los razonamientos de los bloques más débiles
    contexto_razonamientos = ""
    for bloque in top3_bloques:
        razones = razonamientos_por_bloque.get(bloque, [])
        if razones:
            razones_txt = " | ".join(r[:350] for r in razones[-3:])
            contexto_razonamientos += f"**{bloque}**: {razones_txt}\n\n"

    if contexto_razonamientos:
        prompt_sistema = (
            "Eres un coach de ventas consultivas. Basándote en los razonamientos de evaluación "
            "de los apartados más débiles de un asesor durante la semana, genera exactamente "
            "3 recomendaciones de mejora concretas y accionables. "
            "Formato: lista numerada (1. 2. 3.), una frase clara por punto. "
            "Lenguaje directo, sin jerga técnica ni términos de evaluación interna. "
            "Cada punto debe indicar qué hacer, no solo qué está mal."
        )
        prompt_usuario = (
            f"Asesor: {nombre_asesor}\n"
            f"Entrevistas esta semana: {total}\n\n"
            f"Razonamientos de los bloques más débiles:\n{contexto_razonamientos}"
        )
        try:
            top3_texto = consultar_gpt(
                prompt_sistema,
                prompt_usuario,
                referencia_log="stats_semana_top3",
                force_json=False,
                max_tokens=300,
            )
            lineas.append("### 🎯 Top 3 a trabajar esta semana")
            lineas.append(top3_texto)
        except Exception:
            # Fallback sin síntesis: listar bloques directamente
            lineas.append("### 🎯 Bloques a priorizar esta semana")
            for i, bloque in enumerate(top3_bloques[:3], 1):
                lineas.append(f"{i}. **{bloque}**")

    return "\n".join(lineas)


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    """
    Verifica credenciales contra usuarios_auth en Supabase.
    Devuelve cl.User si son válidas, None si fallan.
    """
    usuario = autenticar(username, password)
    if usuario is None:
        return None

    return cl.User(
        identifier=username.strip().lower(),
        metadata={
            "nombre_completo": usuario.get("nombre_completo", username),
            "rol": usuario.get("rol", "asesor"),
            "provider": "credentials",
        }
    )

# ---------------------------------------------------------------------------
# Transcripción de audio/vídeo (AssemblyAI con diarización nativa, o Groq Whisper como fallback)
# ---------------------------------------------------------------------------

ASSEMBLYAI_COST_PER_SECOND = 0.0002  # $0.012/min = $0.72/hora (transcripción $0.0001 + diarización $0.0001)


def _registrar_gasto_assemblyai(referencia: str, duracion_seg: float) -> None:
    """Registra el coste de una transcripción AssemblyAI en control_gastos.csv."""
    import datetime
    from centauro.llm_client import _append_cost_row, get_usuario_activo
    coste = duracion_seg * ASSEMBLYAI_COST_PER_SECOND
    now = datetime.datetime.now()
    row = {
        "Timestamp": now.isoformat(timespec="seconds"),
        "Fecha": now.strftime("%Y-%m-%d"),
        "Hora": now.strftime("%H:%M:%S"),
        "Usuario": get_usuario_activo(),
        "Archivo/Referencia": referencia,
        "Operacion": "transcripcion_assemblyai",
        "Endpoint": "assemblyai/v2/transcript",
        "Modelo": "assemblyai-best",
        "Prompt Tokens": "",
        "Prompt Tokens Cacheados": "",
        "Prompt Tokens No Cacheados": "",
        "Completion Tokens": "",
        "Embedding Tokens": "",
        "Total Tokens": "",
        "Coste Input (USD)": "",
        "Coste Input Cacheado (USD)": "",
        "Coste Output (USD)": "",
        "Coste Embedding (USD)": "",
        "Coste Total (USD)": f"{coste:.6f}",
        "Request ID": "",
    }
    try:
        _append_cost_row(row)
        print(f"  💰 AssemblyAI: {duracion_seg/60:.1f} min × ${ASSEMBLYAI_COST_PER_SECOND*60:.4f}/min = ${coste:.4f}")
    except Exception as e:
        print(f"  ⚠️ No se pudo registrar gasto AssemblyAI: {e}")


def _get_transcripcion_cache_path(audio_path: Path) -> Path:
    """Devuelve la ruta del archivo de caché para una transcripción."""
    from centauro.config import settings
    cache_dir = settings.OUTPUTS_DIR / "transcripciones_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Clave: nombre del archivo (sin extensión) — suficiente para archivos con nombre único.
    # Si quisieramos comparar por contenido usaríamos hash MD5 del fichero.
    return cache_dir / f"{audio_path.stem}.txt"


def _transcribir_con_assemblyai(audio_path: Path, api_key: str, referencia: str = "") -> str:
    """
    Transcribe y diariza el audio usando AssemblyAI.
    Devuelve texto en formato [Speaker_A]: texto / [Speaker_B]: texto
    que el DiarizationAgent reconoce y mapea a ASESOR/LEAD por contenido.

    Antes de llamar a AssemblyAI comprueba un caché local por nombre de archivo.
    Si el archivo ya fue transcrito, devuelve el resultado guardado sin coste adicional.
    """
    # ── Caché de transcripciones ──────────────────────────────────────────────
    # Usar el nombre original del archivo (referencia) como clave de caché,
    # no el path temporal donde Chainlit guarda el upload (que cambia cada vez).
    cache_stem = Path(referencia).stem if referencia else audio_path.stem
    cache_path = _get_transcripcion_cache_path(Path(cache_stem))
    if cache_path.exists():
        print(f"   💾 Transcripción en caché encontrada — omitiendo llamada a AssemblyAI ({cache_path.name})")
        return cache_path.read_text(encoding="utf-8")

    import assemblyai as aai

    aai.settings.api_key = api_key
    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_code="es",
        speech_models=["universal-3-pro"],
    )
    transcriber = aai.Transcriber()
    print("   📡 Enviando a AssemblyAI (transcripción + diarización)...")
    transcript = transcriber.transcribe(str(audio_path), config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")

    if not transcript.utterances:
        print("   ⚠️ AssemblyAI no devolvió utterances, usando texto plano")
        return transcript.text or ""

    # Registrar coste (end de la última utterance está en milisegundos)
    duracion_seg = transcript.utterances[-1].end / 1000
    _registrar_gasto_assemblyai(referencia or audio_path.name, duracion_seg)

    # Formatear como [Speaker_A]: texto para que DiarizationAgent lo procese
    lineas = []
    for utt in transcript.utterances:
        lineas.append(f"[Speaker_{utt.speaker}]: {utt.text}")
    resultado = "\n\n".join(lineas)
    print(f"   ✅ AssemblyAI: {len(transcript.utterances)} utterances, {duracion_seg/60:.1f} min")

    # ── Guardar en caché para evitar re-transcribir si se vuelve a evaluar ──
    try:
        cache_path.write_text(resultado, encoding="utf-8")
        print(f"   💾 Transcripción guardada en caché: {cache_path.name}")
    except Exception as e:
        print(f"   ⚠️ No se pudo guardar caché de transcripción: {e}")

    return resultado


def _procesar_archivo_multimedia(file_path: Path, original_name: str = None) -> tuple:
    """
    Extrae texto de un archivo MP4 o MP3.
    Usa AssemblyAI (transcripción + diarización nativa) si ASSEMBLYAI_API_KEY está disponible.
    Si no, usa Groq Whisper + diarización por timestamps como fallback.
    Función síncrona pensada para usar con cl.make_async().

    Returns:
        (texto: str, audio_features: dict)
    """
    import os
    import subprocess
    import tempfile

    # Determinar extensión usando el nombre original si está disponible
    suffix = Path(original_name).suffix.lower() if original_name else file_path.suffix.lower()
    audio_path = file_path

    # Si es vídeo MP4, extraer audio con ffmpeg primero
    if suffix == '.mp4':
        from centauro.tools.extract_audio import FFMPEG_PATH
        if not FFMPEG_PATH.exists():
            raise RuntimeError(
                f"ffmpeg no encontrado en {FFMPEG_PATH}\n"
                "Instálalo desde https://ffmpeg.org/download.html y colócalo en C:/ffmpeg/bin/"
            )
        mp3_tmp = Path(tempfile.gettempdir()) / f"centauro_{file_path.stem}.mp3"
        comando = [
            str(FFMPEG_PATH),
            "-i", str(file_path),
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "32k",
            "-ac", "1",
            "-ar", "16000",
            "-y",
            str(mp3_tmp),
        ]
        resultado = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if resultado.returncode != 0:
            lineas_error = [l for l in resultado.stderr.splitlines() if l.strip()]
            msg_error = "\n".join(lineas_error[-5:])
            raise RuntimeError(f"Error extrayendo audio con ffmpeg:\n{msg_error}")
        audio_path = mp3_tmp

    # Extraer métricas acústicas (independiente de la transcripción)
    audio_features = None
    try:
        from centauro.tools.audio_features import extraer_metricas_audio
        audio_features = extraer_metricas_audio(audio_path)
    except Exception:
        pass

    # --- AssemblyAI (transcripción + diarización nativa) ---
    assemblyai_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not assemblyai_key:
        raise RuntimeError(
            "ASSEMBLYAI_API_KEY no encontrada en .env\n"
            "Añade tu clave de AssemblyAI para procesar archivos de audio/vídeo."
        )
    texto = _transcribir_con_assemblyai(audio_path, assemblyai_key, original_name or file_path.name)
    return texto, audio_features

    # ---------------------------------------------------------------------------
    # PIPELINE GROQ WHISPER (desactivado — mantener para re-activar si hace falta)
    # ---------------------------------------------------------------------------
    # from groq import Groq
    # from centauro.tools.whisper_transcribe import texto_de_segmentos, segmentos_a_texto_timbrado, WHISPER_MODEL
    # api_key = os.getenv("GROQ_API_KEY")
    # client = Groq(api_key=api_key)
    # if suffix == '.mp4':
    #     nombre_api = (Path(original_name).stem if original_name else file_path.stem) + ".mp3"
    # else:
    #     nombre_api = original_name or audio_path.name
    # with open(audio_path, "rb") as f:
    #     response = client.audio.transcriptions.create(
    #         model=WHISPER_MODEL, file=(nombre_api, f),
    #         response_format="verbose_json", language="es",
    #     )
    # segmentos = getattr(response, "segments", [])
    # texto = segmentos_a_texto_timbrado(segmentos)
    # if not texto:
    #     texto = texto_de_segmentos(segmentos) or getattr(response, "text", "").strip()
    # return texto, audio_features


@cl.on_chat_start
async def start():
    """Inicialización cuando el usuario conecta"""
    # ── Identidad del usuario autenticado ──────────────────────────────────
    app_user = cl.context.session.user
    nombre_del_login = None
    if app_user:
        # Registrar usuario activo para que aparezca en control_gastos.csv
        set_usuario_activo(app_user.identifier)
        rol = app_user.metadata.get("rol", "asesor")
        nombre_del_login = app_user.metadata.get("nombre_completo")

        if rol == "asesor" and nombre_del_login:
            # Asesor → su nombre se pre-carga: sus evaluaciones son siempre suyas
            cl.user_session.set("nombre_asesor", nombre_del_login)
            cl.user_session.set("nombre_asesor_login", nombre_del_login)
        # admin/jefe → NO pre-cargar: evaluarán a cualquier asesor del equipo
        cl.user_session.set("rol_usuario", rol)
        # Guardar username para auditoría (queda en evaluaciones.realizado_por)
        cl.user_session.set("username_activo", app_user.identifier)

    # Verificar si ya se mostró el mensaje de bienvenida en esta sesión
    already_welcomed = cl.user_session.get("welcomed", False)
    # Mensaje de bienvenida (solo se muestra la primera vez)
    if not already_welcomed:
        rol_actual = cl.user_session.get("rol_usuario", "asesor")
        nombre_display = nombre_del_login or "usuario"

        if rol_actual == "admin":
            banner_rol = f"\n> 👑 **Modo Jefe de Equipo** — Conectado como `{nombre_display}`. Puedes evaluar a cualquier asesor del equipo.\n"
        else:
            banner_rol = f"\n> 👤 **Conectado como:** {nombre_display}. Tus evaluaciones se guardarán automáticamente en tu perfil.\n"

        welcome_msg = f"""#  Bienvenido a **Centauro v5.1 (Fase BETA)**
Sistema de evaluación automatizada + **Chat Interactivo** con IA Multi-Agente.
{banner_rol}
---
## 💬 **NUEVO: Modo Chat Interactivo**
Ahora puedes **preguntar directamente** a Centauro:
**Ejemplos de preguntas:**
- *"¿Cómo debería hacer una buena apertura?"*
- *"Muéstrame ejemplos de cierre exitoso"*
- *"@pbi Top 5 programas matriculados del área A"*
**Solo escribe tu pregunta abajo** 👇 y presiona Enter.
---
## 📤 **Modo Evaluación de Llamadas**
1. **Usa el botón 📎 (clip)** o **arrastra tu archivo**
2. Formatos: `.txt`, `.vtt`, `.docx`
3. Puedes escribir texto junto al archivo con:
   - El **nombre del asesor** directamente (ej: *"Llamada de Juan Pérez"* o *"Juan Pérez, lead interesado en..."*)
   - Cualquier contexto adicional (info del lead, programa, objeciones previas, etc.)
4. Espera algunos minutos
5. Descarga reporte PDF completo
---
## 🎯 **¿Qué evalúa Centauro?**
✅ **6 Bloques de Venta Consultiva:**
- 🔍 Investigación • 🎯 Propuesta de Valor
- 💰 Admisión • 🛡️ Objeciones
- 🎬 Cierre • 🎭 Estilo
**🆕 Sistema de Memoria:** Cada evaluación mejora a Centauro y trackea tu progreso.
---
**🤖 Tecnología v5.0:**
Multi-Agente + Sheriff + RAG Multi-Colección + Memoria Continua
👇 **Escribe tu pregunta o adjunta un archivo** 👇
"""
        await cl.Message(content=welcome_msg).send()
        cl.user_session.set("welcomed", True)
    # Inicializar chat handler en sesión (solo si no existe)
    if not cl.user_session.get("chat_handler"):
        chat_handler = ChatHandler()
        cl.user_session.set("chat_handler", chat_handler)
    # Solo ejecutar inicialización completa la primera vez
    if not already_welcomed:
        # Indexar solo si hay cambios en los archivos (sistema de hash)
        async with cl.Step(name="📚 Inicializando base de conocimiento", type="tool") as step:
            try:
                stats = await asyncio.wait_for(
                    cl.make_async(indexar_si_necesario)(),
                    timeout=120
                )
                n_m = stats["manuales"]
                n_bp = stats["buenas_practicas"]
                n_c = stats["coaching"]
                if stats["re_indexado"]:
                    step.output = (
                        f"✅ Base re-indexada: "
                        f"{n_m} manuales + {n_bp} buenas prácticas + {n_c} coaching"
                    )
                else:
                    step.output = (
                        f"✅ Base lista sin cambios: "
                        f"{n_m} manuales + {n_bp} buenas prácticas + {n_c} coaching"
                    )
            except asyncio.TimeoutError:
                step.output = (
                    "⚠️ La inicialización de la base tardó demasiado. "
                    "Continuamos para que puedas usar el chat."
                )
            except Exception as e:
                step.output = f"⚠️ Error en indexación (continuará sin RAG): {e}"
        # Configurar settings para permitir archivos
        await cl.ChatSettings(
            [
                cl.input_widget.TextInput(
                    id="file_upload_info",
                    label="ℹ️ Usa el botón 📎 para adjuntar archivos",
                    initial="Formatos: .txt, .vtt, .docx, .mp3, .mp4"
                )
            ]
        ).send()
    # Guardar estado en sesión
    cl.user_session.set("ready", True)
@cl.action_callback("process_file")
async def process_file_action(action: cl.Action):
    """Callback para procesar archivos adjuntos"""
    await cl.Message(content="📁 Procesando archivo...").send()
@cl.on_message
async def main(message: cl.Message):
    """Procesar transcripciones subidas O responder consultas de chat"""
    # Verificar si hay archivos adjuntos.
    # IMPORTANTE: Chainlit crea cl.Audio para MP3 y cl.Video para MP4,
    # NO cl.File. Hay que incluir los tres tipos para detectarlos correctamente.
    files = (
        [file for file in message.elements if isinstance(file, (cl.File, cl.Audio, cl.Video))]
        if message.elements else []
    )
    # ==================== MODO CHAT INTERACTIVO ====================
    if not files and message.content:
        # Si hay un archivo en proceso, este mensaje es respuesta a un AskUserMessage — ignorar
        if cl.user_session.get("procesando_archivo"):
            return
        # El usuario escribió texto sin adjuntar archivo → Modo chat
        pregunta = message.content.strip()
        if not pregunta:
            return
        # Obtener chat handler
        chat_handler = cl.user_session.get("chat_handler")
        if not chat_handler:
            chat_handler = ChatHandler()
            cl.user_session.set("chat_handler", chat_handler)
        # ── Detectar petición de transcripción ──────────────────────────────
        keywords_transcripcion = [
            "transcripción", "transcripcion", "transcript",
            "texto de la llamada", "texto de la entrevista",
            "transcripción diarizada", "dame la transcripcion",
            "pásame la transcripción", "pasame la transcripcion"
        ]
        if any(kw in pregunta.lower() for kw in keywords_transcripcion):
            ultima_transcripcion = cl.user_session.get("ultima_transcripcion")
            if ultima_transcripcion:
                nombre_archivo = cl.user_session.get("nombre_archivo_evaluado", "evaluacion")
                txt_filename = f"Transcripcion_{nombre_archivo.replace('.', '_')}.txt"
                txt_path = settings.OUTPUTS_DIR / "Transcripciones" / txt_filename
                txt_path.parent.mkdir(exist_ok=True, parents=True)
                txt_path.write_text(ultima_transcripcion, encoding="utf-8")
                await cl.Message(
                    content="📄 **Transcripción lista para descargar:**",
                    elements=[
                        cl.File(
                            name=txt_filename,
                            path=str(txt_path),
                            display="inline"
                        )
                    ]
                ).send()
            else:
                await cl.Message(
                    content="⚠️ No hay ninguna transcripción disponible en esta sesión. "
                            "Adjunta primero un archivo de audio o texto para evaluarlo."
                ).send()
            return
        # ── Procesar pregunta con RAG / Power BI ────────────────────────────
        _kpi_keywords = [
            "kpi", "kpis", "métrica", "metrica", "dashboard", "power bi", "powerbi",
            "ventas del mes", "ventas del año", "ventas de", "total ventas",
            "objetivo de ventas", "target", "revenue", "tasa de conversión",
            "tasa de conversion", "tasa de cierre", "leads totales", "leads activos",
            "pipeline total", "matriculados", "matrículas", "matriculas",
            "facturación", "facturacion", "ingresos del", "cuánto vendió",
            "cuanto vendio", "cuánto se vendió", "ranking de asesores",
            "ranking por ventas", "mejor asesor", "top asesores",
        ]
        es_consulta_pbi = (
            pregunta.lower().strip().startswith("@pbi")
            or any(kw in pregunta.lower() for kw in _kpi_keywords)
        )
        if es_consulta_pbi:
            msg_espera = await cl.Message(
                content="📊 Consultando el modelo semántico de Power BI...\n"
                        "_Generando DAX → ejecutando consulta → interpretando resultado_"
            ).send()
        else:
            msg_espera = await cl.Message(content="🤔 Buscando en la base de conocimiento...").send()
        try:
            nombre_asesor = cl.user_session.get("nombre_asesor", None)
            opp_id_sesion = cl.user_session.get("opportunity_id", None)
            respuesta = await asyncio.get_event_loop().run_in_executor(
                None, chat_handler.procesar_consulta, pregunta, nombre_asesor, opp_id_sesion
            )
            # ── Gráfico: solo si el usuario lo pide explícitamente ───────
            _grafico_kw = [
                "gráfico", "grafico", "chart", "gráfica", "grafica",
                "visualiza", "visualización", "visualizacion",
                "representa", "dibuja", "plot", "plotea",
                "barras", "línea", "linea", "pie",
            ]
            pide_grafico = es_consulta_pbi and any(kw in pregunta.lower() for kw in _grafico_kw)
            elementos = []
            if pide_grafico:
                try:
                    from centauro.core.pbi_charts import generar_grafico_desde_rows
                    from centauro.core.powerbi_client import get_powerbi_client
                    _pbi = get_powerbi_client()
                    if _pbi and len(_pbi._last_query_rows) >= 2:
                        graf_path = await asyncio.get_event_loop().run_in_executor(
                            None,
                            generar_grafico_desde_rows,
                            _pbi._last_query_rows,
                            pregunta,
                            settings.OUTPUTS_DIR / "charts",
                        )
                        if graf_path:
                            elementos = [cl.Image(
                                name="grafico_pbi",
                                path=str(graf_path),
                                display="inline",
                            )]
                except Exception as _e:
                    import logging as _log
                    _log.getLogger(__name__).warning(f"No se pudo generar gráfico PBI: {_e}")
            # ── Aclaración PBI: el agente necesita más info del usuario ─────
            _ACLARACION_PREFIX = "__PBI_ACLARACION__: "
            if respuesta.startswith(_ACLARACION_PREFIX):
                pregunta_aclaracion = respuesta[len(_ACLARACION_PREFIX):].strip()
                # Sustituir el spinner por la pregunta de aclaración vía AskUserMessage
                await msg_espera.remove()
                res_aclaracion = await cl.AskUserMessage(
                    content=pregunta_aclaracion,
                    timeout=120,
                ).send()
                if res_aclaracion and res_aclaracion.get("output"):
                    aclaracion = res_aclaracion["output"].strip()
                    # Reenviar a PBI con contexto completo (sin pasar por clasificador)
                    pregunta_limpia = re.sub(r"^@pbi\s*", "", pregunta, flags=re.IGNORECASE).strip()
                    pregunta_enriquecida = f"@pbi {pregunta_limpia}. El usuario confirma: {aclaracion}"
                    msg_espera2 = await cl.Message(
                        content="📊 Consultando el modelo semántico de Power BI...\n"
                                "_Generando DAX → ejecutando consulta → interpretando resultado_"
                    ).send()
                    nombre_asesor = cl.user_session.get("nombre_asesor", None)
                    opp_id_sesion = cl.user_session.get("opportunity_id", None)
                    respuesta = await asyncio.get_event_loop().run_in_executor(
                        None, chat_handler.procesar_consulta, pregunta_enriquecida, nombre_asesor, opp_id_sesion
                    )
                    await msg_espera2.remove()
                    # Si el agente vuelve a pedir aclaración, mostrar la pregunta limpia
                    _ACLARACION_PREFIX2 = "__PBI_ACLARACION__: "
                    if respuesta.startswith(_ACLARACION_PREFIX2):
                        respuesta = respuesta[len(_ACLARACION_PREFIX2):]
                else:
                    respuesta = (
                        "⏱️ No recibí tu respuesta. "
                        "Por favor, reformula tu pregunta empezando por `@pbi`."
                    )

            await cl.Message(content=respuesta, elements=elementos).send()
        except Exception as e:
            await cl.Message(
                content=f"❌ Error procesando consulta: {str(e)}\n\nIntenta reformular tu pregunta."
            ).send()
        return
    # ==================== MODO EVALUACIÓN (archivo adjunto) ====================
    if not files:
        await cl.Message(
            content="💬 **Escribe tu pregunta** o **adjunta un archivo** para evaluación\n\n"
                    "**Ejemplos de preguntas:**\n"
                    "- ¿Cómo hacer una buena investigación?\n"
                    "- Muéstrame ejemplos de cierre exitoso\n"
                    "- ¿Cuál es mi rendimiento?\n\n"
                    "📎 O usa el botón de clip para adjuntar transcripción (.txt, .vtt, .docx) o audio/vídeo (.mp3, .mp4)"
        ).send()
        return
    # Obtener archivo
    file = files[0]
    file_path = Path(file.path)
    cl.user_session.set("procesando_archivo", True)  # Bloquear chat mientras haya AskUserMessages pendientes
    # Capturar texto del usuario como contexto adicional
    # Si el usuario escribe texto junto con el archivo, se usa como contexto
    contexto_usuario = message.content.strip() if message.content and message.content.strip() else None

    # Detectar si el usuario especificó el nombre del asesor explícitamente en el mensaje
    nombre_especificado_en_mensaje = None
    opp_id_en_mensaje = None  # Opportunity ID escrito por el usuario en el mensaje
    if contexto_usuario:
        # ── Extraer opportunity ID del texto del mensaje ──────────────────
        _m_opp = re.search(r'\b(\d{4}-\d{6,12})\b', contexto_usuario)
        if _m_opp:
            opp_id_en_mensaje = _m_opp.group(1)
            # Limpiar el ID del contexto para no contaminar los prompts de los agentes
            contexto_usuario = re.sub(r'\b\d{4}-\d{6,12}\b', '', contexto_usuario).strip() or None
    if contexto_usuario:
        # ── Extracción del nombre con LLM ─────────────────────────────────────
        # GPT-4o-mini entiende cualquier formato sin necesidad de regex frágiles:
        # "Asesor: X", "asesora es X", "la lleva X", "se llama X", etc.
        # También devuelve el contexto limpio (sin la mención del asesor) en la misma llamada.
        try:
            _extr = await asyncio.get_event_loop().run_in_executor(
                None, _extraer_nombre_y_limpiar_contexto, contexto_usuario
            )
            nombre_especificado_en_mensaje = _extr.get("nombre")  # None si no encontró
            _ctx_limpio = _extr.get("contexto_limpio", "").strip()
            contexto_usuario = _ctx_limpio or None
        except Exception:
            # Si el LLM falla, seguimos sin nombre extraído (el contexto queda intacto)
            pass

    if nombre_especificado_en_mensaje or contexto_usuario:
        partes = []
        if nombre_especificado_en_mensaje:
            partes.append(f"👤 Asesor especificado: **{nombre_especificado_en_mensaje}**")
        if contexto_usuario:
            partes.append("📝 Contexto adicional capturado")
        await cl.Message(
            content=" · ".join(partes) + " — Se tendrá en cuenta durante la evaluación."
        ).send()
    # ==================== VALIDACIÓN CRÍTICA: NOMBRE DE ARCHIVO ====================
    try:
        from centauro.utils import validar_archivo_para_procesamiento, generar_mensaje_error_usuario
        validacion = validar_archivo_para_procesamiento(file_path)
        if not validacion:
            # Generar mensaje de error amigable para Chainlit
            mensaje_error = generar_mensaje_error_usuario(validacion, "análisis de conversación")
            await cl.Message(
                content=mensaje_error
            ).send()
            cl.user_session.set("procesando_archivo", False)
            return
    except ImportError:
        # Si no existe el módulo de validaciones, continuar sin validar
        pass
    # ===============================================================================
    # Usar el nombre original del archivo para detectar el tipo (file_path puede ser un UUID sin extensión)
    es_multimedia = Path(file.name).suffix.lower() in ('.mp4', '.mp3')

    # ── Pregunta anticipada de asesor (solo multimedia sin nombre ya conocido) ──
    # Se hace ANTES de transcribir para no tener al usuario esperando sin actividad.
    # Se omite si ya hay opp_id_en_mensaje o en el nombre del archivo: en ese caso
    # Supabase resolverá el propietario automáticamente.
    nombre_asesor_login = cl.user_session.get("nombre_asesor_login")
    _opp_id_en_filename = extraer_opportunity_id(file.name) if file else None
    _opp_id_conocido_ya = bool(opp_id_en_mensaje or _opp_id_en_filename)
    if es_multimedia and not nombre_asesor_login and not nombre_especificado_en_mensaje and not _opp_id_conocido_ya:
        from centauro.core.gestion_asesores import gestion_asesores as _ga_pre
        sugerencias_pre = _ga_pre.nombres_canonicos[:5] if _ga_pre.nombres_canonicos else []
        sugerencias_pre_txt = (
            "\n\n**Asesores conocidos:** " + " · ".join(f"`{s}`" for s in sugerencias_pre)
        ) if sugerencias_pre else ""
        res_nombre_previo = await cl.AskUserMessage(
            content=(
                f"👤 **¿Quién es el asesor de esta llamada?**{sugerencias_pre_txt}\n\n"
                f"Escribe el nombre (Nombre Apellido) o **skip** para detectarlo de la transcripción."
            ),
            timeout=30
        ).send()
        if res_nombre_previo and res_nombre_previo.get("output"):
            respuesta_pre = res_nombre_previo["output"].strip()
            if respuesta_pre.lower() not in ("skip", "omitir", "-", "n/a"):
                nombre_especificado_en_mensaje = respuesta_pre.strip().title()

    # ── Pregunta anticipada de Opportunity ID (antes de transcribir) ──
    _opp_id_pre = None  # aplica a cualquier tipo de archivo (txt, vtt, docx, mp3, mp4)
    if file:
        _opp_id_pre = extraer_opportunity_id(file.name)
        if _opp_id_pre:
            await cl.Message(content=f"🔗 **Opportunity ID detectado en el nombre del archivo:** `{_opp_id_pre}`").send()
        elif opp_id_en_mensaje:
            # El usuario lo escribió en el mensaje junto al archivo
            _opp_id_pre = opp_id_en_mensaje
            await cl.Message(content=f"🔗 **Opportunity ID detectado en el mensaje:** `{_opp_id_pre}`").send()
        else:
            try:
                _opp_res = await cl.AskUserMessage(
                    content=(
                        "🔗 **¿Tienes el ID de oportunidad de esta entrevista?**\n"
                        "Escríbelo (ej: `2021-002579270`) o escribe **no** para continuar sin él.\n"
                        "_Tienes 5 minutos para responder._"
                    ),
                    timeout=300
                ).send()
                if _opp_res:
                    _opp_txt = _opp_res.get("output", "").strip()
                    # Aceptar cualquier forma de "no": "no", "no tengo", "no lo tengo",
                    # "no tenía", "n", "-", vacío, "skip"…
                    _es_respuesta_no = (
                        not _opp_txt
                        or _opp_txt.lower() in ("no", "n", "-", "skip", "omitir")
                        or bool(re.match(r'^no\b', _opp_txt, re.IGNORECASE))
                    )
                    if _es_respuesta_no:
                        await cl.Message(content="⏭️ Continuando sin Opportunity ID.").send()
                    elif re.match(r'^\d{4}-\d{6,12}$', _opp_txt):
                        _opp_id_pre = _opp_txt
                        await cl.Message(content=f"✅ **Opportunity ID guardado:** `{_opp_id_pre}`").send()
                    else:
                        # Intentar extraer el ID si lo escribió dentro de texto libre
                        _m_id_inline = re.search(r'\b(\d{4}-\d{6,12})\b', _opp_txt)
                        if _m_id_inline:
                            _opp_id_pre = _m_id_inline.group(1)
                            await cl.Message(content=f"✅ **Opportunity ID guardado:** `{_opp_id_pre}`").send()
                        else:
                            await cl.Message(
                                content=f"⚠️ `{_opp_txt}` no tiene el formato esperado (`2021-002579270`). "
                                        f"Continuando sin Opportunity ID."
                            ).send()
            except Exception:
                pass
        cl.user_session.set("opportunity_id", _opp_id_pre)

        # ── Enriquecer contexto_usuario con datos del lead desde Supabase ────
        # Mismo enriquecimiento que hace analizar_entrevista_completa() en batch.
        # Sin esto, los agentes no saben el nombre del lead, país, edad ni programa.
        if _opp_id_pre:
            try:
                from centauro.core.database import get_database as _get_db_lead
                _db_lead = _get_db_lead()
                _datos_lead = _db_lead.obtener_oportunidad(_opp_id_pre)
                if _datos_lead:
                    _contexto_lead = (
                        f"\n\n--- PERFIL DEL LEAD (datos verificados de CRM) ---\n"
                        f"Nombre: {_datos_lead.get('nombre_lead', 'N/A')}\n"
                        f"País: {_datos_lead.get('pais', 'N/A')}\n"
                        f"Edad: {_datos_lead.get('edad', 'N/A')} años\n"
                        f"Programa: {_datos_lead.get('programa', 'N/A')}\n"
                        f"Pilar: {_datos_lead.get('pilar', 'N/A')}\n"
                        f"---\n"
                    )
                    contexto_usuario = (contexto_usuario + _contexto_lead) if contexto_usuario else _contexto_lead
                    cl.user_session.set("datos_oportunidad", _datos_lead)
                    await cl.Message(
                        content=f"📋 **Lead identificado:** {_datos_lead.get('nombre_lead', 'N/A')} "
                                f"· {_datos_lead.get('pais', '')} "
                                f"· {_datos_lead.get('programa', '')}"
                    ).send()
                    # ── Auto-usar propietario de Supabase como asesor ─────────
                    _propietario = _datos_lead.get('propietario')
                    _tiene_asesor_conocido = bool(
                        cl.user_session.get("nombre_asesor_login") or nombre_especificado_en_mensaje
                    )
                    if _propietario and not _tiene_asesor_conocido:
                        nombre_especificado_en_mensaje = _propietario
                        await cl.Message(
                            content=f"👤 **Asesor identificado:** {_propietario}"
                        ).send()
            except Exception as _e_lead:
                pass  # No bloquear la evaluación si falla el enriquecimiento

    # ── Verificar si ya existe evaluación para este opportunity_id ────────────
    # Lo hacemos antes de transcribir para que, si el usuario dice "no sobreescribir",
    # podamos devolver la evaluación existente sin gastar nada en LLMs ni transcripción.
    _sobreescribir_eval_id = None  # None = INSERT nueva; int = UPDATE fila existente
    if _opp_id_pre:
        try:
            from centauro.core.database import get_database as _get_db
            _db_check = _get_db()
            _eval_existente = _db_check.buscar_evaluacion_por_oportunidad(_opp_id_pre)
            if _eval_existente:
                _fecha_eval = (_eval_existente.get("fecha") or "")[:10]
                _cal_existente = _eval_existente.get("calificacion_global", "N/A")
                EMOJI_CAL_CHECK = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}
                _emoji_check = EMOJI_CAL_CHECK.get(_cal_existente, "⚪")
                try:
                    _res_sobreescribir = await cl.AskUserMessage(
                        content=(
                            f"⚠️ **Esta entrevista ya fue evaluada anteriormente**\n\n"
                            f"- **Opportunity ID:** `{_opp_id_pre}`\n"
                            f"- **Fecha:** {_fecha_eval}\n"
                            f"- **Calificación:** {_emoji_check} {_cal_existente}\n\n"
                            f"¿Qué deseas hacer?\n"
                            f"- Escribe **sí** para re-analizar y sobreescribir los datos\n"
                            f"- Escribe **no** para ver la evaluación ya guardada (sin coste)"
                        ),
                        timeout=60
                    ).send()
                except Exception:
                    _res_sobreescribir = None

                _resp_txt = (_res_sobreescribir or {}).get("output", "no").strip().lower()
                if _resp_txt in ("sí", "si", "s", "yes", "y", "sobreescribir", "reanalizar", "re-analizar", "1"):
                    _sobreescribir_eval_id = _eval_existente.get("id")
                    await cl.Message(
                        content=f"🔄 **Re-analizando...** Se sobreescribirá la evaluación del {_fecha_eval}."
                    ).send()
                else:
                    # Mostrar evaluación existente y salir sin gastar nada
                    _bloques_existentes = _db_check.obtener_calificaciones_bloque(_eval_existente["id"])
                    EMOJI_CAL_SHOW = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}
                    _cal_g = _eval_existente.get("calificacion_global", "N/A")
                    _msg_existente = (
                        f"# 📊 Evaluación guardada — {_fecha_eval}\n"
                        f"---\n"
                        f"## {EMOJI_CAL_SHOW.get(_cal_g, '⚪')} Calificación Global: **{_cal_g}**\n"
                        f"**Archivo:** {_eval_existente.get('archivo_origen', 'N/A')}\n"
                        f"---\n"
                        f"## 📈 Evaluación por Bloques\n"
                    )
                    for _b in _bloques_existentes:
                        _bcal = _b.get("calificacion", "N/A")
                        _msg_existente += f"{EMOJI_CAL_SHOW.get(_bcal, '⚪')} **{_b.get('bloque', '')}**: {_bcal}\n"
                    if _eval_existente.get("perfil_lead"):
                        _msg_existente += f"\n**Perfil Lead:** {_eval_existente['perfil_lead']}\n"
                    _msg_existente += (
                        "\n---\n"
                        "💡 Si quieres re-analizarla, sube el archivo de nuevo y responde **sí** a la confirmación."
                    )
                    await cl.Message(content=_msg_existente).send()
                    cl.user_session.set("procesando_archivo", False)
                    return  # Salir sin analizar ni gastar
        except Exception as _e_check:
            pass  # Si falla la consulta a Supabase, continuar normalmente

    cl.user_session.set("sobreescribir_eval_id", _sobreescribir_eval_id)

    import time as _time
    _tiempo_inicio = _time.time()

    tiempo_estimado = "5-10 minutos (transcripción + análisis)" if es_multimedia else "1-2 minutos"
    await cl.Message(
        content=f"📁 Procesando: **{file.name}**\n\nEsto puede tardar {tiempo_estimado}..."
    ).send()
    # Leer contenido según extensión
    # NOTA: NO limpiamos VTT aquí - el agente de diarización necesita
    # el texto crudo para detectar UUIDs de speakers
    audio_features_sesion = None  # Solo disponible para archivos de audio
    try:
        if Path(file.name).suffix.lower() == '.docx':
            texto_crudo = leer_word(file_path)
        elif es_multimedia:
            # MP4 o MP3: extraer audio (si MP4) y transcribir
            import os as _os
            _usar_assemblyai = bool(_os.getenv("ASSEMBLYAI_API_KEY"))
            _step_name = "🎙️ Transcribiendo con AssemblyAI (diarización nativa)" if _usar_assemblyai else "🎙️ Transcribiendo audio con Groq Whisper"
            async with cl.Step(name=_step_name, type="tool") as step:
                if Path(file.name).suffix.lower() == '.mp4':
                    step.output = "⏳ Extrayendo audio con ffmpeg..."
                elif _usar_assemblyai:
                    step.output = "⏳ Subiendo a AssemblyAI..."
                else:
                    step.output = "⏳ Enviando a Groq Whisper..."
                # Pasar file.name para que la API de Groq reconozca el formato correctamente
                texto_crudo, audio_features_sesion = await cl.make_async(_procesar_archivo_multimedia)(file_path, file.name)
                cl.user_session.set("audio_features", audio_features_sesion)
                num_chars = len(texto_crudo) if texto_crudo else 0
                metricas_ok = audio_features_sesion and audio_features_sesion.get("disponible")
                step.output = f"✅ Transcripción completada ({num_chars} caracteres)" + (
                    f"\n📊 Métricas de audio extraídas" if metricas_ok else ""
                )
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                texto_crudo = f.read()
            # Ya no llamamos a limpiar_formato_vtt() aquí
            # El agente de diarización lo procesa correctamente
        if not texto_crudo or len(texto_crudo) < 100:
            await cl.Message(
                content="❌ El archivo parece estar vacío o no se pudo leer correctamente."
            ).send()
            return
    except Exception as e:
        await cl.Message(
            content=f"❌ Error leyendo el archivo: {e}"
        ).send()
        return
    # Envolver TODO en try-catch para capturar errores
    try:
        # Crear orquestador
        orchestrator = CentauroOrchestrator()
        # ==================== FASE 0: PRIVACIDAD ====================
        async with cl.Step(name="🛡️ FASE 0: Protección de datos sensibles", type="tool") as step:
            resultado_redaccion = redact_pii(texto_crudo)
            texto_protegido = resultado_redaccion.text
            stats = resultado_redaccion.stats
            total_redactado = sum(stats.values())
            if total_redactado > 0:
                step.output = f"🔒 Datos redactados: {dict(stats)}\n\n✅ Transcripción sanitizada (RGPD compliant)"
            else:
                step.output = "✅ No se detectaron datos sensibles"
        # ==================== FASE 1: DIARIZACIÓN ====================
        async with cl.Step(name="🎙️ FASE 1: Diarización (ASESOR/LEAD)", type="tool") as step:
            from centauro.agents import DiarizationAgent
            from centauro.core.gestion_asesores import gestion_asesores
            diarization_agent = DiarizationAgent(nombre_asesor=file.name)
            # Ejecutar diarización en hilo para no bloquear el loop async de Chainlit
            transcripcion_diarizada = await cl.make_async(diarization_agent.diarizar)(texto_protegido, file.name)
            # NUEVO: Detección inteligente con validación
            asesor_detectado_inicial = diarization_agent.asesor_detectado
            # Intentar extraer de transcripción primero
            if not asesor_detectado_inicial or not gestion_asesores._es_nombre_valido(asesor_detectado_inicial):
                nombre_de_transcripcion = gestion_asesores.extraer_nombre_de_transcripcion(texto_protegido)
                if nombre_de_transcripcion:
                    asesor_detectado_inicial = nombre_de_transcripcion
            num_lineas = len([l for l in transcripcion_diarizada.split('\n') if l.strip()])
            step.output = f"✅ Transcripción diarizada\n\n📊 {num_lineas} líneas procesadas"
            # Guardar transcripción en sesión para descarga bajo demanda
            cl.user_session.set("ultima_transcripcion", transcripcion_diarizada)
            cl.user_session.set("nombre_archivo_evaluado", file.name)
            # Detección de idioma (equivalente a analizar_entrevista_completa en batch)
            from centauro.utils.validaciones import detectar_idioma_transcripcion
            _idioma_entrevista = detectar_idioma_transcripcion(transcripcion_diarizada)
            if _idioma_entrevista == "en":
                step.output += "\n\n🌐 Entrevista detectada en **INGLÉS** — ajustando evaluación"
                _contexto_idioma = (
                    "\n\nIDIOMA DE LA ENTREVISTA: INGLÉS\n"
                    "Esta entrevista fue conducida en inglés. Evalúa los comportamientos "
                    "del asesor y del lead en inglés. Los criterios de evaluación son "
                    "exactamente los mismos, pero aplicados al contexto lingüístico inglés. "
                    "Los ejemplos de frases del prompt están en español como referencia "
                    "conceptual — busca sus equivalentes en inglés en la transcripción. "
                    "Devuelve el JSON de evaluación con los campos de texto en español, "
                    "excepto las citas literales de evidencia (evidencia_principal, "
                    "evidencias_extra), que deben reproducirse en inglés tal como "
                    "aparecen en la transcripción.\n"
                )
                contexto_usuario = (contexto_usuario or "") + _contexto_idioma
            # Si aún no tenemos un nombre válido, preguntar al usuario
            if not asesor_detectado_inicial or not gestion_asesores._es_nombre_valido(asesor_detectado_inicial):
                step.output += "\n\n⚠️ No se pudo detectar el nombre del asesor automáticamente"
        # ==================== CONFIRMACIÓN DE ASESOR ====================
        # Validar y normalizar nombre del asesor
        asesor_confirmado = None

        # ── Prioridad 1: nombre conocido por login (autenticación) ─────────
        nombre_asesor_login = cl.user_session.get("nombre_asesor_login")
        if nombre_asesor_login:
            # El usuario está autenticado → sabemos quién es, no hace falta preguntar
            asesor_confirmado = nombre_asesor_login

        # ── Prioridad 1.5: nombre especificado explícitamente en el mensaje ─
        if not asesor_confirmado and nombre_especificado_en_mensaje:
            try:
                asesor_confirmado = gestion_asesores.obtener_nombre_canonico(nombre_especificado_en_mensaje)
            except ValueError:
                asesor_confirmado = nombre_especificado_en_mensaje

        # ── Prioridad 2: detectado en la transcripción/contexto ───────────
        if not asesor_confirmado:
            # Intentar extraer nombre del contexto_usuario si no se detectó en transcripción
            if not asesor_detectado_inicial or not gestion_asesores._es_nombre_valido(asesor_detectado_inicial):
                if contexto_usuario:
                    nombre_de_contexto = gestion_asesores.extraer_nombre_de_transcripcion(contexto_usuario)
                    if nombre_de_contexto:
                        asesor_detectado_inicial = nombre_de_contexto

            if asesor_detectado_inicial and gestion_asesores._es_nombre_valido(asesor_detectado_inicial):
                # Buscar si existe uno similar
                resultado_validacion = gestion_asesores.validar_y_normalizar(asesor_detectado_inicial)
                nombre_norm, nombre_existente, score = resultado_validacion
                if nombre_existente and score >= 85:
                    if score >= 99:
                        # Coincidencia exacta → usar perfil existente sin preguntar
                        asesor_confirmado = nombre_existente
                    else:
                        # Coincidencia parcial → pedir confirmación
                        res = await cl.AskUserMessage(
                            content=f"👤 **Confirmación de asesor**\n\n"
                                    f"Detectado: **{nombre_norm}**\n"
                                    f"Existe perfil similar: **{nombre_existente}** (similitud: {score}%)\n\n"
                                    f"¿Cuál es correcto?\n"
                                    f"1️⃣ Usar perfil existente: **{nombre_existente}**\n"
                                    f"2️⃣ Crear nuevo perfil: **{nombre_norm}**\n"
                                    f"O escribe el nombre correcto\n\n"
                                    f"_(Si no respondes en 30s, se usará el perfil existente)_",
                            timeout=30
                        ).send()
                        if res and res.get("output"):
                            respuesta = res["output"].strip()
                            usar_existente = {"1", "1️⃣", "uno", "usar", "usa", "el que hay", "existente", "si", "sí"}
                            crear_nuevo = {"2", "2️⃣", "dos", "nuevo", "crear"}
                            if respuesta.lower() in usar_existente:
                                asesor_confirmado = nombre_existente
                            elif respuesta.lower() in crear_nuevo:
                                asesor_confirmado = nombre_norm
                            elif gestion_asesores._es_nombre_valido(respuesta):
                                # Escribió un nombre nuevo → crear perfil con ese nombre directamente
                                asesor_confirmado = respuesta.strip().title()
                            else:
                                await cl.Message(content=f"⚠️ Respuesta no reconocida: '{respuesta}'. Usando perfil existente.").send()
                                asesor_confirmado = nombre_existente
                        else:
                            # Timeout, usar existente automáticamente
                            asesor_confirmado = nombre_existente
                else:
                    # No hay similar, usar detectado directamente sin preguntar
                    asesor_confirmado = nombre_norm
            else:
                # No se detectó nombre válido — preguntar al usuario
                sugerencias = gestion_asesores.nombres_canonicos[:5] if gestion_asesores.nombres_canonicos else []
                sugerencias_texto = ""
                if sugerencias:
                    sugerencias_texto = "\n\n**Asesores conocidos:**\n" + "\n".join(f"• {s}" for s in sugerencias)
                res = await cl.AskUserMessage(
                    content=f"👤 **¿Quién es el asesor de esta llamada?**\n\n"
                            f"No se pudo detectar automáticamente.\n"
                            f"Escribe el nombre (Nombre Apellido) o **skip** para continuar sin perfil:{sugerencias_texto}",
                    timeout=60
                ).send()
                if res and res.get("output"):
                    nombre_manual = res["output"].strip()
                    if nombre_manual.lower() in ("skip", "omitir", "-", "n/a"):
                        asesor_confirmado = "Asesor Desconocido"
                    else:
                        # Si solo escribió el nombre de pila, pedir apellido
                        if len(nombre_manual.split()) < 2:
                            res_apellido = await cl.AskUserMessage(
                                content=f"👤 Solo has escrito el nombre de pila: **{nombre_manual}**\n\n"
                                        f"¿Cuál es su apellido?\n\n"
                                        f"_(Si no respondes en 30s, se guardará como Asesor Desconocido)_",
                                timeout=30
                            ).send()
                            if res_apellido and res_apellido.get("output"):
                                apellido = res_apellido["output"].strip()
                                nombre_manual = f"{nombre_manual} {apellido}".title()
                            else:
                                asesor_confirmado = "Asesor Desconocido"
                        if asesor_confirmado is None:
                            try:
                                asesor_confirmado = gestion_asesores.obtener_nombre_canonico(nombre_manual)
                            except ValueError:
                                await cl.Message(content=f"⚠️ Nombre no reconocido: '{nombre_manual}'. Usando como está.").send()
                                asesor_confirmado = nombre_manual.strip().title()
                else:
                    # Timeout → continuar sin bloquear
                    asesor_confirmado = "Asesor Desconocido"
        # ── Verificar que el asesor existe en Supabase ──────────────────────
        # Si el nombre no está registrado (no viene del login ni es ya "Desconocido"),
        # intentar resolver por opp_id antes de preguntar al usuario.
        _nombre_asesor_login = cl.user_session.get("nombre_asesor_login")
        _es_desconocido = asesor_confirmado == "Asesor Desconocido"
        if not _nombre_asesor_login and not _es_desconocido:
            from centauro.core.database import get_database as _get_db_check
            _db_check = _get_db_check()
            if _db_check.disponible and not _db_check.buscar_asesor(asesor_confirmado):
                # ── Intento 1: buscar asesor por opp_id (evaluaciones previas) ──
                _asesor_por_opp = None
                if _opp_id_pre:
                    _asesor_por_opp = _db_check.obtener_asesor_por_opp_id(_opp_id_pre)
                    if _asesor_por_opp:
                        asesor_confirmado = _asesor_por_opp["nombre"]
                        await cl.Message(
                            content=f"👤 **Asesor identificado por Opportunity ID:** {asesor_confirmado}"
                        ).send()

                # ── Intento 2: el usuario ya especificó el nombre, no preguntar de nuevo ──
                # Si el nombre vino explícito en el mensaje original (con o sin opp_id),
                # confiamos en él. Solo se avisa si realmente no está registrado.
                if not _asesor_por_opp and nombre_especificado_en_mensaje:
                    _detalle = (
                        f"pero tienes el Opportunity ID `{_opp_id_pre}`. "
                        f"Se guardará bajo la oportunidad indicada."
                        if _opp_id_pre
                        else "Continuando con ese nombre — puede que haya una variante registrada."
                    )
                    await cl.Message(
                        content=f"⚠️ _{asesor_confirmado}_ no está registrado en el sistema, {_detalle}"
                    ).send()

                # ── Intento 3: sin nombre explícito ni resolución → preguntar al usuario ──
                elif not _asesor_por_opp and not nombre_especificado_en_mensaje:
                    _sugerencias_db = gestion_asesores.nombres_canonicos[:8] if gestion_asesores.nombres_canonicos else []
                    _sugerencias_db_txt = (
                        "\n\n**Asesores registrados:** " + " · ".join(f"`{s}`" for s in _sugerencias_db)
                    ) if _sugerencias_db else ""
                    try:
                        _res_nombre_db = await cl.AskUserMessage(
                            content=(
                                f"⚠️ **Asesor no reconocido:** _{asesor_confirmado}_\n\n"
                                f"Este nombre no está registrado en el sistema. "
                                f"¿Puedes indicar el nombre correcto?{_sugerencias_db_txt}\n\n"
                                f"Escribe el nombre exacto o **skip** para continuar como _Asesor Desconocido_."
                            ),
                            timeout=60
                        ).send()
                    except Exception:
                        _res_nombre_db = None

                    if _res_nombre_db and _res_nombre_db.get("output"):
                        _nombre_corregido = _res_nombre_db["output"].strip()
                        if _nombre_corregido.lower() in ("skip", "omitir", "-", "n/a", "no"):
                            asesor_confirmado = "Asesor Desconocido"
                        else:
                            # Si el usuario escribió una frase ("El asesor es X"), extraer solo el nombre
                            _m_frase = re.search(
                                r'(?:asesor|nombre|advisor|llama)\s*(?:[:=,]|es|se\s+llama)?\s*'
                                r'([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)',
                                _nombre_corregido, re.IGNORECASE
                            ) or re.search(
                                r'\bes\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)',
                                _nombre_corregido, re.IGNORECASE
                            )
                            if _m_frase:
                                _nombre_corregido = _m_frase.group(1).strip().title()
                            try:
                                asesor_confirmado = gestion_asesores.obtener_nombre_canonico(_nombre_corregido)
                            except ValueError:
                                await cl.Message(
                                    content=f"⚠️ `{_nombre_corregido}` no está registrado en el sistema. "
                                            f"Guardando como **Asesor Desconocido**."
                                ).send()
                                asesor_confirmado = "Asesor Desconocido"
                    else:
                        asesor_confirmado = "Asesor Desconocido"
        # ─────────────────────────────────────────────────────────────────────
        # Mostrar confirmación
        await cl.Message(content=f"✅ **Asesor confirmado:** {asesor_confirmado}").send()
        # Guardar en sesión
        cl.user_session.set("nombre_asesor", asesor_confirmado)

        # opportunity_id ya fue preguntado antes de la transcripción
        opp_id = cl.user_session.get("opportunity_id")

        # ── Cola: esperar turno antes de las fases LLM pesadas ────────────────
        # Solo un análisis corre a la vez para evitar rate limits de OpenAI.
        # Si hay análisis en curso, el usuario ve su posición y espera su turno.
        _liberar_slot_analisis = await adquirir_slot()
        cl.user_session.set("_slot_analisis", _liberar_slot_analisis)
        _tiempo_inicio = _time.time()  # resetear: mide solo el análisis, no la espera en cola

        # ==================== FASE 2: EXTRACCIÓN DE TEMAS ====================
        async with cl.Step(name="🧠 FASE 2: Extracción de temas (RAG Dinámico)", type="tool") as step:
            try:
                cache_key = file.name
                temas = await cl.make_async(orchestrator.rag_agent.extraer_temas_llamada)(transcripcion_diarizada, cache_key)
                # Convertir a lista si no lo es
                if temas and not isinstance(temas, list):
                    temas = list(temas) if hasattr(temas, '__iter__') else [str(temas)]
                if temas and len(temas) > 0:
                    temas_limitados = temas[:8] if len(temas) > 8 else temas
                    temas_str = ", ".join(str(t) for t in temas_limitados)
                    step.output = f"✅ Temas identificados:\n\n🎯 {temas_str}"
                else:
                    step.output = "✅ Análisis de contexto completado"
            except Exception as e:
                step.output = f"⚠️ Error en extracción de temas: {str(e)}\n\n(Continuará sin RAG dinámico)"
        # ==================== FASE 2.5: PERFIL DEL LEAD ====================
        async with cl.Step(name="📊 FASE 2.5: Extracción de perfil del lead", type="tool") as step:
            try:
                resumen_contextual = await cl.make_async(orchestrator._extraer_resumen_contextual)(transcripcion_diarizada, file.name)
                perfil = resumen_contextual.get('perfil_lead', 'N/A')
                fase = resumen_contextual.get('fase_funnel', 'N/A')
                resultado = resumen_contextual.get('resultado_general', 'N/A')
                step.output = f"""✅ Perfil extraído
**Perfil:** {perfil[:100]}...
**Fase Funnel:** {fase}
**Resultado:** {resultado}"""
            except Exception as e:
                resumen_contextual = {"perfil_lead": "N/A", "fase_funnel": "N/A", "resultado_general": "N/A"}
                step.output = f"⚠️ Error extrayendo perfil: {e} (usando fallback)"
        # ==================== FASE 3: EVALUACIÓN MULTI-AGENTE ====================
        evaluaciones = []
        async with cl.Step(name="🤖 FASE 3: Evaluación Multi-Agente Híbrida", type="tool") as fase3:
            # BLOQUES CRÍTICOS (Individual)
            bloques_criticos = [
                ("🔍 Investigación", "Investigación"),
                ("💰 Admisión y Propuesta Económica", "Proceso de Admisión y Propuesta Económica"),
                ("🛡️ Manejo de objeciones", "Manejo de objeciones"),
                ("🎬 Cierre y próximos pasos", "Cierre y próximos pasos")
            ]
            for emoji_nombre, bloque_nombre in bloques_criticos:
                async with cl.Step(name=f"{emoji_nombre}", type="run") as sub_step:
                    try:
                        if bloque_nombre == "Investigación":
                            from centauro.agents import InvestigacionAgent
                            extracto = orchestrator.config.get_extracto(bloque_nombre, transcripcion_diarizada)
                            ctx = await cl.make_async(orchestrator.rag_agent.buscar_contexto_para_bloque)(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = InvestigacionAgent()
                            resultado = await cl.make_async(agente.evaluate)(extracto, ctx, contexto_usuario)
                        elif bloque_nombre == "Proceso de Admisión y Propuesta Económica":
                            from centauro.agents import AdmisionEconomicaAgent
                            ctx = await cl.make_async(orchestrator.rag_agent.buscar_contexto_para_bloque)(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = AdmisionEconomicaAgent()
                            resultado = await cl.make_async(agente.evaluate)(transcripcion_diarizada, ctx, contexto_usuario)
                        elif bloque_nombre == "Manejo de objeciones":
                            from centauro.agents import ObjecionesAgent
                            ctx = await cl.make_async(orchestrator.rag_agent.buscar_contexto_para_bloque)(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = ObjecionesAgent()
                            resultado = await cl.make_async(agente.evaluate)(transcripcion_diarizada, ctx, contexto_usuario)
                        elif bloque_nombre == "Cierre y próximos pasos":
                            from centauro.agents import CierreAgent
                            ctx = await cl.make_async(orchestrator.rag_agent.buscar_contexto_para_bloque)(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = CierreAgent()
                            resultado = await cl.make_async(agente.evaluate)(transcripcion_diarizada, ctx, contexto_usuario)
                        evaluaciones.append(resultado.to_dict())
                        nota = resultado.calificacion if resultado.calificacion else "N/A"
                        sub_step.output = f"✅ Evaluado: **{nota}**"
                    except Exception as e:
                        sub_step.output = f"❌ Error: {e}"
            # BLOQUES SECUNDARIOS (Batch)
            async with cl.Step(name="📦 Propuesta Valor + Estilo (Batch)", type="run") as sub_step:
                try:
                    evals_secundarias = await cl.make_async(orchestrator._evaluar_bloques_secundarios)(transcripcion_diarizada, file.name, contexto_usuario, audio_features_sesion)
                    evaluaciones.extend(evals_secundarias)
                    sub_step.output = f"✅ 2 bloques evaluados en batch"
                except Exception as e:
                    sub_step.output = f"❌ Error: {e}"
            fase3.output = f"✅ {len(evaluaciones)} bloques evaluados correctamente"
        # ==================== FASE 3.5: SHERIFF ====================
        async with cl.Step(name="🛡️ FASE 3.5: Sheriff Anti-Alucinaciones", type="tool") as step:
            evaluaciones_validadas = await cl.make_async(orchestrator._sheriff_validar)(evaluaciones, transcripcion_diarizada)
            alucinaciones = orchestrator.stats.get("alucinaciones_detectadas", 0)
            ajustes = orchestrator.stats.get("notas_ajustadas_sheriff", 0)
            if alucinaciones > 0:
                step.output = f"⚠️ {alucinaciones} alucinaciones detectadas\n🔧 {ajustes} notas ajustadas"
            else:
                step.output = "✅ Todas las evidencias verificadas (0 alucinaciones)"
        # ==================== FASE 4: SÍNTESIS ====================
        async with cl.Step(name="🎨 FASE 4: Síntesis y generación de reporte", type="tool") as step:
            try:
                reporte = await cl.make_async(orchestrator._sintetizar_evaluaciones)(
                    evaluaciones_validadas,
                    transcripcion_diarizada,
                    asesor_confirmado,
                    resumen_contextual
                )
                reporte["meta"]["stats_optimizacion"] = orchestrator.stats
                reporte["datos_oportunidad"] = cl.user_session.get("datos_oportunidad")
                # Cargar transcripción + bloques en el chat handler para consultas posteriores
                _chat_handler = cl.user_session.get("chat_handler")
                if _chat_handler is None:
                    _chat_handler = ChatHandler()
                    cl.user_session.set("chat_handler", _chat_handler)
                _chat_handler.cargar_contexto_entrevista(
                    transcripcion_diarizada,
                    reporte.get("evaluacion_por_bloques", []),
                )
                step.output = "✅ Reporte JSON generado"
            except Exception as e:
                step.output = f"❌ Error en síntesis: {e}"
                return
        # ==================== RESULTADOS ====================
        cal_global = reporte.get('calificacion_global', 'N/A')
        # Determinar emoji según calificación ordinal
        EMOJI_CAL = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}
        emoji_nota = EMOJI_CAL.get(cal_global, "⚪")
        resultado_msg = f"""# 📊 Resultados de la Evaluación
---
## {emoji_nota} Calificación Global: **{cal_global}**
**Asesor:** {reporte['asesor']}
**Perfil Lead:** {reporte['resumen_contextual'].get('perfil_lead', 'N/A')}
---
## 📈 Evaluación por Bloques
"""
        for bloque in reporte['evaluacion_por_bloques']:
            cal = bloque.get('calificacion', 'N/A')
            nombre = bloque.get('bloque')
            emoji = EMOJI_CAL.get(cal, "⚪")
            resultado_msg += f"{emoji} **{nombre}**: {cal}\n"
        resultado_msg += f"""
---
## 🎯 Plan de Acción (Top 3 Áreas de Mejora)
"""
        areas_mejora = reporte['feedback_resumido']['areas_mejora'][:3]
        if areas_mejora:
            for i, area in enumerate(areas_mejora, 1):
                resultado_msg += f"{i}. {area}\n\n"
        else:
            resultado_msg += "*No hay áreas de mejora críticas detectadas*\n"
        resultado_msg += """
---
📄 **Descarga el reporte completo en PDF** más abajo 👇
"""
        await cl.Message(content=resultado_msg).send()
        # Nombre base para archivos de salida — evita MAX_PATH (260 chars) en Windows.
        # Preferencia: opportunity_id (corto y único). Fallback: stem del archivo truncado.
        _opp_id_base = cl.user_session.get("opportunity_id")
        if _opp_id_base:
            _nombre_base = _opp_id_base
        else:
            _nombre_base = Path(file.name).stem[:70].replace('.', '_')
        # ==================== GENERAR PDF ====================
        async with cl.Step(name="📄 Generando reporte PDF", type="tool") as step:
            try:
                pdf_filename = f"Reporte_{_nombre_base}_v3.pdf"
                datos_oportunidad = reporte.get("datos_oportunidad") if isinstance(reporte, dict) else None
                generar_pdf(reporte, pdf_filename, datos_oportunidad=datos_oportunidad)
                pdf_path = settings.OUTPUTS_DIR / "Reportes_PDF" / pdf_filename
                if pdf_path.exists():
                    step.output = f"✅ PDF generado: {pdf_filename}"
                    # Enviar PDF como descargable
                    await cl.Message(
                        content="📥 **Reporte PDF listo para descargar:**",
                        elements=[
                            cl.File(
                                name=pdf_filename,
                                path=str(pdf_path),
                                display="inline"
                            )
                        ]
                    ).send()
                else:
                    step.output = "⚠️ PDF no encontrado en la ruta esperada"
            except Exception as e:
                step.output = f"❌ Error generando PDF: {e}"
        # ==================== GUARDAR JSON ====================
        json_path = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{_nombre_base}_v3.json"
        json_path.parent.mkdir(exist_ok=True, parents=True)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        # ==================== REGISTRAR EN MEMORIA (NUEVO v4.0) ====================
        # Calcular tiempo antes del registro para que quede en Supabase
        _segundos_totales = int(_time.time() - _tiempo_inicio)
        _stats_evaluacion = {
            "tiempo_analisis_seg": _segundos_totales,
            "llamadas_api": orchestrator.stats.get("llamadas_api"),
        }

        async with cl.Step(name="🧠 Actualizando perfil del asesor", type="tool") as step:
            try:
                opp_id = cl.user_session.get("opportunity_id")
                _eval_id_sobrescribir = cl.user_session.get("sobreescribir_eval_id")

                if _eval_id_sobrescribir:
                    # Modo sobreescritura: UPDATE fila existente en Supabase
                    from centauro.core.database import get_database as _get_db_reg
                    _db_reg = _get_db_reg()
                    _asesor_id_reg = _db_reg.registrar_asesor(asesor_confirmado)
                    if _asesor_id_reg:
                        _pdf_path_str = str(settings.OUTPUTS_DIR / "Reportes_PDF" / f"Reporte_{_nombre_base}_v3.pdf")
                        _ok = _db_reg.actualizar_evaluacion(
                            evaluacion_id=_eval_id_sobrescribir,
                            asesor_id=_asesor_id_reg,
                            resultado_evaluacion=reporte,
                            opportunity_id=opp_id,
                            archivo_origen=file.name if file else None,
                            reporte_pdf_path=_pdf_path_str,
                            stats=_stats_evaluacion,
                        )
                        step.output = "✅ Evaluación sobreescrita en Supabase" if _ok else "⚠️ Error sobreescribiendo en Supabase"
                    else:
                        step.output = "⚠️ No se pudo resolver el asesor en Supabase"
                else:
                    # Modo normal: INSERT nueva evaluación
                    perfil = memory_manager.registrar_evaluacion(
                        nombre_asesor=asesor_confirmado,
                        resultado_evaluacion=reporte,
                        transcripcion_path=str(file_path),
                        opportunity_id=opp_id,
                        archivo_origen=file.name if file else None,
                        stats=_stats_evaluacion,
                        realizado_por=cl.user_session.get("username_activo"),
                    )
                    feedback_personalizado = perfil.obtener_feedback_personalizado()
                    step.output = f"✅ Perfil actualizado\n\n{feedback_personalizado}"
            except Exception as e:
                step.output = f"⚠️ Error actualizando perfil: {e}"

        # ==================== ESTADÍSTICAS SEMANALES ====================
        if asesor_confirmado and asesor_confirmado != "Asesor Desconocido":
            try:
                from centauro.core.database import get_database as _get_db_stats
                _db_stats = _get_db_stats()
                if _db_stats.disponible:
                    _asesor_stats_row = _db_stats.buscar_asesor(asesor_confirmado)
                    if _asesor_stats_row:
                        _stats_sem = await asyncio.get_event_loop().run_in_executor(
                            None,
                            _db_stats.obtener_stats_semana_asesor,
                            _asesor_stats_row["id"],
                            7,
                        )
                        if _stats_sem["total_entrevistas"] > 0:
                            _bloques_actuales = reporte.get("evaluacion_por_bloques", [])
                            _stats_msg = await asyncio.get_event_loop().run_in_executor(
                                None,
                                _generar_msg_stats_semana,
                                asesor_confirmado,
                                _stats_sem,
                                _bloques_actuales,
                            )
                            if _stats_msg:
                                await cl.Message(content=_stats_msg, author="Sistema").send()
            except Exception as _e_stats:
                pass  # no bloquear el flujo si falla la sección de estadísticas

        _mins_analisis = _segundos_totales // 60
        _segs_analisis = _segundos_totales % 60
        if _mins_analisis > 0:
            _duracion_str = f"{_mins_analisis} min {_segs_analisis} seg"
        else:
            _duracion_str = f"{_segs_analisis} seg"

        # Mensaje final
        await cl.Message(
            content=f"""✅ **Análisis completado**
⏱️ **Tu análisis demoró: {_duracion_str}**
📊 Estadísticas de esta evaluación:
- Llamadas API: {orchestrator.stats['llamadas_api']}
- Sheriff: {orchestrator.stats['alucinaciones_detectadas']} alucinaciones detectadas
- Modo: {orchestrator.stats['modo_ejecucion']}
💡 **Ahora puedes:**
- 🔄 Subir otra transcripción para continuar
- 💬 Preguntarme: *"¿Cuál es mi rendimiento?"*
- 📚 Consultar: *"Muéstrame ejemplos de {reporte['feedback_resumido']['areas_mejora'][0][:30] if reporte['feedback_resumido']['areas_mejora'] else 'cierre exitoso'}..."*
""",
            author="Sistema"
        ).send()
    except Exception as e:
        # Capturar cualquier error no manejado
        import traceback
        error_detallado = traceback.format_exc()
        await cl.Message(
            content=f"""❌ **Error crítico durante el procesamiento**
**Error:** {str(e)}
**Detalles técnicos:**
```
{error_detallado}
```
Por favor, verifica:
- Que el archivo .env tenga la OPENAI_API_KEY correcta
- Que todas las dependencias estén instaladas
- Que el archivo subido sea válido
""",
            author="Sistema"
        ).send()
    finally:
        cl.user_session.set("procesando_archivo", False)
        # Liberar slot de análisis si lo habíamos adquirido
        _slot = cl.user_session.get("_slot_analisis")
        if _slot:
            try:
                _slot()
            except Exception:
                pass
            cl.user_session.set("_slot_analisis", None)
if __name__ == "__main__":
    # Esto solo se ejecuta si corres directamente python app.py
    # Lo normal es usar: chainlit run app.py
    print("⚠️ Usa: chainlit run app.py -w")
