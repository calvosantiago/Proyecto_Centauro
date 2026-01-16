"""
Orquestador del Sistema Multi-Agente con Sheriff + Citas Literales FORZADAS

INSTRUCCIÓN: REEMPLAZA el contenido de:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\core\\orchestrator.py

CAMBIO CRÍTICO: Prompts que FUERZAN citas literales obligatorias
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
    """Orquestador principal con Sheriff anti-alucinaciones"""
    
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
        """Pipeline completo orquestado con Sheriff"""
        print(f"\n{'='*60}")
        print(f"🎯 ANÁLISIS MULTI-AGENTE OPTIMIZADO: {nombre_archivo}")
        print(f"{'='*60}\n")
        
        # --- FASE 1: DIARIZACIÓN ---
        print("📍 FASE 1: Diarización")
        diarization_agent = DiarizationAgent(nombre_asesor=nombre_archivo)
        transcripcion_diarizada = diarization_agent.diarizar(texto_crudo, nombre_archivo)
        self.stats["llamadas_api"] += 7
        
        # --- FASE 2: EXTRACCIÓN DE TEMAS ---
        print("\n📍 FASE 2: Análisis de contexto")
        cache_key = nombre_archivo
        temas = self.rag_agent.extraer_temas_llamada(transcripcion_diarizada, cache_key)
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
            nombre_archivo
        )
        self.stats["llamadas_api"] += 1
        
        reporte_final["meta"]["stats_optimizacion"] = self.stats
        
        print(f"\n{'='*60}")
        print(f"✅ COMPLETADO - Nota: {reporte_final['puntuacion_global_1_5']}/5")
        print(f"📊 Llamadas API: {self.stats['llamadas_api']}")
        print(f"🛡️ Sheriff: {self.stats['alucinaciones_detectadas']} alucinaciones detectadas")
        print(f"{'='*60}\n")
        
        return reporte_final
    
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
        
        # Limpiar etiquetas [ASESOR]/[LEAD] y nombres
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
            
            return mejor_ratio >= 75  # Más permisivo (era 80)
            
        except ImportError:
            palabras = evidencia_limpia.lower().split()
            palabras_encontradas = sum(1 for p in palabras if p in transcripcion.lower())
            return (palabras_encontradas / len(palabras)) >= 0.6  # Más permisivo
    
    # ========== EVALUACIÓN POR BATCHES CON CITAS FORZADAS ==========
    
    def _evaluar_batch_ligero(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """Evalúa Apertura, Cierre y Legal CON CITAS LITERALES OBLIGATORIAS"""
        inicio = self.config.get_extracto("Apertura", transcripcion)
        final = self.config.get_extracto("Cierre y siguiente paso", transcripcion)
        legal_extracto = self.config.get_extracto("Legal (Compliance)", transcripcion)
        
        contexto_apertura = self.rag_agent.buscar_contexto_para_bloque("Apertura", transcripcion, cache_key)
        contexto_cierre = self.rag_agent.buscar_contexto_para_bloque("Cierre y siguiente paso", transcripcion, cache_key)
        contexto_legal = self.rag_agent.buscar_contexto_para_bloque("Legal (Compliance)", transcripcion, cache_key)
        
        prompt_sistema = f"""
Eres un auditor que evalúa TRES bloques simultáneamente.

MANUAL - APERTURA:
{contexto_apertura}

MANUAL - CIERRE:
{contexto_cierre}

MANUAL - LEGAL:
{contexto_legal}

⚠️ REGLA CRÍTICA OBLIGATORIA ⚠️
TODAS las evidencias DEBEN ser CITAS LITERALES EXACTAS de la transcripción.
- Usa COPY-PASTE directo, no parafrasees
- Incluye SIEMPRE la etiqueta [ASESOR]: o [LEAD]:
- Si la cita es larga, usa los primeros 100 caracteres exactos
- NUNCA resumas, NUNCA interpretes, SIEMPRE cita textual

FORMATO JSON OBLIGATORIO:
{{
  "apertura": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Cita textual EXACTA del saludo...",
    "evidencias_extra": [
      "[ASESOR]: Otra cita textual EXACTA...",
      "[LEAD]: Respuesta textual EXACTA del lead..."
    ],
    "razonamiento": "...",
    "recomendacion_accionable": "..."
  }},
  "cierre": {{...similar...}},
  "legal": {{...similar...}}
}}

EJEMPLO DE EVIDENCIA CORRECTA:
"evidencia_principal": "[ASESOR]: Hola buenos días Cindy, ¿cómo estás? Te llamo de OBS Business School"

EJEMPLO DE EVIDENCIA INCORRECTA (NO HACER):
"evidencia_principal": "El asesor establece un diálogo abierto y busca entender las dudas"
"""
        
        prompt_usuario = f"""
APERTURA (cita literal de aquí):
{inicio}

CIERRE (cita literal de aquí):
{final}

LEGAL (cita literal de aquí):
{legal_extracto}

Genera las 3 evaluaciones con CITAS LITERALES OBLIGATORIAS.
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
            
            if "legal" in data:
                eval_legal = data["legal"]
                eval_legal["bloque"] = "Legal (Compliance)"
                eval_legal["confianza"] = 0.9
                evaluaciones.append(eval_legal)
            
            print(f"      ✓ Evaluados 3 bloques en 1 llamada")
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
Eres un auditor que evalúa CUATRO bloques.

MANUAL - DETECCIÓN:
{ctx_deteccion}

MANUAL - PRESENTACIÓN:
{ctx_presentacion}

MANUAL - OBJECIONES:
{ctx_objeciones}

MANUAL - ESTILO:
{ctx_estilo}

⚠️ REGLA CRÍTICA OBLIGATORIA ⚠️
TODAS las evidencias DEBEN ser CITAS TEXTUALES EXACTAS.
- COPY-PASTE literal, NO parafrasees
- Incluye [ASESOR]: o [LEAD]: siempre
- Si es largo, primeros 100-150 caracteres exactos

FORMATO JSON:
{{
  "deteccion_necesidades": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "[ASESOR]: Pregunta textual EXACTA...",
    "evidencias_extra": ["[ASESOR]: Otra pregunta EXACTA...", "[LEAD]: Respuesta EXACTA..."],
    "razonamiento": "...",
    "recomendacion_accionable": "..."
  }},
  "presentacion_programa": {{...}},
  "manejo_objeciones": {{...}},
  "estilo_comunicacion": {{...}}
}}
"""
        
        prompt_usuario = f"""
Analiza esta transcripción y CITA LITERALMENTE:

{transcripcion}

Genera las 4 evaluaciones con CITAS TEXTUALES EXACTAS.
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
        """Modo sin optimizar"""
        evaluaciones = []
        agente_apertura = AperturaAgent()
        contexto = self.rag_agent.buscar_contexto_para_bloque("Apertura", transcripcion, cache_key)
        resultado = agente_apertura.evaluate(transcripcion, contexto)
        evaluaciones.append(resultado.to_dict())
        return evaluaciones
    
    def _sintetizar_evaluaciones(self, evaluaciones: List[Dict], 
                                 transcripcion: str, nombre: str) -> Dict:
        """Genera reporte final consolidado"""
        notas_validas = [
            e["puntuacion_1_5"] for e in evaluaciones
            if e.get("puntuacion_1_5") is not None
        ]
        
        nota_global = round(sum(notas_validas) / len(notas_validas), 2) if notas_validas else 0.0
        
        return {
            "asesor": nombre,
            "meta": {
                "version_modelo": "Centauro_V2_MultiAgent_Optimized_Sheriff",
                "flags_tecnicos": {
                    "modo_batch": self.config.MODO_BATCH,
                    "bloques_evaluados": len(notas_validas),
                    "sheriff_activo": True
                }
            },
            "evaluacion_por_bloques": evaluaciones,
            "puntuacion_global_1_5": nota_global,
            "feedback_resumido": {
                "fortalezas": [e["bloque"] for e in evaluaciones if e.get("puntuacion_1_5", 0) >= 4],
                "areas_mejora": [e["bloque"] for e in evaluaciones if e.get("puntuacion_1_5", 5) < 3]
            }
        }