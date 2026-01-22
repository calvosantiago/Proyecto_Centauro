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

    def analizar_entrevista_completa(self, nombre_archivo: str, texto_crudo: str) -> Dict:
        """Pipeline completo orquestado v3.0"""
        print(f"\n{'='*60}")
        print(f"🎯 CENTAURO v3.0 - MODO HÍBRIDO: {nombre_archivo}")
        print(f"{'='*60}")
        print(f"⚙️  {self.stats['modo_ejecucion']}")
        print(f"{'='*60}\n")

        # --- FASE 1: DIARIZACIÓN ---
        print("📍 FASE 1: Diarización")
        diarization_agent = DiarizationAgent(nombre_asesor=nombre_archivo)
        transcripcion_diarizada = diarization_agent.diarizar(texto_crudo, nombre_archivo)
        asesor_detectado = diarization_agent.asesor_detectado or nombre_archivo
        self.stats["llamadas_api"] += 7

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
            evaluaciones_criticas = self._evaluar_bloques_criticos(transcripcion_diarizada, cache_key)
            evaluaciones.extend(evaluaciones_criticas)
            self.stats["llamadas_api"] += len(self.config.BLOQUES_CRITICOS)

            print("\n   📦 BLOQUES SECUNDARIOS (batch optimizado):")
            evaluaciones_secundarias = self._evaluar_bloques_secundarios(transcripcion_diarizada, cache_key)
            evaluaciones.extend(evaluaciones_secundarias)
            self.stats["llamadas_api"] += 1

        else:
            # MODO INDIVIDUAL: Cada agente una llamada
            print("\n   🔬 MODO PRUEBAS: Todos los agentes individual")
            evaluaciones = self._evaluar_todos_individual(transcripcion_diarizada, cache_key)
            self.stats["llamadas_api"] += 6  # 6 agentes

        # --- FASE 3.5: SHERIFF ---
        print("\n📍 FASE 3.5: Auditoría Sheriff (anti-alucinaciones)")
        evaluaciones = self._sheriff_validar(evaluaciones, transcripcion_diarizada)

        # --- FASE 4: SÍNTESIS ---
        print("\n📍 FASE 4: Síntesis y validación")
        reporte_final = self._sintetizar_evaluaciones(
            evaluaciones,
            transcripcion_diarizada,
            asesor_detectado,
            resumen_contextual
        )
        self.stats["llamadas_api"] += 1

        reporte_final["meta"]["stats_optimizacion"] = self.stats

        print(f"\n{'='*60}")
        print(f"✅ COMPLETADO - Nota: {reporte_final['puntuacion_global_1_5']}/5")
        print(f"📊 Llamadas API: {self.stats['llamadas_api']}")
        print(f"🛡️ Sheriff: {self.stats['alucinaciones_detectadas']} alucinaciones detectadas")
        print(f"{'='*60}\n")

        return reporte_final

    # ========== EVALUACIÓN: BLOQUES CRÍTICOS (Individual) ==========

    def _evaluar_bloques_criticos(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """
        Evalúa bloques críticos con agentes individuales especializados

        Bloques críticos:
        1. Investigación (extracto primeros 3000 chars)
        2. Proceso de Admisión y Propuesta Económica (transcripción completa)
        3. Manejo de objeciones (transcripción completa)
        4. Cierre y próximos pasos (extracto últimos 2500 chars)
        """
        evaluaciones = []

        # 1. INVESTIGACIÓN (con extracto)
        print("      1️⃣ Investigación (agente individual)")
        extracto_investigacion = self.config.get_extracto("Investigación", transcripcion)
        contexto_investigacion = self.rag_agent.buscar_contexto_para_bloque("Investigación", transcripcion, cache_key)

        agente_investigacion = InvestigacionAgent()
        resultado = agente_investigacion.evaluate(extracto_investigacion, contexto_investigacion)
        evaluaciones.append(resultado.to_dict())

        # 2. PROCESO ADMISIÓN/ECONÓMICA (completo)
        print("      2️⃣ Proceso Admisión y Propuesta Económica (agente individual)")
        contexto_admision = self.rag_agent.buscar_contexto_para_bloque(
            "Proceso de Admisión y Propuesta Económica",
            transcripcion,
            cache_key
        )

        agente_admision = AdmisionEconomicaAgent()
        resultado = agente_admision.evaluate(transcripcion, contexto_admision)
        evaluaciones.append(resultado.to_dict())

        # 3. MANEJO DE OBJECIONES (completo)
        print("      3️⃣ Manejo de objeciones (agente individual)")
        contexto_objeciones = self.rag_agent.buscar_contexto_para_bloque("Manejo de objeciones", transcripcion, cache_key)

        agente_objeciones = ObjecionesAgent()
        resultado = agente_objeciones.evaluate(transcripcion, contexto_objeciones)
        evaluaciones.append(resultado.to_dict())

        # 4. CIERRE Y PRÓXIMOS PASOS (con extracto)
        print("      4️⃣ Cierre y próximos pasos (agente individual)")
        extracto_cierre = self.config.get_extracto("Cierre y próximos pasos", transcripcion)
        contexto_cierre = self.rag_agent.buscar_contexto_para_bloque("Cierre y próximos pasos", transcripcion, cache_key)

        agente_cierre = CierreAgent()
        resultado = agente_cierre.evaluate(transcripcion, contexto_cierre)  # CierreAgent maneja extracto interno
        evaluaciones.append(resultado.to_dict())

        print(f"      ✓ {len(evaluaciones)} bloques críticos evaluados")
        return evaluaciones

    # ========== EVALUACIÓN: BLOQUES SECUNDARIOS (Batch) ==========

    def _evaluar_bloques_secundarios(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """
        Evalúa bloques secundarios en batch (1 llamada para 2 bloques)

        Bloques secundarios:
        1. Propuesta de valor Institución y Programa
        2. Estilo y comunicación
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

        prompt_sistema = f"""
Eres un auditor CRÍTICO que evalúa DOS bloques secundarios simultáneamente.

RÚBRICA:
1 = NEGLIGENTE: Error grave o ausencia total
2 = DEFICIENTE: Pasivo, inseguro
3 = MEDIOCRE: Cumple pero sin profundidad
4 = BUENO: Sólido, profesional, con detalles pulibles
5 = EXCELENCIA: Liderazgo claro, conecta emocionalmente

MANUAL - PROPUESTA DE VALOR:
{ctx_propuesta}

MANUAL - ESTILO:
{ctx_estilo}

⚠️ REGLA CRÍTICA OBLIGATORIA ⚠️
TODAS las evidencias DEBEN ser CITAS LITERALES EXACTAS de la transcripción.
- Usa COPY-PASTE directo, no parafrasees
- Incluye SIEMPRE la etiqueta [ASESOR]: o [LEAD]:
- NUNCA resumas, SIEMPRE cita textual

FORMATO JSON OBLIGATORIO:
{{
  "propuesta_valor": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA...",
    "evidencias_extra": ["[ASESOR]: Otra cita EXACTA..."],
    "razonamiento": "Explica QUÉ faltó para el 5. Sé CRÍTICO.",
    "recomendacion_accionable": "Instrucción directa para mejorar."
  }},
  "estilo": {{...similar...}}
}}
"""

        prompt_usuario = f"""
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

    def _evaluar_todos_individual(self, transcripcion: str, cache_key: str) -> List[Dict]:
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
        evaluaciones.append(agente.evaluate(extracto_inv, ctx_inv).to_dict())

        # 2. Propuesta Valor
        print("      2️⃣ Propuesta de valor Institución y Programa")
        ctx_pv = self.rag_agent.buscar_contexto_para_bloque("Propuesta de valor Institución y Programa", transcripcion, cache_key)
        agente = PropuestaValorAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_pv).to_dict())

        # 3. Admisión/Económica
        print("      3️⃣ Proceso Admisión y Propuesta Económica")
        ctx_adm = self.rag_agent.buscar_contexto_para_bloque("Proceso de Admisión y Propuesta Económica", transcripcion, cache_key)
        agente = AdmisionEconomicaAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_adm).to_dict())

        # 4. Objeciones
        print("      4️⃣ Manejo de objeciones")
        ctx_obj = self.rag_agent.buscar_contexto_para_bloque("Manejo de objeciones", transcripcion, cache_key)
        agente = ObjecionesAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_obj).to_dict())

        # 5. Cierre
        print("      5️⃣ Cierre y próximos pasos")
        ctx_cierre = self.rag_agent.buscar_contexto_para_bloque("Cierre y próximos pasos", transcripcion, cache_key)
        agente = CierreAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_cierre).to_dict())

        # 6. Estilo
        print("      6️⃣ Estilo y comunicación")
        ctx_estilo = self.rag_agent.buscar_contexto_para_bloque("Estilo y comunicación", transcripcion, cache_key)
        agente = EstiloAgent()
        evaluaciones.append(agente.evaluate(transcripcion, ctx_estilo).to_dict())

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

        # Muestras distribuidas
        inicio = '\n'.join(lineas[:min(30, total_lineas)])
        medio = '\n'.join(lineas[total_lineas//3 : total_lineas//3 + 20]) if total_lineas > 60 else ""
        final = '\n'.join(lineas[-min(30, total_lineas):])

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

Analiza SOLO lo que dice el [LEAD] para extraer su perfil.

FORMATO JSON OBLIGATORIO:
{
  "perfil_lead": "Descripción breve: profesión, experiencia, situación actual. Ej: 'Ingeniero con 5 años de experiencia en logística, busca especialización para ascender'",
  "fase_funnel": "AWARENESS | CONSIDERATION | DECISION | CIERRE_INMEDIATO",
  "objetivo_del_lead": "Qué busca conseguir con el máster. Ej: 'Cambio de carrera hacia análisis de datos'",
  "barreras_principales": ["Barrera 1", "Barrera 2"],
  "resultado_general": "POSITIVO_CON_COMPROMISO | POSITIVO_SIN_FECHA | NEUTRO_PENDIENTE | NEGATIVO_OBJECCION_FUERTE"
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
        """Valida que las evidencias citadas existan realmente"""
        evaluaciones_validadas = []

        for evaluacion in evaluaciones:
            bloque = evaluacion.get("bloque", "Unknown")
            evidencia_principal = evaluacion.get("evidencia_principal", "")
            evidencias_extra = evaluacion.get("evidencias_extra", [])

            evidencia_valida = self._validar_evidencia(evidencia_principal, transcripcion)

            evidencias_extra_validas = sum(
                1 for ev in evidencias_extra
                if self._validar_evidencia(ev, transcripcion)
            )

            total_evidencias = 1 + len(evidencias_extra)
            evidencias_verificadas = (1 if evidencia_valida else 0) + evidencias_extra_validas

            porcentaje_verificado = (evidencias_verificadas / total_evidencias * 100) if total_evidencias > 0 else 0

            # REGLA SHERIFF: Si < 30% de evidencias son verificables → ALUCINACIÓN
            if porcentaje_verificado < 30:
                self.stats["alucinaciones_detectadas"] += 1
                nota_original = evaluacion.get("puntuacion_1_5")

                if nota_original and nota_original > 2:
                    nota_ajustada = max(1, nota_original - 2)
                    evaluacion["puntuacion_1_5"] = nota_ajustada
                    evaluacion["sheriff_ajuste"] = {
                        "nota_original": nota_original,
                        "nota_ajustada": nota_ajustada,
                        "razon": f"Evidencias no verificables ({porcentaje_verificado:.0f}%)",
                        "evidencias_verificadas": f"{evidencias_verificadas}/{total_evidencias}"
                    }
                    self.stats["notas_ajustadas_sheriff"] += 1

                    print(f"   🛡️ Sheriff ajustó {bloque}: {nota_original} → {nota_ajustada} (evidencias no verificables)")

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

        # Calcular nota global
        notas_validas = [
            e["puntuacion_1_5"] for e in evaluaciones
            if e.get("puntuacion_1_5") is not None
        ]
        nota_global = round(sum(notas_validas) / len(notas_validas), 2) if notas_validas else 0.0

        # Generar fortalezas y áreas de mejora DETALLADAS
        fortalezas = []
        areas_mejora = []

        for e in evaluaciones:
            bloque = e.get("bloque", "Unknown")
            nota = e.get("puntuacion_1_5", 0)
            razonamiento = e.get("razonamiento", "")

            if nota >= 4:
                # Extraer la razón de la buena nota
                fortalezas.append(f"{bloque} ({nota}/5)")
            elif nota <= 2:
                # Extraer la recomendación
                recomendacion = e.get("recomendacion_accionable", razonamiento[:100])
                areas_mejora.append(f"{bloque}: {recomendacion[:80]}...")
            elif nota == 3:
                # Nota media - también es área de mejora
                recomendacion = e.get("recomendacion_accionable", "Profundizar más")
                areas_mejora.append(f"{bloque}: {recomendacion[:80]}...")

        # Si no hay áreas de mejora explícitas, buscar las notas más bajas
        if not areas_mejora and evaluaciones:
            notas_ordenadas = sorted(evaluaciones, key=lambda x: x.get("puntuacion_1_5", 5))
            for e in notas_ordenadas[:2]:
                bloque = e.get("bloque", "Unknown")
                recomendacion = e.get("recomendacion_accionable", "Mejorar ejecución")
                areas_mejora.append(f"{bloque}: {recomendacion[:80]}...")

        # Construir reporte final
        reporte = {
            "asesor": asesor,
            "meta": {
                "version_modelo": "Centauro_V3.0_Hibrido_Inteligente",
                "flags_tecnicos": {
                    "modo_batch": self.config.MODO_BATCH,
                    "modo_descripcion": self.stats["modo_ejecucion"],
                    "bloques_evaluados": len(notas_validas),
                    "bloques_criticos": len(self.config.BLOQUES_CRITICOS),
                    "bloques_secundarios": len(self.config.BATCH_SECUNDARIOS.agentes),
                    "sheriff_activo": True
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
            "puntuacion_global_1_5": nota_global,
            "feedback_resumido": {
                "fortalezas": fortalezas if fortalezas else ["Ninguna destacable"],
                "areas_mejora": areas_mejora if areas_mejora else ["Revisión general recomendada"]
            }
        }

        return reporte
