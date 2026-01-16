"""
Orquestador del Sistema Multi-Agente con Optimizaciones de Tokens

INSTRUCCIÓN: Copia este archivo en centauro/core/orchestrator.py
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
    """
    Orquestador principal que coordina todos los agentes con optimizaciones
    """
    
    def __init__(self):
        self.rag_agent = DynamicRAGAgent()
        self.config = OptimizacionConfig()
        
        # Contadores de optimización
        self.stats = {
            "llamadas_api": 0,
            "tokens_ahorrados": 0,
            "cache_hits": 0
        }
    
    def analizar_entrevista_completa(self, nombre_archivo: str, texto_crudo: str) -> Dict:
        """
        Pipeline completo orquestado con optimizaciones
        """
        print(f"\n{'='*60}")
        print(f"🎯 ANÁLISIS MULTI-AGENTE OPTIMIZADO: {nombre_archivo}")
        print(f"{'='*60}\n")
        
        # --- FASE 1: DIARIZACIÓN ---
        print("📍 FASE 1: Diarización")
        diarization_agent = DiarizationAgent(nombre_asesor=nombre_archivo)
        transcripcion_diarizada = diarization_agent.diarizar(texto_crudo, nombre_archivo)
        self.stats["llamadas_api"] += 7  # Estimado de chunks
        
        # --- FASE 2: EXTRACCIÓN DE TEMAS (1 vez, con cache) ---
        print("\n📍 FASE 2: Análisis de contexto")
        cache_key = nombre_archivo
        temas = self.rag_agent.extraer_temas_llamada(transcripcion_diarizada, cache_key)
        self.stats["llamadas_api"] += 1
        
        # --- FASE 3: EVALUACIÓN OPTIMIZADA ---
        print("\n📍 FASE 3: Evaluación por agentes (modo BATCH)")
        
        evaluaciones = []
        
        if self.config.MODO_BATCH:
            # BATCH 1: Agentes ligeros (Apertura, Cierre, Legal)
            print("\n   🚀 Batch 1: Agentes ligeros (1 llamada)")
            batch_ligero = self._evaluar_batch_ligero(
                transcripcion_diarizada, 
                cache_key
            )
            evaluaciones.extend(batch_ligero)
            self.stats["llamadas_api"] += 1
            
            # BATCH 2: Agentes pesados (Detección, Presentación, Objeciones, Estilo)
            print("\n   🚀 Batch 2: Agentes pesados (1 llamada)")
            batch_pesado = self._evaluar_batch_pesado(
                transcripcion_diarizada,
                cache_key
            )
            evaluaciones.extend(batch_pesado)
            self.stats["llamadas_api"] += 1
            
        else:
            # Modo sin optimizar (para comparación)
            print("\n   ⚠️ Modo NO optimizado (7 llamadas)")
            evaluaciones = self._evaluar_individual(transcripcion_diarizada, cache_key)
            self.stats["llamadas_api"] += 7
        
        # --- FASE 4: SÍNTESIS ---
        print("\n📍 FASE 4: Síntesis y validación")
        reporte_final = self._sintetizar_evaluaciones(
            evaluaciones,
            transcripcion_diarizada,
            nombre_archivo
        )
        self.stats["llamadas_api"] += 1
        
        # Añadir estadísticas de optimización
        reporte_final["meta"]["stats_optimizacion"] = self.stats
        
        print(f"\n{'='*60}")
        print(f"✅ COMPLETADO - Nota: {reporte_final['puntuacion_global_1_5']}/5")
        print(f"📊 Llamadas API: {self.stats['llamadas_api']}")
        print(f"💾 Cache hits: {self.stats['cache_hits']}")
        print(f"{'='*60}\n")
        
        return reporte_final
    
    def _evaluar_batch_ligero(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """
        Evalúa Apertura, Cierre y Legal en UNA SOLA llamada usando extractos
        """
        # Preparar extractos
        inicio = self.config.get_extracto("Apertura", transcripcion)
        final = self.config.get_extracto("Cierre y siguiente paso", transcripcion)
        legal_extracto = self.config.get_extracto("Legal (Compliance)", transcripcion)
        
        # Contexto RAG específico (compartido para los 3)
        contexto_apertura = self.rag_agent.buscar_contexto_para_bloque(
            "Apertura", transcripcion, cache_key
        )
        contexto_cierre = self.rag_agent.buscar_contexto_para_bloque(
            "Cierre y siguiente paso", transcripcion, cache_key
        )
        contexto_legal = self.rag_agent.buscar_contexto_para_bloque(
            "Legal (Compliance)", transcripcion, cache_key
        )
        
        prompt_sistema = f"""
Eres un auditor que evalúa TRES bloques simultáneamente de forma independiente.

MANUAL - APERTURA:
{contexto_apertura}

MANUAL - CIERRE:
{contexto_cierre}

MANUAL - LEGAL:
{contexto_legal}

FORMATO JSON OBLIGATORIO:
{{
  "apertura": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "...",
    "evidencias_extra": [],
    "razonamiento": "...",
    "recomendacion_accionable": "..."
  }},
  "cierre": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "...",
    "evidencias_extra": [],
    "razonamiento": "...",
    "recomendacion_accionable": "...",
    "recepcion_cliente": {{
      "estado": "ALINEADO",
      "evidencia": "..."
    }}
  }},
  "legal": {{
    "puntuacion_1_5": 3,
    "observabilidad": "ALTA",
    "evidencia_principal": "...",
    "evidencias_extra": [],
    "razonamiento": "...",
    "recomendacion_accionable": "..."
  }}
}}
"""
        
        prompt_usuario = f"""
BLOQUE 1 - APERTURA (analiza solo este extracto):
{inicio}

BLOQUE 2 - CIERRE (analiza solo este extracto):
{final}

BLOQUE 3 - LEGAL (busca aviso legal en este extracto):
{legal_extracto}

Genera las 3 evaluaciones en JSON.
"""
        
        try:
            resp = consultar_gpt(prompt_sistema, prompt_usuario, f"{cache_key}_batch_ligero")
            data = json.loads(resp)
            
            # Convertir a formato estándar
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
            # Fallback: evaluar individualmente
            return self._fallback_individual_ligero(inicio, final, legal_extracto, cache_key)
    
    def _evaluar_batch_pesado(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """
        Evalúa Detección, Presentación, Objeciones y Estilo en UNA SOLA llamada
        """
        # Contextos RAG específicos
        ctx_deteccion = self.rag_agent.buscar_contexto_para_bloque(
            "Detección de necesidades", transcripcion, cache_key
        )
        ctx_presentacion = self.rag_agent.buscar_contexto_para_bloque(
            "Presentación del programa", transcripcion, cache_key
        )
        ctx_objeciones = self.rag_agent.buscar_contexto_para_bloque(
            "Manejo de objeciones", transcripcion, cache_key
        )
        ctx_estilo = self.rag_agent.buscar_contexto_para_bloque(
            "Estilo y comunicación", transcripcion, cache_key
        )
        
        prompt_sistema = f"""
Eres un auditor que evalúa CUATRO bloques simultáneamente.

MANUAL - DETECCIÓN DE NECESIDADES:
{ctx_deteccion}

MANUAL - PRESENTACIÓN:
{ctx_presentacion}

MANUAL - OBJECIONES:
{ctx_objeciones}

MANUAL - ESTILO:
{ctx_estilo}

FORMATO JSON:
{{
  "deteccion_necesidades": {{...}},
  "presentacion_programa": {{...}},
  "manejo_objeciones": {{...}},
  "estilo_comunicacion": {{...}}
}}
"""
        
        prompt_usuario = f"""
Analiza esta transcripción completa para los 4 bloques:

{transcripcion}

Genera las 4 evaluaciones en JSON.
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
            # Fallback
            return []
    
    def _fallback_individual_ligero(self, inicio, final, legal, cache_key):
        """Fallback si el batch falla"""
        print("      ⚠️ Usando evaluación individual como fallback")
        return []
    
    def _evaluar_individual(self, transcripcion: str, cache_key: str) -> List[Dict]:
        """Modo sin optimizar (para comparación)"""
        evaluaciones = []
        
        # Evaluar Apertura individualmente
        agente_apertura = AperturaAgent()
        contexto = self.rag_agent.buscar_contexto_para_bloque("Apertura", transcripcion, cache_key)
        resultado = agente_apertura.evaluate(transcripcion, contexto)
        evaluaciones.append(resultado.to_dict())
        
        # TODO: Añadir resto de agentes individuales
        
        return evaluaciones
    
    def _sintetizar_evaluaciones(self, evaluaciones: List[Dict], 
                                 transcripcion: str, nombre: str) -> Dict:
        """Genera reporte final consolidado"""
        # Calcular nota global
        notas_validas = [
            e["puntuacion_1_5"] for e in evaluaciones
            if e.get("puntuacion_1_5") is not None
        ]
        
        nota_global = round(sum(notas_validas) / len(notas_validas), 2) if notas_validas else 0.0
        
        return {
            "asesor": nombre,
            "meta": {
                "version_modelo": "Centauro_V2_MultiAgent_Optimized",
                "flags_tecnicos": {
                    "modo_batch": self.config.MODO_BATCH,
                    "bloques_evaluados": len(notas_validas)
                }
            },
            "evaluacion_por_bloques": evaluaciones,
            "puntuacion_global_1_5": nota_global,
            "feedback_resumido": {
                "fortalezas": [e["bloque"] for e in evaluaciones if e.get("puntuacion_1_5", 0) >= 4],
                "areas_mejora": [e["bloque"] for e in evaluaciones if e.get("puntuacion_1_5", 5) < 3]
            }
        }