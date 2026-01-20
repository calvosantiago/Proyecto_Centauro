"""
Orquestador del Sistema Multi-Agente v2.1

CAMBIOS EN v2.1:
- NUEVO: Genera resumen_contextual (perfil_lead, fase_funnel, objetivo, barreras)
- NUEVO: Fase 2.5 dedicada a extracción de contexto del lead
- FIX: Mejor síntesis de fortalezas/áreas de mejora (no solo por nota)
- FIX: feedback_resumido más detallado

INSTRUCCIÓN: REEMPLAZA el contenido de:
centauro/core/orchestrator.py
"""
from typing import Dict, List
import json
from ..agents import DiarizationAgent, AperturaAgent
from ..agents.base_agent import EvaluationResult
from .rag_dynamic import DynamicRAGAgent
from .config_agents import OptimizacionConfig
from ..llm_client import consultar_gpt
from ..config import settings


class CentauroOrchestrator:
    """Orquestador principal con Sheriff anti-alucinaciones y resumen contextual"""
    
    def __init__(self):
        self.rag_agent = DynamicRAGAgent()
        self.config = OptimizacionConfig()
        
        self.stats = {
            "llamadas_api": 0,
            "tokens_ahorrados": 0,
            "cache_hits": 0,
            "alucinaciones_detectadas": 0,
            "notas_ajustadas_sheriff": 0
        }
    
    def analizar_entrevista_completa(self, nombre_archivo: str, texto_crudo: str) -> Dict:
        """Pipeline completo orquestado con Sheriff y Resumen Contextual"""
        print(f"\n{'='*60}")
        print(f"🎯 ANÁLISIS MULTI-AGENTE OPTIMIZADO: {nombre_archivo}")
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
        
        # --- FASE 2.5: RESUMEN CONTEXTUAL (NUEVO) ---
        print("\n📍 FASE 2.5: Extracción de perfil del lead")
        resumen_contextual = self._extraer_resumen_contextual(transcripcion_diarizada, cache_key)
        self.stats["llamadas_api"] += 1
        
        # --- FASE 3: EVALUACIÓN OPTIMIZADA ---
        print("\n📍 FASE 3: Evaluación por agentes (modo BATCH)")
        
        evaluaciones = []
        
        if self.config.MODO_BATCH:
            print("\n   🚀 Batch 1: Agentes ligeros (1 llamada)")
            batch_ligero = self._evaluar_batch_ligero(transcripcion_diarizada, cache_key)
            evaluaciones.extend(batch_ligero)
            self.stats["llamadas_api"] += 1
            
            print("\n   🚀 Batch 2: Agentes pesados (1 llamada)")
            batch_pesado = self._evaluar_batch_pesado(transcripcion_diarizada, cache_key)
            evaluaciones.extend(batch_pesado)
            self.stats["llamadas_api"] += 1
        else:
            evaluaciones = self._evaluar_individual(transcripcion_diarizada, cache_key)
            self.stats["llamadas_api"] += 7
        
        # --- FASE 3.5: SHERIFF ---
        print("\n📍 FASE 3.5: Auditoría Sheriff (anti-alucinaciones)")
        evaluaciones = self._sheriff_validar(evaluaciones, transcripcion_diarizada)
        
        # --- FASE 4: SÍNTESIS ---
        print("\n📍 FASE 4: Síntesis y validación")
        reporte_final = self._sintetizar_evaluaciones(
            evaluaciones,
            transcripcion_diarizada,
            asesor_detectado,
            resumen_contextual  # NUEVO: Pasar el resumen
        )
        self.stats["llamadas_api"] += 1
        
        reporte_final["meta"]["stats_optimizacion"] = self.stats
        
        print(f"\n{'='*60}")
        print(f"✅ COMPLETADO - Nota: {reporte_final['puntuacion_global_1_5']}/5")
        print(f"📊 Llamadas API: {self.stats['llamadas_api']}")
        print(f"🛡️ Sheriff: {self.stats['alucinaciones_detectadas']} alucinaciones detectadas")
        print(f"{'='*60}\n")
        
        return reporte_final
    
    # ========== NUEVO: EXTRACCIÓN DE RESUMEN CONTEXTUAL ==========
    
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
    
    # ========== EVALUACIÓN POR BATCHES ==========
    
    def _evaluar_batch_ligero(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """Evalúa Apertura y Cierre CON CITAS LITERALES OBLIGATORIAS"""
        inicio = self.config.get_extracto("Apertura", transcripcion)
        final = self.config.get_extracto("Cierre y siguiente paso", transcripcion)
        
        contexto_apertura = self.rag_agent.buscar_contexto_para_bloque("Apertura", transcripcion, cache_key)
        contexto_cierre = self.rag_agent.buscar_contexto_para_bloque("Cierre y siguiente paso", transcripcion, cache_key)
        
        prompt_sistema = f"""
Eres un auditor CRÍTICO que evalúa DOS bloques simultáneamente.
Tu estándar es la EXCELENCIA. No regales notas.

RÚBRICA:
1 = NEGLIGENTE: Error grave o ausencia total
2 = DEFICIENTE: Pasivo, inseguro
3 = MEDIOCRE: Cumple pero sin profundidad
4 = BUENO: Sólido, profesional, con detalles pulibles
5 = EXCELENCIA: Liderazgo claro, conecta emocionalmente

MANUAL - APERTURA:
{contexto_apertura}

MANUAL - CIERRE:
{contexto_cierre}

⚠️ REGLA CRÍTICA OBLIGATORIA ⚠️
TODAS las evidencias DEBEN ser CITAS LITERALES EXACTAS de la transcripción.
- Usa COPY-PASTE directo, no parafrasees
- Incluye SIEMPRE la etiqueta [ASESOR]: o [LEAD]:
- NUNCA resumas, SIEMPRE cita textual

REGLA DE ORO: Antes de dar un 4 o 5, busca activamente 2 "oportunidades perdidas".
Si encuentras dónde podría haber profundizado y no lo hizo → la nota baja.

FORMATO JSON OBLIGATORIO:
{{
  "apertura": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA...",
    "evidencias_extra": ["[ASESOR]: Otra cita EXACTA..."],
    "razonamiento": "Explica QUÉ faltó para el 5. Sé CRÍTICO.",
    "recomendacion_accionable": "Instrucción directa para mejorar."
  }},
  "cierre": {{...similar...}}
}}
"""
        
        prompt_usuario = f"""
APERTURA (primeros minutos):
{inicio}

CIERRE (últimos minutos):
{final}

Evalúa con CITAS LITERALES y sé CRÍTICO con las notas.
"""
        
        try:
            resp = consultar_gpt(prompt_sistema, prompt_usuario, f"{cache_key}_batch_ligero")
            data = json.loads(resp)
            
            evaluaciones = []
            
            if "apertura" in data:
                eval_apertura = data["apertura"]
                eval_apertura["bloque"] = "Apertura"
                eval_apertura["confianza"] = 0.9
                evaluaciones.append(eval_apertura)
            
            if "cierre" in data:
                eval_cierre = data["cierre"]
                eval_cierre["bloque"] = "Cierre y siguiente paso"
                eval_cierre["confianza"] = 0.9
                evaluaciones.append(eval_cierre)
            
            print(f"      ✓ Evaluados 2 bloques en 1 llamada")
            return evaluaciones
            
        except Exception as e:
            print(f"   ⚠️ Error en batch ligero: {e}")
            return []
    
    def _evaluar_batch_pesado(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """Evalúa bloques pesados CON CITAS LITERALES OBLIGATORIAS"""
        ctx_deteccion = self.rag_agent.buscar_contexto_para_bloque("Detección de necesidades", transcripcion, cache_key)
        ctx_presentacion = self.rag_agent.buscar_contexto_para_bloque("Presentación del programa", transcripcion, cache_key)
        ctx_objeciones = self.rag_agent.buscar_contexto_para_bloque("Manejo de objeciones", transcripcion, cache_key)
        ctx_estilo = self.rag_agent.buscar_contexto_para_bloque("Estilo y comunicación", transcripcion, cache_key)
        
        prompt_sistema = f"""
Eres un auditor EXTREMADAMENTE CRÍTICO que evalúa CUATRO bloques.
Tu perfil es de Director Comercial exigente.

RÚBRICA DRACONIANA:
1 = NEGLIGENTE: Error grave que mata la venta
2 = DEFICIENTE: Pasivo, "tomador de pedidos"
3 = MEDIOCRE: Cumple el guion sin alma
4 = BUENO: Profesional, con detalles pulibles
5 = EXCELENCIA: Liderazgo claro, mueve al cliente

MANUAL - DETECCIÓN:
{ctx_deteccion}

MANUAL - PRESENTACIÓN:
{ctx_presentacion}

MANUAL - OBJECIONES:
{ctx_objeciones}

MANUAL - ESTILO:
{ctx_estilo}

⚠️ REGLAS CRÍTICAS ⚠️
1. CITAS LITERALES: Copy-paste exacto con [ASESOR]: o [LEAD]:
2. DISTRIBUCIÓN: Las evidencias deben venir de DIFERENTES partes de la llamada
3. CRÍTICO: Explica QUÉ faltó. No uses lenguaje positivo vacío.
4. OPORTUNIDADES PERDIDAS: Antes de dar 4+, busca 2 momentos donde podría haber hecho más.

PENALIZACIONES:
- Detección: Si el asesor habla más que el lead → máximo 3
- Presentación: Si no personaliza beneficios → máximo 3
- Objeciones: Si contradice el manual → máximo 2
- Estilo: Muletillas, interrupciones → penalizar

FORMATO JSON:
{{
  "deteccion_necesidades": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Pregunta textual EXACTA...",
    "evidencias_extra": ["[LEAD]: Respuesta EXACTA...", "[ASESOR]: Seguimiento EXACTO..."],
    "razonamiento": "Sé CRÍTICO: qué faltó, qué pudo hacer mejor",
    "recomendacion_accionable": "Instrucción específica"
  }},
  "presentacion_programa": {{...}},
  "manejo_objeciones": {{...}},
  "estilo_comunicacion": {{...}}
}}
"""
        
        prompt_usuario = f"""
TRANSCRIPCIÓN COMPLETA:

{transcripcion}

Evalúa los 4 bloques con CITAS TEXTUALES EXACTAS.
Sé CRÍTICO y busca oportunidades perdidas antes de dar notas altas.
"""
        
        try:
            resp = consultar_gpt(prompt_sistema, prompt_usuario, f"{cache_key}_batch_pesado")
            data = json.loads(resp)
            
            evaluaciones = []
            
            mapeo = {
                "deteccion_necesidades": "Detección de necesidades",
                "presentacion_programa": "Presentación del programa",
                "manejo_objeciones": "Manejo de objeciones",
                "estilo_comunicacion": "Estilo y comunicación"
            }
            
            for key, bloque_nombre in mapeo.items():
                if key in data:
                    eval_bloque = data[key]
                    eval_bloque["bloque"] = bloque_nombre
                    eval_bloque["confianza"] = 0.85
                    evaluaciones.append(eval_bloque)
            
            print(f"      ✓ Evaluados 4 bloques en 1 llamada")
            return evaluaciones
            
        except Exception as e:
            print(f"   ⚠️ Error en batch pesado: {e}")
            return []
    
    def _evaluar_individual(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """Modo sin optimizar (fallback)"""
        evaluaciones = []
        agente_apertura = AperturaAgent()
        contexto = self.rag_agent.buscar_contexto_para_bloque("Apertura", transcripcion, cache_key)
        resultado = agente_apertura.evaluate(transcripcion, contexto)
        evaluaciones.append(resultado.to_dict())
        return evaluaciones
    
    # ========== SÍNTESIS MEJORADA ==========
    
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
                "version_modelo": "Centauro_V2.1_MultiAgent_Optimized_Sheriff",
                "flags_tecnicos": {
                    "modo_batch": self.config.MODO_BATCH,
                    "bloques_evaluados": len(notas_validas),
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
