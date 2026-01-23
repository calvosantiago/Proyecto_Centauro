"""
CENTAURO v3.0 - Interfaz Chainlit
Sistema de evaluación automatizada de llamadas comerciales

Ejecutar con: chainlit run app.py -w
"""
import chainlit as cl
from pathlib import Path
from centauro.core import CentauroOrchestrator
from centauro.rag import indexar_documentacion
from centauro.privacy import redact_pii
from centauro.reports import generar_pdf
from centauro.config import settings
import json


@cl.on_chat_start
async def start():
    """Inicialización cuando el usuario conecta"""

    # Mensaje de bienvenida
    welcome_msg = """# 🦄 Bienvenido a **Centauro v3.0**

Sistema de evaluación automatizada de llamadas comerciales con **IA Multi-Agente**.

---

## 📤 ¿Cómo usarlo?

1. **Usa el botón 📎 (clip) de abajo** o **arrastra el archivo** aquí
2. Formatos: `.txt`, `.vtt` o `.docx`
3. Espera 1-2 minutos mientras analiza
4. Descarga el reporte PDF completo

---

## 🎯 ¿Qué evalúa Centauro?

✅ **6 Bloques de Venta Consultiva:**
- 🔍 Investigación (Apertura + Detección)
- 🎯 Propuesta de Valor
- 💰 Admisión y Propuesta Económica
- 🛡️ Manejo de Objeciones
- 🎬 Cierre y Próximos Pasos
- 🎭 Estilo y Comunicación

---

**🤖 Tecnología:** Multi-Agente Híbrido + Sheriff Anti-Alucinaciones + RAG Dinámico

👇 **Usa el botón 📎 de abajo para adjuntar tu archivo** 👇
"""

    await cl.Message(content=welcome_msg).send()

    # Indexar manuales en background
    async with cl.Step(name="📚 Inicializando base de conocimiento", type="tool") as step:
        try:
            indexar_documentacion()
            step.output = "✅ Manuales OBS indexados correctamente"
        except Exception as e:
            step.output = f"⚠️ Error en indexación (continuará sin RAG): {e}"

    # Guardar estado en sesión
    cl.user_session.set("ready", True)

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


@cl.action_callback("process_file")
async def process_file_action(action: cl.Action):
    """Callback para procesar archivos adjuntos"""
    await cl.Message(content="📁 Procesando archivo...").send()


@cl.on_message
async def main(message: cl.Message):
    """Procesar transcripciones subidas"""

    # Verificar si hay archivos adjuntos
    files = [file for file in message.elements if isinstance(file, cl.File)] if message.elements else []

    if not files:
        await cl.Message(
            content="⚠️ **Por favor, sube un archivo de transcripción**\n\n"
                    "📎 Usa el botón de clip (📎) en la barra inferior\n"
                    "Formatos soportados: `.txt`, `.vtt`, `.docx`"
        ).send()
        return

    # Obtener archivo
    file = files[0]
    file_path = Path(file.path)

    await cl.Message(
        content=f"📁 Procesando: **{file.name}**\n\nEsto puede tardar 1-2 minutos..."
    ).send()

    # Leer contenido según extensión
    try:
        if file_path.suffix.lower() == '.docx':
            from centauro.main import leer_word
            texto_crudo = leer_word(file_path)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                texto_crudo = f.read()

            if file_path.suffix.lower() == '.vtt':
                from centauro.main import limpiar_formato_vtt
                texto_crudo = limpiar_formato_vtt(texto_crudo)

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

        diarization_agent = DiarizationAgent(nombre_asesor=file.name)
        transcripcion_diarizada = diarization_agent.diarizar(texto_protegido, file.name)

        asesor_detectado = diarization_agent.asesor_detectado or file.name

        num_lineas = len([l for l in transcripcion_diarizada.split('\n') if l.strip()])
        step.output = f"✅ Transcripción diarizada\n\n📊 {num_lineas} líneas procesadas\n👤 Asesor: **{asesor_detectado}**"

    # ==================== FASE 2: EXTRACCIÓN DE TEMAS ====================
    async with cl.Step(name="🧠 FASE 2: Extracción de temas (RAG Dinámico)", type="tool") as step:
        try:
            cache_key = file.name
            temas = orchestrator.rag_agent.extraer_temas_llamada(transcripcion_diarizada, cache_key)

            if temas and len(temas) > 0:
                temas_str = ", ".join(temas[:8])
                step.output = f"✅ Temas identificados:\n\n🎯 {temas_str}"
            else:
                step.output = "✅ Análisis de contexto completado"
        except Exception as e:
            step.output = f"⚠️ Error en extracción de temas: {e}\n\n(Continuará sin RAG dinámico)"

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
                        resultado = agente.evaluate(extracto, ctx)

                    elif bloque_nombre == "Proceso de Admisión y Propuesta Económica":
                        from centauro.agents import AdmisionEconomicaAgent
                        ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                        agente = AdmisionEconomicaAgent()
                        resultado = agente.evaluate(transcripcion_diarizada, ctx)

                    elif bloque_nombre == "Manejo de objeciones":
                        from centauro.agents import ObjecionesAgent
                        ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                        agente = ObjecionesAgent()
                        resultado = agente.evaluate(transcripcion_diarizada, ctx)

                    elif bloque_nombre == "Cierre y próximos pasos":
                        from centauro.agents import CierreAgent
                        ctx = orchestrator.rag_agent.buscar_contexto_para_bloque(bloque_nombre, transcripcion_diarizada, file.name)
                        agente = CierreAgent()
                        resultado = agente.evaluate(transcripcion_diarizada, ctx)

                    evaluaciones.append(resultado.to_dict())
                    nota = resultado.puntuacion_1_5 if resultado.puntuacion_1_5 else "N/A"
                    sub_step.output = f"✅ Evaluado: **{nota}/5**"

                except Exception as e:
                    sub_step.output = f"❌ Error: {e}"

        # BLOQUES SECUNDARIOS (Batch)
        async with cl.Step(name="📦 Propuesta Valor + Estilo (Batch)", type="run") as sub_step:
            try:
                evals_secundarias = orchestrator._evaluar_bloques_secundarios(transcripcion_diarizada, file.name)
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
                asesor_detectado,
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

    # Mensaje final
    await cl.Message(
        content=f"""✅ **Análisis completado**

📊 Estadísticas:
- Llamadas API: {orchestrator.stats['llamadas_api']}
- Sheriff: {orchestrator.stats['alucinaciones_detectadas']} alucinaciones detectadas
- Modo: {orchestrator.stats['modo_ejecucion']}

🔄 Puedes subir otra transcripción para continuar.
""",
        author="Sistema"
    ).send()


if __name__ == "__main__":
    # Esto solo se ejecuta si corres directamente python app.py
    # Lo normal es usar: chainlit run app.py
    print("⚠️ Usa: chainlit run app.py -w")
