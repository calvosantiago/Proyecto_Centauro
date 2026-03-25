"""
CENTAURO v4.0 - Interfaz Chainlit
Sistema de evaluación automatizada de llamadas comerciales con chat interactivo
NUEVO en v4.0:
- Chat interactivo para consultas al RAG
- Sistema de memoria y perfiles de asesores
- Múltiples colecciones ChromaDB
Ejecutar con: chainlit run app.py -w
"""
import chainlit as cl
import asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
from centauro.core import CentauroOrchestrator
from centauro.core.chat_handler import ChatHandler
from centauro.core.memoria import memory_manager
from centauro.rag import indexar_si_necesario
from centauro.privacy import redact_pii
from centauro.reports import generar_pdf
from centauro.config import settings
from centauro.utils.validaciones import extraer_opportunity_id
from centauro.auth import autenticar
import json
# Importar funciones de lectura desde main.py (raíz del proyecto)
from main import leer_word, limpiar_formato_vtt


# ---------------------------------------------------------------------------
# AUTENTICACIÓN — Chainlit invoca este callback en cada intento de login
# ---------------------------------------------------------------------------

@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    """
    Verifica credenciales contra centauro_users.json.
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
    from centauro.llm_client import _append_cost_row
    coste = duracion_seg * ASSEMBLYAI_COST_PER_SECOND
    now = datetime.datetime.now()
    row = {
        "Timestamp": now.isoformat(timespec="seconds"),
        "Fecha": now.strftime("%Y-%m-%d"),
        "Hora": now.strftime("%H:%M:%S"),
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


def _transcribir_con_assemblyai(audio_path: Path, api_key: str, referencia: str = "") -> str:
    """
    Transcribe y diariza el audio usando AssemblyAI.
    Devuelve texto en formato [Speaker_A]: texto / [Speaker_B]: texto
    que el DiarizationAgent reconoce y mapea a ASESOR/LEAD por contenido.
    """
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
        rol = app_user.metadata.get("rol", "asesor")
        nombre_del_login = app_user.metadata.get("nombre_completo")

        if rol == "asesor" and nombre_del_login:
            # Asesor → su nombre se pre-carga: sus evaluaciones son siempre suyas
            cl.user_session.set("nombre_asesor", nombre_del_login)
            cl.user_session.set("nombre_asesor_login", nombre_del_login)
        # admin/jefe → NO pre-cargar: evaluarán a cualquier asesor del equipo
        cl.user_session.set("rol_usuario", rol)

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
            respuesta = await asyncio.get_event_loop().run_in_executor(
                None, chat_handler.procesar_consulta, pregunta, nombre_asesor
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
    # Capturar texto del usuario como contexto adicional
    # Si el usuario escribe texto junto con el archivo, se usa como contexto
    contexto_usuario = message.content.strip() if message.content and message.content.strip() else None

    # Detectar si el usuario especificó el nombre del asesor explícitamente en el mensaje
    nombre_especificado_en_mensaje = None
    if contexto_usuario:
        import re
        # ── Patrón 1: formato explícito "Asesor: Nombre Apellido" ──────────
        patron_nombre = re.search(
            r'(?:asesor|nombre\s+asesor?|advisor)\s*[:=]\s*'
            r'([A-ZÁÉÍÓÚÜÑa-záéíóúüñ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ][a-záéíóúüñ]+)+)',
            contexto_usuario,
            re.IGNORECASE
        )
        if patron_nombre:
            nombre_especificado_en_mensaje = patron_nombre.group(1).strip().title()
            # Limpiar esa parte del contexto para no contaminar los prompts de los agentes
            contexto_usuario = re.sub(
                r'(?:asesor|nombre\s+asesor?|advisor)\s*[:=]\s*[^\n,;]+[,;\n]?\s*',
                '',
                contexto_usuario,
                flags=re.IGNORECASE
            ).strip() or None

        # ── Patrón 2 (fallback): nombre natural en el mensaje ──────────────
        # Cubre: "se llama Yanet de la Torre", "llamada de Juan Pérez",
        # "es de María García", "evalúa a Juan Pérez", "Pedro Martínez,", etc.
        # Soporta apellidos compuestos: "de la Torre", "del Valle", "van der Berg"
        if not nombre_especificado_en_mensaje and contexto_usuario:
            from centauro.core.gestion_asesores import gestion_asesores as _ga_msg
            # Núcleo de nombre: PrimeraPalabra + opcionalmente partícula + más palabras
            _NOM = (
                r'[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+'                             # Nombre/apellido (mayúscula)
                r'(?:\s+(?:de\s+(?:la\s+|los\s+|las\s+|el\s+)?'        # partícula "de [la/los...]"
                r'|del\s+|la\s+|van\s+|von\s+)?'                        # o "del/la/van/von"
                r'[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3}'                       # + siguiente palabra
            )
            patrones_naturales = [
                # "se llama / llama Nombre [de la] Apellido" (NUEVO)
                r'\bllama\s+(' + _NOM + r')',
                # "de Nombre [de la] Apellido"
                r'\bde\s+(' + _NOM + r')',
                # "a Nombre Apellido" (evalúa a Juan Pérez)
                r'\ba\s+(' + _NOM + r')',
                # "es Nombre Apellido"
                r'\bes\s+(' + _NOM + r')',
                # Nombre Apellido al inicio del mensaje (sin preposición)
                r'^(' + _NOM + r')[,\s]',
            ]
            for pat in patrones_naturales:
                m = re.search(pat, contexto_usuario, re.IGNORECASE)
                if m:
                    candidato = m.group(1).strip()
                    if _ga_msg._es_nombre_valido(candidato):
                        nombre_especificado_en_mensaje = candidato.title()
                        break

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
            return
    except ImportError:
        # Si no existe el módulo de validaciones, continuar sin validar
        pass
    # ===============================================================================
    # Usar el nombre original del archivo para detectar el tipo (file_path puede ser un UUID sin extensión)
    es_multimedia = Path(file.name).suffix.lower() in ('.mp4', '.mp3')

    # ── Pregunta anticipada de asesor (solo multimedia sin nombre ya conocido) ──
    # Se hace ANTES de transcribir para no tener al usuario esperando sin actividad
    nombre_asesor_login = cl.user_session.get("nombre_asesor_login")
    if es_multimedia and not nombre_asesor_login and not nombre_especificado_en_mensaje:
        from centauro.core.gestion_asesores import gestion_asesores as _ga_pre
        sugerencias_pre = _ga_pre.asesores_conocidos[:5] if _ga_pre.asesores_conocidos else []
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
                sugerencias = gestion_asesores.asesores_conocidos[:5] if gestion_asesores.asesores_conocidos else []
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
        # Mostrar confirmación
        await cl.Message(content=f"✅ **Asesor confirmado:** {asesor_confirmado}").send()
        # Guardar en sesión
        cl.user_session.set("nombre_asesor", asesor_confirmado)

        # ==================== OPPORTUNITY ID ====================
        opp_id = extraer_opportunity_id(file.name) if file else None
        if opp_id:
            await cl.Message(content=f"🔗 **Opportunity ID detectado:** `{opp_id}`").send()
        else:
            try:
                opp_respuesta = await cl.AskUserMessage(
                    content=(
                        "🔗 **¿Tienes el ID de oportunidad de esta entrevista?**\n"
                        "Escríbelo (ej: `2021-002579270`) o escribe **no** para continuar sin él."
                    ),
                    timeout=30
                ).send()
                if opp_respuesta:
                    texto = opp_respuesta.get("output", "").strip()
                    if texto.lower() not in ("no", "n", "-", ""):
                        opp_id = texto
                        await cl.Message(content=f"✅ **Opportunity ID guardado:** `{opp_id}`").send()
                    else:
                        await cl.Message(content="⏭️ Continuando sin Opportunity ID.").send()
            except Exception:
                pass  # Timeout o error → continuar sin ID
        cl.user_session.set("opportunity_id", opp_id)
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
        # ==================== GENERAR PDF ====================
        async with cl.Step(name="📄 Generando reporte PDF", type="tool") as step:
            try:
                pdf_filename = f"Reporte_{file.name.replace('.', '_')}_v3.pdf"
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
        json_path = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{file.name.replace('.', '_')}_v3.json"
        json_path.parent.mkdir(exist_ok=True, parents=True)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        # ==================== REGISTRAR EN MEMORIA (NUEVO v4.0) ====================
        async with cl.Step(name="🧠 Actualizando perfil del asesor", type="tool") as step:
            try:
                opp_id = cl.user_session.get("opportunity_id")
                perfil = memory_manager.registrar_evaluacion(
                    nombre_asesor=asesor_confirmado,
                    resultado_evaluacion=reporte,
                    transcripcion_path=str(file_path),
                    opportunity_id=opp_id,
                    archivo_origen=file.name if file else None,
                )
                # Obtener feedback personalizado
                feedback_personalizado = perfil.obtener_feedback_personalizado()
                step.output = f"✅ Perfil actualizado\n\n{feedback_personalizado}"
                # Ya está guardado en sesión desde la confirmación
                # cl.user_session.set("nombre_asesor", asesor_confirmado)
            except Exception as e:
                step.output = f"⚠️ Error actualizando perfil: {e}"
        # Calcular tiempo total del análisis
        _segundos_totales = int(_time.time() - _tiempo_inicio)
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
if __name__ == "__main__":
    # Esto solo se ejecuta si corres directamente python app.py
    # Lo normal es usar: chainlit run app.py
    print("⚠️ Usa: chainlit run app.py -w")
