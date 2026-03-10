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

    def analizar_entrevista_completa(self, nombre_archivo: str, texto_crudo: str, contexto_usuario: str = None) -> Dict:
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

        # --- FASE 1: DIARIZACIÓN ---
        print("\n📍 FASE 1: Diarización")
        diarization_agent = DiarizationAgent(nombre_asesor=nombre_archivo)
        transcripcion_diarizada = diarization_agent.diarizar(texto_protegido, nombre_archivo)
        asesor_detectado = diarization_agent.asesor_detectado or nombre_archivo
        self.stats["llamadas_api"] += 7

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
            evaluaciones_secundarias = self._evaluar_bloques_secundarios(transcripcion_diarizada, cache_key, contexto_usuario)
            evaluaciones.extend(evaluaciones_secundarias)
            self.stats["llamadas_api"] += 1

        else:
            # MODO INDIVIDUAL: Cada agente una llamada
            print("\n   🔬 MODO PRUEBAS: Todos los agentes individual")
            evaluaciones = self._evaluar_todos_individual(transcripcion_diarizada, cache_key, contexto_usuario)
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

    def _evaluar_bloques_secundarios(self, transcripcion: str, cache_key: str, contexto_usuario: str = None) -> List[Dict]:
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

        prompt_sistema = f"""
Eres un auditor CRÍTICO que evalúa DOS bloques secundarios simultáneamente.

CALIFICACIÓN ORDINAL (elige UNA etiqueta por bloque):
🔴 MALO: Insuficiente, desorganizado o contraproducente
🟡 MEJORABLE: Correcto pero genérico, mecánico, sin profundidad real
🟢 BUENO: Personalizado, profesional, conecta con el lead

MANUAL - PROPUESTA DE VALOR:
{ctx_propuesta}

MANUAL - ESTILO:
{ctx_estilo}
{ejemplos_bp_texto}

⚠️ REGLA CRÍTICA OBLIGATORIA ⚠️
TODAS las evidencias DEBEN ser CITAS LITERALES EXACTAS de la transcripción.
- Usa COPY-PASTE directo, no parafrasees
- Incluye SIEMPRE la etiqueta [ASESOR]: o [LEAD]:
- NUNCA resumas, SIEMPRE cita textual

FORMATO JSON OBLIGATORIO:
{{
  "propuesta_valor": {{
    "calificacion": "MALO" | "MEJORABLE" | "BUENO",
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA (COPY-PASTE)...",
    "evidencias_extra": ["[ASESOR]: Otra cita EXACTA (COPY-PASTE)..."],
    "razonamiento": "¿Personalizó? ¿Beneficios o características? ¿Conectó con el lead? ¿Por qué esa calificación?",
    "recomendacion_accionable": "Combina en un SOLO texto fluido: (1) qué mejorar, (2) UNA técnica de los libros del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 frases ejemplo adaptadas a ESTA conversación. Máx 6-8 líneas."
  }},
  "estilo": {{
    "calificacion": "MALO" | "MEJORABLE" | "BUENO",
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA...",
    "evidencias_extra": ["[ASESOR]: Otra cita EXACTA..."],
    "razonamiento": "Análisis del tono, ritmo y empatía. ¿Por qué esa calificación?",
    "recomendacion_accionable": "Combina en un SOLO texto fluido: (1) qué mejorar en estilo, (2) UNA técnica de los libros del CONTEXTO que aplique, dando 2 frases ejemplo. Máx 6-8 líneas."
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

⚠️ REGLAS CRÍTICAS:
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

            if "propuesta_valor" in data:
                eval_pv = data["propuesta_valor"]
                eval_pv["bloque"] = "Propuesta de valor Institución y Programa"
                eval_pv["confianza"] = 0.85
                evaluaciones.append(eval_pv)

            if "estilo" in data:
                eval_estilo = data["estilo"]
                eval_estilo["bloque"] = "Estilo y comunicación"
                eval_estilo["confianza"] = 0.85
                evaluaciones.append(eval_estilo)

            print(f"      ✓ 2 bloques secundarios en 1 llamada batch")
            return evaluaciones

        except Exception as e:
            print(f"   ⚠️ Error en batch secundarios: {e}")
            return []

    # ========== EVALUACIÓN: TODO INDIVIDUAL (Modo Pruebas) ==========

    def _evaluar_todos_individual(self, transcripcion: str, cache_key: str, contexto_usuario: str = None) -> List[Dict]:
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
        evaluaciones.append(agente.evaluate(transcripcion, ctx_estilo, contexto_usuario).to_dict())

        print(f"      ✓ {len(evaluaciones)} agentes ejecutados individualmente")
        return evaluaciones

    # ========== RESUMEN CONTEXTUAL DEL LEAD ==========

    def _extraer_resumen_contextual(self, transcripcion: str, cache_key: str) -> Dict:
        """
        Extrae información del perfil del lead y contexto de la llamada.

        Genera:
        - perfil_lead: Descripción del candidato
        - fase_funnel: En qué etapa del proceso está
        - objetivo_del_lead: Qué busca el candidato
        - barreras_principales: Obstáculos detectados
        - resultado_general: Cómo terminó la llamada
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
  "fase_funnel": "AWARENESS | CONSIDERATION | DECISION | CIERRE_INMEDIATO",
  "objetivo_del_lead": "El objetivo PROFESIONAL del lead (qué quiere conseguir), no el nombre del programa. Ej: 'Cambio de carrera hacia análisis de datos'",
  "barreras_principales": ["Barrera 1", "Barrera 2"],
  "resultado_general": "POSITIVO_CON_COMPROMISO | POSITIVO_SIN_FECHA | NEUTRO_PENDIENTE | NEGATIVO_OBJECCION_FUERTE",
  "reconduccion_asesor": false,
  "nota_reconduccion": "Si reconduccion_asesor=true: describe brevemente el programa inicial del lead y hacia cuál lo recondujo el asesor. Ej: 'Lead llegó interesado en MBA, asesor recondujo hacia Máster en Marketing Digital por mejor encaje con su perfil'. Si false: dejar vacío."
}

GUÍA PARA FASE_FUNNEL:
- AWARENESS: Apenas conoce OBS, explorando opciones
- CONSIDERATION: Comparando activamente, tiene dudas específicas
- DECISION: Ya decidido a estudiar, solo falta resolver detalles (precio, fechas)
- CIERRE_INMEDIATO: Listo para matricularse en esta llamada

GUÍA PARA RESULTADO_GENERAL:
- POSITIVO_CON_COMPROMISO: Hay fecha de siguiente paso o intención clara
- POSITIVO_SIN_FECHA: Interesado pero sin compromiso concreto
- NEUTRO_PENDIENTE: Ni sí ni no, "lo pensaré"
- NEGATIVO_OBJECCION_FUERTE: Objeción no resuelta (precio, tiempo, etc.)

GUÍA PARA BARRERAS:
- Ejemplos: "Precio elevado", "Falta de tiempo", "Necesita consultar con pareja/jefe",
  "Comparando con otra universidad", "Dudas sobre modalidad online", "Sin urgencia"
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
            campos_requeridos = ["perfil_lead", "fase_funnel", "objetivo_del_lead",
                                "barreras_principales", "resultado_general"]

            for campo in campos_requeridos:
                if campo not in data:
                    data[campo] = "No identificado" if campo != "barreras_principales" else []

            # Campos de reconducción con defaults seguros
            if "reconduccion_asesor" not in data:
                data["reconduccion_asesor"] = False
            if "nota_reconduccion" not in data:
                data["nota_reconduccion"] = ""

            print(f"      ✓ Perfil: {data.get('perfil_lead', 'N/A')[:50]}...")
            print(f"      ✓ Fase: {data.get('fase_funnel', 'N/A')}")
            print(f"      ✓ Resultado: {data.get('resultado_general', 'N/A')}")

            return data

        except Exception as e:
            print(f"   ⚠️ Error extrayendo resumen contextual: {e}")
            return {
                "perfil_lead": "Error en extracción",
                "fase_funnel": "CONSIDERATION",
                "objetivo_del_lead": "No identificado",
                "barreras_principales": [],
                "resultado_general": "NEUTRO_PENDIENTE"
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
                "fase_funnel": "CONSIDERATION",
                "objetivo_del_lead": "No identificado",
                "barreras_principales": [],
                "resultado_general": "NEUTRO_PENDIENTE"
            },
            "evaluacion_por_bloques": evaluaciones,
            "calificacion_global": calificacion_global,
            "feedback_resumido": {
                "areas_mejora": areas_mejora if areas_mejora else ["Revisión general de todos los bloques recomendada"]
            }
        }

        return reporte
