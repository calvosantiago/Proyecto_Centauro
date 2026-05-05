"""
Orquestador del Sistema Multi-Agente v3.0 - MODO HÍBRIDO

CAMBIOS EN v3.0:
- NUEVA ESTRUCTURA: 4 bloques críticos (agentes individuales) + 2 secundarios (batch)
- BLOQUES CRÍTICOS (individual): Investigación, Admisión/Económica, Objeciones, Cierre
- BLOQUES SECUNDARIOS (batch): Propuesta Valor, Estilo
- MODO_BATCH = True  → Híbrido (producción)
- MODO_BATCH = False → Todo individual (pruebas)
- Sheriff anti-alucinaciones mantenido
- Resumen contextual del lead mantenido
"""
from typing import Dict, List
import json
import re

# Importar TODOS los agentes v3.0
from ..agents import (
    DiarizationAgent,
    InvestigacionAgent,
    PropuestaValorAgent,
    AdmisionEconomicaAgent,
    ObjecionesAgent,
    CierreAgent,
    EstiloAgent
)
from ..agents.base_agent import EvaluationResult
from .rag_dynamic import DynamicRAGAgent
from .config_agents import OptimizacionConfig
from ..llm_client import consultar_gpt
from ..config import settings
from ..privacy import redact_pii  # NUEVO: Redactar datos sensibles


class CentauroOrchestrator:
    """Orquestador v3.0 con Modo Híbrido Inteligente"""

    def __init__(self):
        self.rag_agent = DynamicRAGAgent()
        self.config = OptimizacionConfig()

        # Estadísticas de ejecución
        self.stats = {
            "llamadas_api": 0,
            "tokens_ahorrados": 0,
            "cache_hits": 0,
            "alucinaciones_detectadas": 0,
            "notas_ajustadas_sheriff": 0,
            "modo_ejecucion": self.config.get_modo_descripcion()
        }

    def analizar_entrevista_completa(self, nombre_archivo: str, texto_crudo: str, contexto_usuario: str = None, audio_features: dict = None) -> Dict:
        # Reset stats por cada evaluación (evita acumulación entre asesores en la misma sesión)
        self.stats = {
            "llamadas_api": 0,
            "tokens_ahorrados": 0,
            "cache_hits": 0,
            "alucinaciones_detectadas": 0,
            "notas_ajustadas_sheriff": 0,
            "modo_ejecucion": self.config.get_modo_descripcion()
        }
        """Pipeline completo orquestado v3.0

        Args:
            nombre_archivo: Nombre del archivo de transcripción
            texto_crudo: Texto crudo de la transcripción
            contexto_usuario: (Opcional) Contexto adicional proporcionado por el usuario.
                             Puede incluir info del lead, instrucciones especiales, etc.
                             Se pasa a todos los agentes evaluadores.
        """
        print(f"\n{'='*60}")
        print(f"🎯 CENTAURO v3.0 - MODO HÍBRIDO: {nombre_archivo}")
        print(f"{'='*60}")
        print(f"⚙️  {self.stats['modo_ejecucion']}")
        print(f"{'='*60}\n")

        # --- FASE 0: REDACCIÓN PII (PRIVACIDAD) ---
        print("📍 FASE 0: Protección de datos sensibles")
        resultado_redaccion = redact_pii(texto_crudo)
        texto_protegido = resultado_redaccion.text

        if sum(resultado_redaccion.stats.values()) > 0:
            print(f"   🛡️ Datos redactados: {dict(resultado_redaccion.stats)}")
        else:
            print("   ✓ No se detectaron datos sensibles")

        # --- ENRIQUECIMIENTO: DATOS DEL LEAD DESDE SUPABASE ---
        datos_oportunidad = None
        from centauro.utils.validaciones import extraer_opportunity_id
        opportunity_id = extraer_opportunity_id(nombre_archivo)
        if opportunity_id:
            try:
                from .database import get_database
                db = get_database()
                datos_oportunidad = db.obtener_oportunidad(opportunity_id)
                if datos_oportunidad:
                    nombre_lead = datos_oportunidad.get('nombre_lead', 'N/A')
                    pais = datos_oportunidad.get('pais', 'N/A')
                    edad = datos_oportunidad.get('edad', 'N/A')
                    programa = datos_oportunidad.get('programa', 'N/A')
                    pilar = datos_oportunidad.get('pilar', 'N/A')
                    contexto_lead = (
                        f"\n\n--- PERFIL DEL LEAD (contexto de referencia) ---\n"
                        f"Nombre: {nombre_lead}\n"
                        f"País: {pais}\n"
                        f"Edad aproximada: {edad} años\n"
                        f"Programa de interés: {programa}\n"
                        f"Pilar: {pilar}\n"
                        f"---------------------------------------------------\n"
                        f"IMPORTANTE: Si en la grabación el lead menciona datos diferentes "
                        f"(edad, situación financiera, perfil, etc.), usa SIEMPRE lo que dice "
                        f"en la grabación — eso es la realidad de la llamada. Estos datos son "
                        f"contexto de referencia, no reemplazan lo que el lead comunica en directo.\n"
                        f"Usa este perfil únicamente para entender quién es el lead y evaluar "
                        f"si el asesor adaptó su discurso a ese perfil concreto.\n"
                    )
                    contexto_usuario = (contexto_usuario or "") + contexto_lead
                    print(f"   ✅ Lead: {nombre_lead} ({pais}, {edad} años, {programa})")
                else:
                    print(f"   ℹ️ Oportunidad {opportunity_id} no encontrada en Supabase")
            except Exception as e:
                print(f"   ⚠️ No se pudo enriquecer con datos del lead: {e}")

        # --- FASE 1: DIARIZACIÓN ---
        print("\n📍 FASE 1: Diarización")
        diarization_agent = DiarizationAgent(nombre_asesor=nombre_archivo)
        transcripcion_diarizada = diarization_agent.diarizar(texto_protegido, nombre_archivo)
        asesor_detectado = diarization_agent.asesor_detectado or nombre_archivo
        self.stats["llamadas_api"] += 7

        # --- DETECCIÓN DE IDIOMA ---
        from centauro.utils.validaciones import detectar_idioma_transcripcion
        idioma_entrevista = detectar_idioma_transcripcion(transcripcion_diarizada)
        if idioma_entrevista == "en":
            print("   🌐 Entrevista detectada en INGLÉS — ajustando evaluación")
            contexto_idioma = (
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
            contexto_usuario = (contexto_usuario or "") + contexto_idioma

        # --- GUARDAR TRANSCRIPCIÓN DIARIZADA PARA DEBUG ---
        self._guardar_transcripcion_debug(nombre_archivo, transcripcion_diarizada)

        # --- FASE 2: EXTRACCIÓN DE TEMAS ---
        print("\n📍 FASE 2: Análisis de contexto")
        cache_key = nombre_archivo
        temas = self.rag_agent.extraer_temas_llamada(transcripcion_diarizada, cache_key)
        self.stats["llamadas_api"] += 1

        # --- FASE 2.5: RESUMEN CONTEXTUAL ---
        print("\n📍 FASE 2.5: Extracción de perfil del lead")
        resumen_contextual = self._extraer_resumen_contextual(transcripcion_diarizada, cache_key)
        self.stats["llamadas_api"] += 1

        # --- FASE 3: EVALUACIÓN (HÍBRIDO O INDIVIDUAL) ---
        print("\n📍 FASE 3: Evaluación por agentes")

        evaluaciones = []

        if self.config.MODO_BATCH:
            # MODO HÍBRIDO: Críticos individual + Secundarios batch
            print("\n   ⭐ BLOQUES CRÍTICOS (agentes individuales):")
            evaluaciones_criticas = self._evaluar_bloques_criticos(transcripcion_diarizada, cache_key, contexto_usuario)
            evaluaciones.extend(evaluaciones_criticas)
            self.stats["llamadas_api"] += len(self.config.BLOQUES_CRITICOS)

            print("\n   📦 BLOQUES SECUNDARIOS (batch optimizado):")
            evaluaciones_secundarias = self._evaluar_bloques_secundarios(transcripcion_diarizada, cache_key, contexto_usuario, audio_features)
            evaluaciones.extend(evaluaciones_secundarias)
            self.stats["llamadas_api"] += 1

        else:
            # MODO INDIVIDUAL: Cada agente una llamada
            print("\n   🔬 MODO PRUEBAS: Todos los agentes individual")
            evaluaciones = self._evaluar_todos_individual(transcripcion_diarizada, cache_key, contexto_usuario, audio_features)
            self.stats["llamadas_api"] += 6  # 6 agentes

        # --- FASE 3.5: SHERIFF ---
        print("\n📍 FASE 3.5: Auditoría Sheriff (anti-alucinaciones)")
        evaluaciones = self._sheriff_validar(evaluaciones, transcripcion_diarizada)

        # NOTA: El coaching ahora está integrado directamente en cada agente evaluador.
        # Los fragmentos de libros de ventas llegan vía RAG y cada agente los integra
        # orgánicamente en su recomendacion_accionable. No se necesita fase separada.

        # --- FASE 4: SÍNTESIS ---
        print("\n📍 FASE 4: Síntesis y validación")
        reporte_final = self._sintetizar_evaluaciones(
            evaluaciones,
            transcripcion_diarizada,
            asesor_detectado,
            resumen_contextual
        )
        # NOTA: _sintetizar_evaluaciones NO hace llamada LLM, es puro Python

        reporte_final["meta"]["stats_optimizacion"] = self.stats
        reporte_final["datos_oportunidad"] = datos_oportunidad

        print(f"\n{'='*60}")
        print(f"✅ COMPLETADO - Calificación: {reporte_final['calificacion_global']}")
        print(f"📊 Llamadas API: {self.stats['llamadas_api']}")
        print(f"🛡️ Sheriff: {self.stats['alucinaciones_detectadas']} alucinaciones detectadas")
        print(f"{'='*60}\n")

        return reporte_final

    # ========== DEBUG: GUARDAR TRANSCRIPCIÓN DIARIZADA ==========

    def _guardar_transcripcion_debug(self, nombre_archivo: str, transcripcion: str):
        """
        Guarda una copia de la transcripción diarizada para verificación.
        Permite confirmar que la diarización es correcta y no hay alucinaciones.
        """
        try:
            debug_dir = settings.OUTPUTS_DIR / "Input_Debug"
            debug_dir.mkdir(parents=True, exist_ok=True)

            # Nombre del archivo de debug
            nombre_limpio = nombre_archivo.replace(" ", "_").replace("/", "_")
            debug_path = debug_dir / f"{nombre_limpio}_diarizada.txt"

            # Guardar con encabezado informativo
            contenido = f"""{'='*70}
TRANSCRIPCIÓN DIARIZADA - DEBUG
{'='*70}
Archivo original: {nombre_archivo}
Fecha: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*70}

NOTA: Esta es la transcripción que los agentes evaluadores reciben.
      Verifica que la diarización (ASESOR/LEAD) sea correcta.
      Si hay errores aquí, las evaluaciones pueden ser incorrectas.

{'='*70}

{transcripcion}
"""
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(contenido)

            print(f"   📝 Debug guardado: {debug_path.name}")

        except Exception as e:
            print(f"   ⚠️ No se pudo guardar debug: {e}")

    # ========== EVALUACIÓN: BLOQUES CRÍTICOS (Individual) ==========

    def _evaluar_bloques_criticos(self, transcripcion: str, cache_key: str, contexto_usuario: str = None) -> List[Dict]:
        """
        Evalúa bloques críticos con agentes individuales especializados

        Bloques críticos (v5.1):
        1. Investigación (transcripción completa — necesita evaluar aprovechamiento posterior)
        2. Proceso de Admisión y Propuesta Económica (transcripción completa)
        3. Manejo de objeciones (transcripción completa)
        4. Cierre y próximos pasos (inicio + final via CierreAgent interno)
        """
        evaluaciones = []

        # 1. INVESTIGACIÓN (con extracto)
        print("      1️⃣ Investigación (agente individual)")
        extracto_investigacion = self.config.get_extracto("Investigación", transcripcion)
        contexto_investigacion = self.rag_agent.buscar_contexto_para_bloque("Investigación", transcripcion, cache_key)

        agente_investigacion = InvestigacionAgent()
        resultado = agente_investigacion.evaluate(extracto_investigacion, contexto_investigacion, contexto_usuario)
        evaluaciones.append(resultado.to_dict())

        # 2. PROCESO ADMISIÓN/ECONÓMICA (completo)
        print("      2️⃣ Proceso Admisión y Propuesta Económica (agente individual)")
        contexto_admision = self.rag_agent.buscar_contexto_para_bloque(
            "Proceso de Admisión y Propuesta Económica",
            transcripcion,
            cache_key
        )

        agente_admision = AdmisionEconomicaAgent()
        resultado = agente_admision.evaluate(transcripcion, contexto_admision, contexto_usuario)
        evaluaciones.append(resultado.to_dict())

        # 3. MANEJO DE OBJECIONES (completo)
        print("      3️⃣ Manejo de objeciones (agente individual)")
        contexto_objeciones = self.rag_agent.buscar_contexto_para_bloque("Manejo de objeciones", transcripcion, cache_key)

        agente_objeciones = ObjecionesAgent()
        resultado = agente_objeciones.evaluate(transcripcion, contexto_objeciones, contexto_usuario)
        evaluaciones.append(resultado.to_dict())

        # 4. CIERRE Y PRÓXIMOS PASOS (con extracto)
        print("      4️⃣ Cierre y próximos pasos (agente individual)")
        extracto_cierre = self.config.get_extracto("Cierre y próximos pasos", transcripcion)
        contexto_cierre = self.rag_agent.buscar_contexto_para_bloque("Cierre y próximos pasos", transcripcion, cache_key)

        agente_cierre = CierreAgent()
        resultado = agente_cierre.evaluate(transcripcion, contexto_cierre, contexto_usuario)  # CierreAgent maneja extracto interno
        evaluaciones.append(resultado.to_dict())

        print(f"      ✓ {len(evaluaciones)} bloques críticos evaluados")
        return evaluaciones

    # ========== EVALUACIÓN: BLOQUES SECUNDARIOS (Batch) ==========

    def _evaluar_bloques_secundarios(self, transcripcion: str, cache_key: str, contexto_usuario: str = None, audio_features: dict = None) -> List[Dict]:
        """
        Evalúa bloques secundarios en batch (1 llamada para 2 bloques)

        Bloques secundarios:
        1. Propuesta de valor Institución y Programa
        2. Estilo y comunicación

        ACTUALIZADO v4.3: Incluye ejemplos de buenas prácticas en el prompt
        ACTUALIZADO v4.4: Soporte para contexto_usuario
        """
        ctx_propuesta = self.rag_agent.buscar_contexto_para_bloque(
            "Propuesta de valor Institución y Programa",
            transcripcion,
            cache_key
        )
        ctx_estilo = self.rag_agent.buscar_contexto_para_bloque(
            "Estilo y comunicación",
            transcripcion,
            cache_key
        )

        # Buscar ejemplos de buenas prácticas para propuesta de valor
        ejemplos_bp_texto = ""
        try:
            from .rag_dynamic import buscar_contexto_dinamico
            from ..config import centauro_config

            ejemplos_pv = buscar_contexto_dinamico(
                query=f"Ejemplo de buena práctica propuesta de valor: {transcripcion[:300]}",
                collection_name="buenas_practicas",
                k=centauro_config.RAG_TOP_K_BUENAS_PRACTICAS,
                filtro_seccion="Propuesta de valor Institución y Programa"
            )
            if ejemplos_pv:
                ejemplos_bp_texto = "\n\n" + "="*80 + "\n"
                ejemplos_bp_texto += "ANCLAS DE CALIBRACION - EJEMPLOS REALES PUNTUADOS\n"
                ejemplos_bp_texto += "="*80 + "\n\n"
                ejemplos_bp_texto += "Los siguientes son extractos de entrevistas REALES evaluadas manualmente.\n"
                ejemplos_bp_texto += "USALOS PARA CALIBRAR tu evaluacion:\n"
                ejemplos_bp_texto += "1. Lee los ejemplos para entender el NIVEL DE CALIDAD de cada calificacion\n"
                ejemplos_bp_texto += "2. Evalua la conversacion por SUS PROPIOS MERITOS primero\n"
                ejemplos_bp_texto += "3. NO exijas que se parezca al ejemplo para calificar como BUENO\n\n"
                for i, ej in enumerate(ejemplos_pv, 1):
                    texto = ej.get('text', '') if isinstance(ej, dict) else str(ej)
                    if texto:
                        ejemplos_bp_texto += f"\n--- EJEMPLO DE REFERENCIA {i} ---\n{texto[:centauro_config.MAX_EJEMPLO_LENGTH_IN_PROMPT]}\n"
                ejemplos_bp_texto += "\n" + "="*80 + "\n"
                print(f"      Buenas prácticas incluidas: {len(ejemplos_pv)} ejemplos")
        except Exception as e:
            print(f"      Info: No se pudieron cargar buenas prácticas para batch: {e}")

        # Bloque de métricas de audio para el prompt de estilo (siempre presente)
        from ..tools.audio_features import formatear_metricas_para_prompt, formatear_sin_audio_para_prompt
        if audio_features and audio_features.get("disponible"):
            bloque_audio_estilo = f"\n{formatear_metricas_para_prompt(audio_features)}\n"
        else:
            bloque_audio_estilo = f"\n{formatear_sin_audio_para_prompt()}\n"

        prompt_sistema = f"""
Eres un auditor CRÍTICO que evalúa DOS bloques secundarios simultáneamente.
Debes ser RIGUROSO: MALO y MEJORABLE son calificaciones distintas con criterios concretos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOQUE A — PROPUESTA DE VALOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANUAL DE REFERENCIA:
{ctx_propuesta}
{ejemplos_bp_texto}

CHECKLIST PROPUESTA DE VALOR — responde SÍ/NO a cada pregunta:
  1. ¿Explicó con claridad qué es OBS y qué incluye el programa?
  2. ¿Enfatizó beneficios para el lead (no solo características del programa)?
  3. ¿Recuperó el FDC del lead (su motivo o necesidad más concreta revelada en la
     investigación) y lo vinculó explícitamente al programa? Mención superficial = NO.
  4. ¿Evitó afirmaciones superlativas sin argumentos ("somos los mejores") o las justificó?
  5. ¿El lead mostró interés o comprensión genuina durante o después de la propuesta?

CUENTA los NOs → "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: 3 o más NOs → calificación es MALO. Sin excepciones.
No detectes múltiples fallos graves y concluyas MEJORABLE: sería incoherente.

CRITERIOS:
🔴 MALO: Presentación confusa o desorganizada, O el lead no entiende qué se le ofrece,
   O múltiples fallos del checklist acumulados. El lead no recibe información útil.
🟡 MEJORABLE: Existe propuesta ordenada pero genérica — el asesor no recuperó el FDC
   del lead para vincular el programa a SU situación concreta. El lead escucha información
   válida pero no siente que el programa resuelve SU problema específico.
🟢 BUENO: Clara, estructurada y vincula explícitamente el FDC del lead con lo que el
   programa ofrece. El lead siente que el asesor habla de SU caso.
   Si dudas entre BUENO y MEJORABLE: ¿el asesor vinculó el FDC con el programa
   en una frase explícita? Si no hay esa vinculación directa → MEJORABLE, aunque
   haya mencionado el perfil del lead o su trabajo de pasada.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOQUE B — ESTILO Y COMUNICACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANUAL DE REFERENCIA:
{ctx_estilo}
{bloque_audio_estilo}

CHECKLIST ESTILO — responde SÍ/NO a cada pregunta:
  1. ¿El tono fue profesional y cercano (no mecánico ni inapropiado)?
  2. ¿Hubo al menos un momento de empatía o cercanía genuina?
  3. ¿El ritmo permitió al lead participar (no fue monólogo)?
  4. ¿El vocabulario fue claro y adaptado al perfil del lead?
  5. ¿El profesionalismo fue alto (sin muletillas excesivas, seguro)?

CUENTA los NOs → "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: 3 o más NOs → calificación es MALO. Sin excepciones.
Si no puedes identificar ni UNA fortaleza comunicativa REAL → también es MALO.
No detectes múltiples fallos graves y concluyas MEJORABLE: sería incoherente.

¿QUÉ NO CUENTA COMO FORTALEZA REAL?
- Hacer alguna pregunta puntual en medio de largos monólogos.
- Usar el nombre del lead una sola vez en toda la llamada.
- "El vocabulario fue claro" — claridad mínima es el estándar base, no un positivo.
Si el único positivo que puedes citar es de estas categorías → la calificación es MALO.

CRITERIOS:
🔴 MALO (dos vías posibles):
   VÍA A — Activamente dañino: tono grosero, condescendiente, o tan desorganizado que
   el lead no entiende la conversación.
   VÍA B — Sin ninguna fortaleza real: el estilo no es dañino pero falla en todos
   los frentes sin nada que rescatar. La conversación es mecánica e impersonal.
🟡 MEJORABLE: Hay al menos UNA fortaleza comunicativa real, pero el conjunto es
   insuficiente. Tono educado pero robótico, pocos momentos de empatía, pocas preguntas.
   ⚠️ REQUISITO: para ser MEJORABLE debe existir al menos UNA fortaleza real. Sin ninguna → MALO.
🟢 BUENO: El estilo genera confianza y el lead se siente cómodo participando. Hay al menos
   un momento de empatía real o cercanía genuina.
   Si dudas entre MEJORABLE y MALO: ¿puedes citar al menos UNA fortaleza comunicativa real? Si no → MALO.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGLA CRÍTICA — EVIDENCIAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TODAS las evidencias DEBEN ser CITAS LITERALES EXACTAS de la transcripción.
- Usa COPY-PASTE directo, no parafrasees
- Incluye SIEMPRE la etiqueta [ASESOR]: o [LEAD]:
- NUNCA resumas, SIEMPRE cita textual

FORMATO JSON OBLIGATORIO:
{{
  "propuesta_valor": {{
    "contador_fallos_criticos": 0,
    "calificacion": "MALO" | "MEJORABLE" | "BUENO",
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA (COPY-PASTE)...",
    "evidencias_extra": ["[ASESOR]: Otra cita EXACTA (COPY-PASTE)..."],
    "razonamiento": "4-6 líneas fluidas: ¿personalizó? ¿beneficios o características? ¿conectó con el lead? ¿por qué esa calificación? Si MALO o MEJORABLE: incluye al menos una cita literal del fallo principal.",
    "recomendacion_accionable": "Combina en un SOLO texto fluido: (1) qué mejorar, (2) UNA técnica de los libros del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 frases ejemplo adaptadas a ESTA conversación. Máx 6-8 líneas.",
    "personalizacion_detectada": true | false
  }},
  "estilo": {{
    "contador_fallos_criticos": 0,
    "calificacion": "MALO" | "MEJORABLE" | "BUENO",
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA...",
    "evidencias_extra": ["[ASESOR]: Otra cita EXACTA..."],
    "razonamiento": "4-6 líneas fluidas: tono, ritmo, empatía. ¿por qué esa calificación? Si MALO o MEJORABLE: incluye al menos una cita literal del fallo principal.",
    "recomendacion_accionable": "Combina en un SOLO texto fluido: (1) qué mejorar en estilo, (2) UNA técnica de los libros del CONTEXTO que aplique, dando 2 frases ejemplo. Máx 6-8 líneas.",
    "fortaleza_principal": "La fortaleza comunicativa real más destacada, o 'ninguna' si no existe."
  }}
}}

REGLAS PARA RECOMENDACIÓN CON COACHING:
El contexto incluye fragmentos de libros marcados como [COACHING: ...].
DEBES integrarlos en cada "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para cada bloque
- Explica POR QUÉ le ayudaría, conectando con la situación real
- Da 2 frases concretas adaptadas a ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene

⚠️ REGLAS FINALES:
- Sé decisivo: elige UNA etiqueta por bloque
- BUENO no requiere perfección, requiere personalización y conexión real con el lead
- En "recomendacion_accionable" NO repitas lo que ya hizo bien
"""

        # Incluir contexto del usuario si se proporcionó
        bloque_contexto_usuario = ""
        if contexto_usuario:
            bloque_contexto_usuario = f"""
CONTEXTO ADICIONAL DEL USUARIO:
{contexto_usuario}

INSTRUCCIÓN: Ten en cuenta este contexto al evaluar. Puede contener información sobre el lead,
el programa vendido, circunstancias especiales u otras indicaciones relevantes.
"""

        prompt_usuario = f"""{bloque_contexto_usuario}
TRANSCRIPCIÓN COMPLETA:

{transcripcion}

Evalúa los 2 bloques secundarios con CITAS LITERALES y sé CRÍTICO.
"""

        try:
            resp = consultar_gpt(prompt_sistema, prompt_usuario, f"{cache_key}_batch_secundarios")
            data = json.loads(resp)

            evaluaciones = []

            ORDEN_CAL = {"MALO": 0, "MEJORABLE": 1, "BUENO": 2}

            if "propuesta_valor" in data:
                eval_pv = data["propuesta_valor"]
                eval_pv["bloque"] = "Propuesta de valor Institución y Programa"
                eval_pv["confianza"] = 0.85
                # Tope Python: 3+ fallos críticos → MALO
                fallos_pv = eval_pv.get("contador_fallos_criticos", 0)
                cal_pv = eval_pv.get("calificacion", "MEJORABLE")
                if fallos_pv >= 3 and ORDEN_CAL.get(cal_pv, 1) > 0:
                    nota_pv = (
                        f"[Ajuste automático] Calificación bajada de {cal_pv} a MALO: "
                        f"{fallos_pv} fallos críticos en checklist de propuesta de valor."
                    )
                    eval_pv["calificacion"] = "MALO"
                    eval_pv["razonamiento"] = eval_pv.get("razonamiento", "") + f"\n\n{nota_pv}"
                    print(f"      ⚠️ Tope batch PV: {fallos_pv} fallos → MALO")
                    self.stats["notas_ajustadas_sheriff"] += 1
                evaluaciones.append(eval_pv)

            if "estilo" in data:
                eval_estilo = data["estilo"]
                eval_estilo["bloque"] = "Estilo y comunicación"
                eval_estilo["confianza"] = 0.85
                # Tope Python A: 3+ fallos críticos → MALO
                fallos_est = eval_estilo.get("contador_fallos_criticos", 0)
                cal_est = eval_estilo.get("calificacion", "MEJORABLE")
                if fallos_est >= 3 and ORDEN_CAL.get(cal_est, 1) > 0:
                    nota_est = (
                        f"[Ajuste automático] Calificación bajada de {cal_est} a MALO: "
                        f"{fallos_est} fallos críticos en checklist de estilo."
                    )
                    eval_estilo["calificacion"] = "MALO"
                    eval_estilo["razonamiento"] = eval_estilo.get("razonamiento", "") + f"\n\n{nota_est}"
                    print(f"      ⚠️ Tope batch Estilo A: {fallos_est} fallos → MALO")
                    self.stats["notas_ajustadas_sheriff"] += 1
                    cal_est = "MALO"
                # Tope Python B: MEJORABLE sin fortaleza real → MALO
                if cal_est == "MEJORABLE":
                    fortaleza = str(eval_estilo.get("fortaleza_principal", "") or "").strip().lower()
                    sin_fortaleza = fortaleza in ("", "ninguna", "no identificada", "n/a", "-", "no hay", "ninguno")
                    if sin_fortaleza:
                        nota_b = (
                            "[Ajuste automático] Calificación bajada de MEJORABLE a MALO: "
                            "no se identificó ninguna fortaleza comunicativa real."
                        )
                        eval_estilo["calificacion"] = "MALO"
                        eval_estilo["razonamiento"] = eval_estilo.get("razonamiento", "") + f"\n\n{nota_b}"
                        print("      ⚠️ Tope batch Estilo B: sin fortaleza → MALO")
                        self.stats["notas_ajustadas_sheriff"] += 1
                meta_estilo = eval_estilo.setdefault("metadata", {})
                meta_estilo["audio_features"] = audio_features
                try:
                    from centauro.tools.audio_features import calcular_ratio_habla_diarizada as _crh
                    _ratio = _crh(transcripcion)
                    meta_estilo["pct_asesor"] = _ratio.get("pct_asesor")
                    meta_estilo["pct_lead"] = _ratio.get("pct_lead")
                except Exception:
                    pass
                evaluaciones.append(eval_estilo)

            print(f"      ✓ 2 bloques secundarios en 1 llamada batch")
            return evaluaciones

        except Exception as e:
            print(f"   ⚠️ Error en batch secundarios: {e}")
            return []

    # ========== EVALUACIÓN: TODO INDIVIDUAL (Modo Pruebas) ==========

    def _evaluar_todos_individual(self, transcripcion: str, cache_key: str, contexto_usuario: str = None, audio_features: dict = None) -> List[Dict]:
        """
        Evalúa TODOS los bloques con agentes individuales
        Solo se usa cuando MODO_BATCH = False (pruebas)
        """
        evaluaciones = []

        # 1. Investigación
        print("      1️⃣ Investigación")
        extracto_inv = self.config.get_extracto("Investigación", transcripcion)
        ctx_inv = self.rag_agent.buscar_contexto_para_bloque("Investigación", transcripcion, cache_key)
        agente = InvestigacionAgent()
        evaluaciones.append(agente.evaluate(extracto_inv, ctx_inv, contexto_usuario).to_dict())

        # 2. Propuesta Valor
        print("      2️⃣ Propuesta de valor Institución y Programa")
        ctx_pv = self.rag_agent.buscar_contexto_para_bloque("Propuesta de valor Institución y Programa", transcripcion, cache_key)
        agente = PropuestaValorAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_pv, contexto_usuario).to_dict())

        # 3. Admisión/Económica
        print("      3️⃣ Proceso Admisión y Propuesta Económica")
        ctx_adm = self.rag_agent.buscar_contexto_para_bloque("Proceso de Admisión y Propuesta Económica", transcripcion, cache_key)
        agente = AdmisionEconomicaAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_adm, contexto_usuario).to_dict())

        # 4. Objeciones
        print("      4️⃣ Manejo de objeciones")
        ctx_obj = self.rag_agent.buscar_contexto_para_bloque("Manejo de objeciones", transcripcion, cache_key)
        agente = ObjecionesAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_obj, contexto_usuario).to_dict())

        # 5. Cierre
        print("      5️⃣ Cierre y próximos pasos")
        ctx_cierre = self.rag_agent.buscar_contexto_para_bloque("Cierre y próximos pasos", transcripcion, cache_key)
        agente = CierreAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_cierre, contexto_usuario).to_dict())

        # 6. Estilo
        print("      6️⃣ Estilo y comunicación")
        ctx_estilo = self.rag_agent.buscar_contexto_para_bloque("Estilo y comunicación", transcripcion, cache_key)
        agente = EstiloAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_estilo, contexto_usuario, audio_features).to_dict())

        print(f"      ✓ {len(evaluaciones)} agentes ejecutados individualmente")
        return evaluaciones

    # ========== RESUMEN CONTEXTUAL DEL LEAD ==========

    def _extraer_resumen_contextual(self, transcripcion: str, cache_key: str) -> Dict:
        """
        Extrae información del perfil del lead y contexto de la llamada.

        Genera:
        - perfil_lead: Descripción del candidato
        - objetivo_del_lead: Qué busca el candidato
        - factor_determinante_compra: El factor clave que decidirá si compra
        - barreras_principales: Obstáculos detectados
        - fecha_seguimiento: Fecha y hora del seguimiento comprometido (o null)
        """
        print("   🔍 Extrayendo perfil del lead y contexto...")

        # Tomar muestras del inicio, medio y final para contexto completo
        lineas = transcripcion.split('\n')
        total_lineas = len(lineas)

        # v5.1: Muestras ampliadas para mejor extracción del perfil del lead
        inicio = '\n'.join(lineas[:min(50, total_lineas)])
        medio = '\n'.join(lineas[total_lineas//3 : total_lineas//3 + 40]) if total_lineas > 90 else ""
        final = '\n'.join(lineas[-min(50, total_lineas):])

        muestra = f"""
=== INICIO DE LA LLAMADA ===
{inicio}

=== PARTE MEDIA ===
{medio}

=== FINAL DE LA LLAMADA ===
{final}
"""

        prompt_sistema = """
Eres un analista de ventas. Extrae información del LEAD (cliente potencial) de esta transcripción.

IMPORTANTE:
- El [LEAD] es el cliente potencial que está considerando estudiar en OBS
- El [ASESOR] es quien vende el programa

Analiza lo que dice el [LEAD] para extraer su perfil, pero también observa
si el asesor recondujo al lead hacia un programa diferente al que llegó inicialmente.

⚠️ RECONDUCCIÓN: Si el lead llegó a la llamada con un programa o especialización
en mente (o con una idea vaga) y el asesor lo redirigió hacia un programa diferente
más adecuado a su perfil → esto es un mérito del asesor, NO el objetivo original
del lead. En ese caso:
- "objetivo_del_lead" debe reflejar el OBJETIVO REAL del lead (qué quiere conseguir
  profesionalmente), NO el nombre del programa al que fue redirigido.
- "reconduccion_asesor" debe ser true, con nota del programa original y el programa
  al que fue redirigido.

FORMATO JSON OBLIGATORIO:
{
  "perfil_lead": "Descripción breve: profesión, experiencia, situación actual. Ej: 'Ingeniero con 5 años de experiencia en logística, busca especialización para ascender'",
  "objetivo_del_lead": "El objetivo PROFESIONAL del lead (qué quiere conseguir), no el nombre del programa. Ej: 'Cambio de carrera hacia análisis de datos'",
  "factor_determinante_compra": "El factor ÚNICO más importante que decidirá si el lead compra o no. Ej: 'Aprobación de financiación por la empresa', 'Comparación de precio con competencia', 'Consulta con pareja'. Sé específico, no genérico.",
  "barreras_principales": ["Barrera 1", "Barrera 2"],
  "fecha_seguimiento": "ISO datetime del seguimiento acordado en la llamada, ej: '2026-03-25T10:00:00'. null si no se acordó fecha concreta.",
  "reconduccion_asesor": false,
  "nota_reconduccion": "Si reconduccion_asesor=true: describe brevemente el programa inicial del lead y hacia cuál lo recondujo el asesor. Ej: 'Lead llegó interesado en MBA, asesor recondujo hacia Máster en Marketing Digital por mejor encaje con su perfil'. Si false: dejar vacío."
}

GUÍA PARA FACTOR_DETERMINANTE_COMPRA:
- Es el factor que, si se resuelve positivamente, probablemente cierre la venta
- Ejemplos: "Aprobación de beca por empresa", "Precio vs universidad X", "Decidir entre programa A y B",
  "Consulta con pareja sobre dedicación horaria", "Ver si caben los plazos con su trabajo actual"

GUÍA PARA BARRERAS:
- Ejemplos: "Precio elevado", "Falta de tiempo", "Necesita consultar con pareja/jefe",
  "Comparando con otra universidad", "Dudas sobre modalidad online", "Sin urgencia"

GUÍA PARA FECHA_SEGUIMIENTO:
- Solo si en la llamada se acordó explícitamente una fecha/hora para el siguiente contacto
- Si el asesor dijo "te llamo el martes a las 10" → extraer esa fecha/hora
- Si no hay fecha concreta → null
"""

        prompt_usuario = f"""
Analiza esta transcripción y extrae el perfil del LEAD:

{muestra}

Genera el JSON con la información del lead.
"""

        try:
            resp = consultar_gpt(prompt_sistema, prompt_usuario, f"{cache_key}_resumen_contextual")
            data = json.loads(resp)

            # Validar campos obligatorios
            campos_requeridos = ["perfil_lead", "objetivo_del_lead",
                                "factor_determinante_compra", "barreras_principales"]

            for campo in campos_requeridos:
                if campo not in data:
                    data[campo] = "No identificado" if campo != "barreras_principales" else []

            # fecha_seguimiento puede ser null
            if "fecha_seguimiento" not in data:
                data["fecha_seguimiento"] = None

            # Campos de reconducción con defaults seguros
            if "reconduccion_asesor" not in data:
                data["reconduccion_asesor"] = False
            if "nota_reconduccion" not in data:
                data["nota_reconduccion"] = ""

            print(f"      ✓ Perfil: {data.get('perfil_lead', 'N/A')[:50]}...")
            print(f"      ✓ Factor compra: {data.get('factor_determinante_compra', 'N/A')}")
            print(f"      ✓ Seguimiento: {data.get('fecha_seguimiento', 'sin fecha')}")

            return data

        except Exception as e:
            print(f"   ⚠️ Error extrayendo resumen contextual: {e}")
            return {
                "perfil_lead": "Error en extracción",
                "objetivo_del_lead": "No identificado",
                "factor_determinante_compra": "No identificado",
                "barreras_principales": [],
                "fecha_seguimiento": None,
            }

    # ========== SHERIFF ANTI-ALUCINACIONES ==========

    def _sheriff_validar(self, evaluaciones: List[Dict], transcripcion: str) -> List[Dict]:
        """Valida que las evidencias citadas existan realmente en la transcripción COMPLETA"""
        evaluaciones_validadas = []

        for evaluacion in evaluaciones:
            bloque = evaluacion.get("bloque", "Unknown")
            evidencia_principal = evaluacion.get("evidencia_principal", "")
            evidencias_extra = evaluacion.get("evidencias_extra", [])

            # CRÍTICO: Validar contra transcripción COMPLETA (no extracto)
            # Esto soluciona el problema de alucinaciones en Cierre que usa extracto
            evidencia_valida = self._validar_evidencia(evidencia_principal, transcripcion)

            evidencias_extra_validas = sum(
                1 for ev in evidencias_extra
                if self._validar_evidencia(ev, transcripcion)
            )

            total_evidencias = 1 + len(evidencias_extra)
            evidencias_verificadas = (1 if evidencia_valida else 0) + evidencias_extra_validas

            porcentaje_verificado = (evidencias_verificadas / total_evidencias * 100) if total_evidencias > 0 else 0

            # REGLA SHERIFF: Si < 30% de evidencias son verificables → ALUCINACIÓN
            # Penalidad: bajar un nivel (BUENO→MEJORABLE, MEJORABLE→MALO)
            ORDEN_CALIFICACIONES = ["MALO", "MEJORABLE", "BUENO"]
            if porcentaje_verificado < 30:
                self.stats["alucinaciones_detectadas"] += 1
                cal_original = evaluacion.get("calificacion")

                if cal_original and cal_original in ORDEN_CALIFICACIONES:
                    idx = ORDEN_CALIFICACIONES.index(cal_original)
                    if idx > 0:  # No se puede bajar más de MALO
                        cal_ajustada = ORDEN_CALIFICACIONES[idx - 1]
                        evaluacion["calificacion"] = cal_ajustada
                        evaluacion["sheriff_ajuste"] = {
                            "calificacion_original": cal_original,
                            "calificacion_ajustada": cal_ajustada,
                            "razon": f"Evidencias no verificables ({porcentaje_verificado:.0f}%)",
                            "evidencias_verificadas": f"{evidencias_verificadas}/{total_evidencias}"
                        }
                        self.stats["notas_ajustadas_sheriff"] += 1

                        print(f"   🛡️ Sheriff ajustó {bloque}: {cal_original} → {cal_ajustada} (evidencias no verificables)")

            if "metadata" not in evaluacion:
                evaluacion["metadata"] = {}

            evaluacion["metadata"]["sheriff_validacion"] = {
                "evidencias_total": total_evidencias,
                "evidencias_verificadas": evidencias_verificadas,
                "porcentaje_verificado": round(porcentaje_verificado, 1),
                "estado": "OK" if porcentaje_verificado >= 30 else "ALUCINACION_DETECTADA"
            }

            evaluaciones_validadas.append(evaluacion)

        return evaluaciones_validadas

    def _validar_evidencia(self, evidencia: str, transcripcion: str) -> bool:
        """Valida que la evidencia exista en la transcripción con fuzzy matching"""
        if not evidencia or len(evidencia) < 10:
            return False

        import re
        evidencia_limpia = re.sub(r'\[([^\]]+)\]:\s*', '', evidencia).strip()

        if len(evidencia_limpia) < 15:
            return evidencia_limpia.lower() in transcripcion.lower()

        try:
            from rapidfuzz import fuzz
            ventana = len(evidencia_limpia) + 100
            transcripcion_lower = transcripcion.lower()
            evidencia_lower = evidencia_limpia.lower()

            mejor_ratio = 0
            for i in range(0, len(transcripcion_lower) - ventana + 1, 100):
                fragmento = transcripcion_lower[i:i+ventana]
                ratio = fuzz.partial_ratio(evidencia_lower, fragmento)
                if ratio > mejor_ratio:
                    mejor_ratio = ratio
                if ratio >= 85:
                    return True

            return mejor_ratio >= 75

        except ImportError:
            palabras = evidencia_limpia.lower().split()
            palabras_encontradas = sum(1 for p in palabras if p in transcripcion.lower())
            return (palabras_encontradas / len(palabras)) >= 0.6

    # ========== TOPE COMERCIAL ==========

    def _aplicar_tope_comercial(self, calificacion_global: str, evaluaciones: List[Dict]) -> dict:
        """
        Regla Python que impide que la calificación global sea BUENO cuando
        los tres bloques comerciales críticos fallan simultáneamente.

        Bloques comerciales críticos (los tres que más acercan a matrícula):
          - Investigación: sin perfil del lead no hay personalización posible
          - Proceso de Admisión y Propuesta Económica: inversión y comité
          - Cierre y próximos pasos: compromiso y siguiente paso con fecha

        El documento maestro OBS exige: diagnóstico, propuesta personalizada,
        inversión, cierre y siguiente paso. Sin esos momentos no hay BUENO global.

        Regla 1: Si CUALQUIERA de los tres es MALO → global máx MEJORABLE.
        Regla 2: Si NINGUNO de los tres llegó a BUENO (todos ≤ MEJORABLE) → global máx MEJORABLE.

        Solo actúa cuando la calificación global ya es BUENO (nunca empeora MEJORABLE).
        Si algún bloque no fue evaluado (desconexión, off-record) no aplica el tope.
        """
        ORDEN_CAL = {"MALO": 0, "MEJORABLE": 1, "BUENO": 2}

        if ORDEN_CAL.get(calificacion_global, 0) < 2:
            return {"ajustada": False, "calificacion": calificacion_global, "motivo": None}

        cal_investigacion = None
        cal_admision = None
        cal_cierre = None
        for e in evaluaciones:
            bloque = e.get("bloque", "")
            cal = e.get("calificacion")
            if bloque == "Investigación" and cal in ORDEN_CAL:
                cal_investigacion = cal
            elif bloque == "Proceso de Admisión y Propuesta Económica" and cal in ORDEN_CAL:
                cal_admision = cal
            elif bloque == "Cierre y próximos pasos" and cal in ORDEN_CAL:
                cal_cierre = cal

        # Si algún bloque no tiene calificación válida (off-record / desconexión), no aplicar
        if cal_investigacion is None or cal_admision is None or cal_cierre is None:
            return {"ajustada": False, "calificacion": calificacion_global, "motivo": None}

        val_inv = ORDEN_CAL[cal_investigacion]
        val_adm = ORDEN_CAL[cal_admision]
        val_cierre = ORDEN_CAL[cal_cierre]
        motivo = None

        if val_inv == 0 or val_adm == 0 or val_cierre == 0:
            # Regla 1: alguno de los tres es MALO
            bloques_malo = []
            if val_inv == 0:
                bloques_malo.append("Investigación")
            if val_adm == 0:
                bloques_malo.append("Proceso de Admisión y Propuesta Económica")
            if val_cierre == 0:
                bloques_malo.append("Cierre y próximos pasos")
            nombres = " y ".join(bloques_malo)
            plural = "s" if len(bloques_malo) > 1 else ""
            motivo = (
                f"{nombres} calificado{plural} como MALO. Sin los tres momentos "
                f"comerciales clave (investigación del lead, inversión presentada, "
                f"cierre con compromiso), la calificación global no puede ser BUENO "
                f"aunque otros bloques sean sólidos."
            )
        elif max(val_inv, val_adm, val_cierre) < 2:
            # Regla 2: ninguno de los tres llegó a BUENO (todos son MEJORABLE)
            motivo = (
                "Ninguno de los tres bloques comerciales críticos (Investigación, "
                "Admisión y Propuesta Económica, Cierre) alcanzó BUENO. El documento "
                "maestro OBS exige diagnóstico del lead, inversión y cierre con "
                "compromiso. Sin al menos uno de esos momentos en BUENO, la "
                "calificación global no puede ser BUENO aunque la presentación "
                "del programa haya sido excelente."
            )

        if motivo:
            print(f"   📊 Tope comercial: BUENO → MEJORABLE — {motivo[:80]}...")
            self.stats["notas_ajustadas_sheriff"] += 1
            return {"ajustada": True, "calificacion": "MEJORABLE", "motivo": motivo}

        return {"ajustada": False, "calificacion": calificacion_global, "motivo": None}

    # ========== SÍNTESIS FINAL ==========

    def _sintetizar_evaluaciones(self, evaluaciones: List[Dict],
                                 transcripcion: str, asesor: str,
                                 resumen_contextual: Dict = None) -> Dict:
        """Genera reporte final consolidado CON resumen contextual"""
        from collections import Counter

        # Calcular calificación global por mayoría simple
        CALIFICACIONES_VALIDAS = {"MALO", "MEJORABLE", "BUENO"}
        calificaciones_validas = [
            e["calificacion"] for e in evaluaciones
            if e.get("calificacion") in CALIFICACIONES_VALIDAS
        ]

        if calificaciones_validas:
            conteo = Counter(calificaciones_validas)
            calificacion_global = conteo.most_common(1)[0][0]
        else:
            calificacion_global = None

        # ── TOPE COMERCIAL ────────────────────────────────────────────────────
        # El documento maestro OBS establece que toda entrevista debe incluir:
        # diagnóstico, presentación personalizada, INVERSIÓN, CIERRE y SIGUIENTE PASO.
        # Si los bloques que representan esos momentos críticos de avance fallan,
        # la calificación global no puede ser BUENO aunque el resto vote mayoritariamente
        # BUENO. Una llamada "bien explicada" ≠ una llamada "bien cerrada comercialmente".
        tope = self._aplicar_tope_comercial(calificacion_global, evaluaciones)
        if tope["ajustada"]:
            calificacion_global = tope["calificacion"]
        # ─────────────────────────────────────────────────────────────────────

        # Generar áreas de mejora: bloques MALO o MEJORABLE con recomendación
        areas_mejora = []
        for e in evaluaciones:
            bloque = e.get("bloque", "Unknown")
            cal = e.get("calificacion")
            recomendacion = e.get("recomendacion_accionable", "")

            if cal in ("MALO", "MEJORABLE") and recomendacion:
                areas_mejora.append(f"[{bloque}] ({cal}): {recomendacion}")

        # Si no hay áreas de mejora explícitas (todos BUENOS), incluir recomendaciones igual
        if not areas_mejora and evaluaciones:
            for e in evaluaciones:
                bloque = e.get("bloque", "Unknown")
                recomendacion = e.get("recomendacion_accionable", "")
                if recomendacion:
                    areas_mejora.append(f"[{bloque}]: {recomendacion}")
                    break  # Solo la primera para no saturar

        bloques_con_calificacion = len(calificaciones_validas)

        # Construir reporte final
        reporte = {
            "asesor": asesor,
            "meta": {
                "version_modelo": "Centauro_V5.0_Calificacion_Ordinal",
                "flags_tecnicos": {
                    "modo_batch": self.config.MODO_BATCH,
                    "modo_descripcion": self.stats["modo_ejecucion"],
                    "bloques_evaluados": bloques_con_calificacion,
                    "bloques_criticos": len(self.config.BLOQUES_CRITICOS),
                    "bloques_secundarios": len(self.config.BATCH_SECUNDARIOS.agentes),
                    "sheriff_activo": True,
                    "distribucion_calificaciones": dict(Counter(calificaciones_validas))
                }
            },
            "resumen_contextual": resumen_contextual or {
                "perfil_lead": "No extraído",
                "objetivo_del_lead": "No identificado",
                "factor_determinante_compra": "No identificado",
                "barreras_principales": [],
                "fecha_seguimiento": None,
            },
            "evaluacion_por_bloques": evaluaciones,
            "calificacion_global": calificacion_global,
            "tope_comercial": tope if tope["ajustada"] else None,
            "feedback_resumido": {
                "areas_mejora": areas_mejora if areas_mejora else ["Revisión general de todos los bloques recomendada"]
            }
        }

        return reporte
