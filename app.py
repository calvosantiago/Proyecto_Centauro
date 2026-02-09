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
from pathlib import Path
from centauro.core import CentauroOrchestrator
from centauro.core.chat_handler import ChatHandler
from centauro.core.memoria import memory_manager
from centauro.rag import indexar_documentacion
from centauro.privacy import redact_pii
from centauro.reports import generar_pdf
from centauro.config import settings
import json

# Importar funciones de lectura desde main.py (raíz del proyecto)
from main import leer_word, limpiar_formato_vtt


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
2. Formatos: `.txt`, `.vtt` o `.docx`
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
        # Indexar manuales en background (solo si está vacío)
        async with cl.Step(name="📚 Inicializando base de conocimiento", type="tool") as step:
            try:
                from centauro.rag import collection_manuales, collection_buenas_practicas

                # Verificar si ya está indexado
                total_manuales = collection_manuales.count()
                total_buenas_practicas = collection_buenas_practicas.count()
                total_docs = total_manuales + total_buenas_practicas

                if total_docs == 0:
                    # Primera vez, indexar todo
                    indexar_documentacion()
                    step.output = "✅ Base de conocimiento indexada correctamente"
                else:
                    # Ya está indexado, solo informar
                    step.output = f"✅ Base de conocimiento lista ({total_manuales} manuales + {total_buenas_practicas} buenas prácticas)"
            except Exception as e:
                step.output = f"⚠️ Error en indexación (continuará sin RAG): {e}"

        # Configurar settings para permitir archivos
        await cl.ChatSettings(
            [
                cl.input_widget.TextInput(
                    id="file_upload_info",
                    label="ℹ️ Usa el botón 📎 para adjuntar archivos",
                    initial="Formatos: .txt, .vtt, .docx"
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

    # Verificar si hay archivos adjuntos
    files = [file for file in message.elements if isinstance(file, cl.File)] if message.elements else []

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
                    "📎 O usa el botón de clip para adjuntar transcripción (.txt, .vtt, .docx)"
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

    await cl.Message(
        content=f"📁 Procesando: **{file.name}**\n\nEsto puede tardar 1-2 minutos..."
    ).send()

    # Leer contenido según extensión
    # NOTA: NO limpiamos VTT aquí - el agente de diarización necesita
    # el texto crudo para detectar UUIDs de speakers
    try:
        if file_path.suffix.lower() == '.docx':
            texto_crudo = leer_word(file_path)
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
            transcripcion_diarizada = diarization_agent.diarizar(texto_protegido, file.name)

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

        if asesor_detectado_inicial and gestion_asesores._es_nombre_valido(asesor_detectado_inicial):
            # Buscar si existe uno similar
            resultado_validacion = gestion_asesores.validar_y_normalizar(asesor_detectado_inicial)
            nombre_norm, nombre_existente, score = resultado_validacion

            if nombre_existente and score >= 85:
                # Existe uno muy similar, preguntar cuál usar
                res = await cl.AskUserMessage(
                    content=f"👤 **Confirmación de asesor**\n\n"
                            f"Detectado: **{nombre_norm}**\n"
                            f"Existe perfil similar: **{nombre_existente}** (similitud: {score}%)\n\n"
                            f"¿Cuál es correcto?\n"
                            f"1️⃣ Usar perfil existente: **{nombre_existente}**\n"
                            f"2️⃣ Crear nuevo perfil: **{nombre_norm}**\n"
                            f"3️⃣ Escribir nombre manualmente\n\n"
                            f"Responde: **1**, **2** o escribe el nombre correcto",
                    timeout=60
                ).send()

                if res and res.get("output"):
                    respuesta = res["output"].strip()
                    if respuesta == "1":
                        asesor_confirmado = nombre_existente
                    elif respuesta == "2":
                        asesor_confirmado = nombre_norm
                    else:
                        # Usuario escribió nombre manualmente
                        try:
                            asesor_confirmado = gestion_asesores.obtener_nombre_canonico(respuesta)
                        except ValueError:
                            await cl.Message(content=f"⚠️ Nombre inválido: '{respuesta}'. Usando detectado: {nombre_norm}").send()
                            asesor_confirmado = nombre_norm
                else:
                    # Timeout, usar existente
                    asesor_confirmado = nombre_existente
            else:
                # No hay similar, usar detectado
                asesor_confirmado = nombre_norm
        else:
            # No se detectó nombre válido, preguntar
            sugerencias = gestion_asesores.asesores_conocidos[:5] if gestion_asesores.asesores_conocidos else []

            sugerencias_texto = ""
            if sugerencias:
                sugerencias_texto = "\n\n**Asesores conocidos:**\n" + "\n".join(f"• {s}" for s in sugerencias)

            res = await cl.AskUserMessage(
                content=f"👤 **¿Quién es el asesor de esta llamada?**\n\n"
                        f"No se pudo detectar automáticamente.\n"
                        f"Por favor, escribe el nombre completo (Nombre Apellido):{sugerencias_texto}",
                timeout=120
            ).send()

            if res and res.get("output"):
                nombre_manual = res["output"].strip()
                try:
                    asesor_confirmado = gestion_asesores.obtener_nombre_canonico(nombre_manual)
                except ValueError as e:
                    await cl.Message(content=f"❌ {e}\n\nUsando 'Asesor Desconocido'").send()
                    asesor_confirmado = "Asesor Desconocido"
            else:
                asesor_confirmado = "Asesor Desconocido"

        # Mostrar confirmación
        await cl.Message(content=f"✅ **Asesor confirmado:** {asesor_confirmado}").send()

        # Guardar en sesión
        cl.user_session.set("nombre_asesor", asesor_confirmado)

        # ==================== FASE 2: EXTRACCIÓN DE TEMAS ====================
        async with cl.Step(name="🧠 FASE 2: Extracción de temas (RAG Dinámico)", type="tool") as step:
            try:
                cache_key = file.name
                temas = orchestrator.rag_agent.extraer_temas_llamada(transcripcion_diarizada, cache_key)

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
                resumen_contextual = orchestrator._extraer_resumen_contextual(transcripcion_diarizada, file.name)

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
                            ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = InvestigacionAgent()
                            resultado = agente.evaluate(extracto, ctx, contexto_usuario)

                        elif bloque_nombre == "Proceso de Admisión y Propuesta Económica":
                            from centauro.agents import AdmisionEconomicaAgent
                            ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = AdmisionEconomicaAgent()
                            resultado = agente.evaluate(transcripcion_diarizada, ctx, contexto_usuario)

                        elif bloque_nombre == "Manejo de objeciones":
                            from centauro.agents import ObjecionesAgent
                            ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = ObjecionesAgent()
                            resultado = agente.evaluate(transcripcion_diarizada, ctx, contexto_usuario)

                        elif bloque_nombre == "Cierre y próximos pasos":
                            from centauro.agents import CierreAgent
                            ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                            agente = CierreAgent()
                            resultado = agente.evaluate(transcripcion_diarizada, ctx, contexto_usuario)

                        evaluaciones.append(resultado.to_dict())
                        nota = resultado.puntuacion_1_5 if resultado.puntuacion_1_5 else "N/A"
                        sub_step.output = f"✅ Evaluado: **{nota}/5**"

                    except Exception as e:
                        sub_step.output = f"❌ Error: {e}"

            # BLOQUES SECUNDARIOS (Batch)
            async with cl.Step(name="📦 Propuesta Valor + Estilo (Batch)", type="run") as sub_step:
                try:
                    evals_secundarias = orchestrator._evaluar_bloques_secundarios(transcripcion_diarizada, file.name, contexto_usuario)
                    evaluaciones.extend(evals_secundarias)
                    sub_step.output = f"✅ 2 bloques evaluados en batch"
                except Exception as e:
                    sub_step.output = f"❌ Error: {e}"

            fase3.output = f"✅ {len(evaluaciones)} bloques evaluados correctamente"

        # ==================== FASE 3.5: SHERIFF ====================
        async with cl.Step(name="🛡️ FASE 3.5: Sheriff Anti-Alucinaciones", type="tool") as step:
            evaluaciones_validadas = orchestrator._sheriff_validar(evaluaciones, transcripcion_diarizada)

            alucinaciones = orchestrator.stats.get("alucinaciones_detectadas", 0)
            ajustes = orchestrator.stats.get("notas_ajustadas_sheriff", 0)

            if alucinaciones > 0:
                step.output = f"⚠️ {alucinaciones} alucinaciones detectadas\n🔧 {ajustes} notas ajustadas"
            else:
                step.output = "✅ Todas las evidencias verificadas (0 alucinaciones)"

        # ==================== FASE 4: SÍNTESIS ====================
        async with cl.Step(name="🎨 FASE 4: Síntesis y generación de reporte", type="tool") as step:
            try:
                reporte = orchestrator._sintetizar_evaluaciones(
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
        nota_global = reporte['puntuacion_global_1_5']

        # Determinar emoji según nota
        if nota_global >= 4.0:
            emoji_nota = "🟢"
        elif nota_global >= 3.0:
            emoji_nota = "🟡"
        else:
            emoji_nota = "🔴"

        resultado_msg = f"""# 📊 Resultados de la Evaluación

---

## {emoji_nota} Nota Global: **{nota_global}/5.0**

**Asesor:** {reporte['asesor']}
**Perfil Lead:** {reporte['resumen_contextual'].get('perfil_lead', 'N/A')[:80]}...

---

## 📈 Evaluación por Bloques

"""

        for bloque in reporte['evaluacion_por_bloques']:
            nota = bloque.get('puntuacion_1_5', 'N/A')
            nombre = bloque.get('bloque')

            if nota == 'N/A' or nota is None:
                emoji = "⚪"
                nota_str = "N/A"
            elif nota >= 4:
                emoji = "🟢"
                nota_str = f"{nota}/5"
            elif nota == 3:
                emoji = "🟡"
                nota_str = f"{nota}/5"
            else:
                emoji = "🔴"
                nota_str = f"{nota}/5"

            resultado_msg += f"{emoji} **{nombre}**: {nota_str}\n"

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
