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
import json
# Importar funciones de lectura desde main.py (raíz del proyecto)
from main import leer_word, limpiar_formato_vtt

# ---------------------------------------------------------------------------
# Transcripción de audio/vídeo (MP4 → ffmpeg → MP3 → Groq Whisper)
# ---------------------------------------------------------------------------

def _procesar_archivo_multimedia(file_path: Path, original_name: str = None) -> str:
    """
    Extrae texto de un archivo MP4 o MP3 usando Groq Whisper.
    - MP4: extrae audio con ffmpeg (32kbps/mono/16kHz) y luego transcribe.
    - MP3: transcribe directamente.
    Función síncrona pensada para usar con cl.make_async().

    original_name: nombre original del archivo subido (ej: "entrevista.mp3").
    Se usa para que la API de Groq reconozca el formato correctamente,
    ya que Chainlit puede guardar el fichero con un UUID como nombre.
    """
    import os
    import subprocess
    import tempfile
    from groq import Groq
    from centauro.tools.whisper_transcribe import texto_de_segmentos, WHISPER_MODEL

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
        # Usar directorio temporal del sistema para evitar problemas con rutas
        # con espacios (como el directorio de Chainlit en este entorno)
        mp3_tmp = Path(tempfile.gettempdir()) / f"centauro_{file_path.stem}.mp3"
        comando = [
            str(FFMPEG_PATH),
            "-i", str(file_path),
            "-vn",                    # sin vídeo
            "-c:a", "libmp3lame",     # codec MP3
            "-b:a", "32k",            # bitrate (suficiente para voz)
            "-ac", "1",               # mono
            "-ar", "16000",           # 16 kHz (Whisper solo necesita hasta 16 kHz)
            "-y",                     # sobreescribir sin preguntar
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

    # Transcribir con Groq Whisper
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY no encontrada en .env\n"
            "Añade tu clave Groq para procesar archivos de audio/vídeo."
        )

    client = Groq(api_key=api_key)

    # Nombre que se envía a la API: Groq necesita la extensión para reconocer el formato.
    # Para MP4 ya convertido a MP3, ajustar extensión.
    if suffix == '.mp4':
        nombre_api = (Path(original_name).stem if original_name else file_path.stem) + ".mp3"
    else:
        nombre_api = original_name or audio_path.name

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=(nombre_api, f),   # Nombre explícito para que Groq reconozca el formato
            response_format="verbose_json",
            language="es",
        )

    segmentos = getattr(response, "segments", [])
    texto = texto_de_segmentos(segmentos)
    if not texto:
        texto = getattr(response, "text", "").strip()

    return texto


@cl.on_chat_start
async def start():
    """Inicialización cuando el usuario conecta"""
    # Verificar si ya se mostró el mensaje de bienvenida en esta sesión
    already_welcomed = cl.user_session.get("welcomed", False)
    # Mensaje de bienvenida (solo se muestra la primera vez)
    if not already_welcomed:
        welcome_msg = """#  Bienvenido a **Centauro v4.0**
Sistema de evaluación automatizada + **Chat Interactivo** con IA Multi-Agente.
---
## 💬 **NUEVO: Modo Chat Interactivo**
Ahora puedes **preguntar directamente** a Centauro:
**Ejemplos de preguntas:**
- *"¿Cómo debería hacer una buena apertura?"*
- *"Muéstrame ejemplos de cierre exitoso"*
- *"¿Cuál es mi rendimiento histórico?"* (si has sido evaluado)
- *"Dame estadísticas del equipo"*
**Solo escribe tu pregunta abajo** 👇 y presiona Enter.
---
## 📤 **Modo Evaluación de Llamadas**
1. **Usa el botón 📎 (clip)** o **arrastra tu archivo**
2. Formatos: `.txt`, `.vtt`, `.docx`, `.mp3`, `.mp4`
3. **NUEVO:** Puedes escribir contexto junto al archivo (info del lead, programa, etc.)
4. Espera 1-2 minutos
5. Descarga reporte PDF completo
---
## 🎯 **¿Qué evalúa Centauro?**
✅ **6 Bloques de Venta Consultiva:**
- 🔍 Investigación • 🎯 Propuesta de Valor
- 💰 Admisión • 🛡️ Objeciones
- 🎬 Cierre • 🎭 Estilo
**🆕 Sistema de Memoria:** Cada evaluación mejora a Centauro y trackea tu progreso.
---
**🤖 Tecnología v4.0:**
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
        # Procesar pregunta
        await cl.Message(content="🤔 Buscando en la base de conocimiento...").send()
        try:
            # TODO: Detectar nombre de asesor si pregunta por su perfil
            # Por ahora, intentar extraer de la sesión o usar None
            nombre_asesor = cl.user_session.get("nombre_asesor", None)
            respuesta = chat_handler.procesar_consulta(pregunta, nombre_asesor)
            await cl.Message(content=respuesta).send()
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
    # NUEVO: Capturar texto del usuario como contexto adicional
    # Si el usuario escribe texto junto con el archivo, se usa como contexto
    contexto_usuario = message.content.strip() if message.content and message.content.strip() else None
    if contexto_usuario:
        await cl.Message(
            content=f"📝 **Contexto del usuario capturado:** Se tendrá en cuenta durante la evaluación."
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
    tiempo_estimado = "5-10 minutos (transcripción + análisis)" if es_multimedia else "1-2 minutos"
    await cl.Message(
        content=f"📁 Procesando: **{file.name}**\n\nEsto puede tardar {tiempo_estimado}..."
    ).send()
    # Leer contenido según extensión
    # NOTA: NO limpiamos VTT aquí - el agente de diarización necesita
    # el texto crudo para detectar UUIDs de speakers
    try:
        if Path(file.name).suffix.lower() == '.docx':
            texto_crudo = leer_word(file_path)
        elif es_multimedia:
            # MP4 o MP3: extraer audio (si MP4) y transcribir con Groq Whisper
            async with cl.Step(name="🎙️ Transcribiendo audio con Groq Whisper", type="tool") as step:
                if Path(file.name).suffix.lower() == '.mp4':
                    step.output = "⏳ Extrayendo audio con ffmpeg..."
                else:
                    step.output = "⏳ Enviando a Groq Whisper..."
                # Pasar file.name para que la API de Groq reconozca el formato correctamente
                texto_crudo = await cl.make_async(_procesar_archivo_multimedia)(file_path, file.name)
                num_chars = len(texto_crudo) if texto_crudo else 0
                step.output = f"✅ Transcripción completada ({num_chars} caracteres)"
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
            # Si aún no tenemos un nombre válido, preguntar al usuario
            if not asesor_detectado_inicial or not gestion_asesores._es_nombre_valido(asesor_detectado_inicial):
                step.output += "\n\n⚠️ No se pudo detectar el nombre del asesor automáticamente"
        # ==================== CONFIRMACIÓN DE ASESOR ====================
        # Validar y normalizar nombre del asesor
        asesor_confirmado = None
        # Intentar extraer nombre del contexto_usuario si no se detectó
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
                # Existe uno muy similar, preguntar cuál usar (timeout corto)
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
                    if respuesta == "1":
                        asesor_confirmado = nombre_existente
                    elif respuesta == "2":
                        asesor_confirmado = nombre_norm
                    else:
                        try:
                            asesor_confirmado = gestion_asesores.obtener_nombre_canonico(respuesta)
                        except ValueError:
                            await cl.Message(content=f"⚠️ Nombre inválido: '{respuesta}'. Usando detectado: {nombre_norm}").send()
                            asesor_confirmado = nombre_norm
                else:
                    # Timeout, usar existente automáticamente
                    asesor_confirmado = nombre_existente
            else:
                # No hay similar, usar detectado directamente sin preguntar
                asesor_confirmado = nombre_norm
        else:
            # No se detectó nombre válido — preguntar solo si no hay asesores conocidos con sugerencias
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
                    try:
                        asesor_confirmado = gestion_asesores.obtener_nombre_canonico(nombre_manual)
                    except ValueError as e:
                        await cl.Message(content=f"⚠️ Nombre no reconocido: '{nombre_manual}'. Usando como está.").send()
                        asesor_confirmado = nombre_manual.strip().title()
            else:
                # Timeout → continuar sin bloquear
                asesor_confirmado = "Asesor Desconocido"
        # Mostrar confirmación
        await cl.Message(content=f"✅ **Asesor confirmado:** {asesor_confirmado}").send()
        # Guardar en sesión
        cl.user_session.set("nombre_asesor", asesor_confirmado)
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
                step.output = f"⚠️ Error extrayendo perfil: {e}"
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
                    evals_secundarias = await cl.make_async(orchestrator._evaluar_bloques_secundarios)(transcripcion_diarizada, file.name, contexto_usuario)
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
**Perfil Lead:** {reporte['resumen_contextual'].get('perfil_lead', 'N/A')[:80]}...
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
                # Limitar longitud para legibilidad
                area_corta = area[:150] + "..." if len(area) > 150 else area
                resultado_msg += f"{i}. {area_corta}\n\n"
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
                generar_pdf(reporte, pdf_filename)
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
                # Convertir evaluaciones a formato dict
                evaluaciones_dict = {
                    e['bloque']: e for e in evaluaciones_validadas
                }
                # Registrar evaluación
                perfil = memory_manager.registrar_evaluacion(
                    nombre_asesor=asesor_confirmado,
                    resultado_evaluacion=evaluaciones_dict,
                    transcripcion_path=str(file_path)
                )
                # Obtener feedback personalizado
                feedback_personalizado = perfil.obtener_feedback_personalizado()
                step.output = f"✅ Perfil actualizado\n\n{feedback_personalizado}"
                # Ya está guardado en sesión desde la confirmación
                # cl.user_session.set("nombre_asesor", asesor_confirmado)
            except Exception as e:
                step.output = f"⚠️ Error actualizando perfil: {e}"
        # Mensaje final
        await cl.Message(
            content=f"""✅ **Análisis completado**
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
