"""
Base Agent v4.0: Template para todos los agentes evaluadores
Define la interfaz común y utilidades compartidas

ACTUALIZADO v4.0: Usa configuración centralizada
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from dataclasses import dataclass, field
import json
from pathlib import Path
from centauro.config import centauro_config

@dataclass
class EvaluationResult:
    """Resultado estandarizado de evaluación

    NOTA v4.0: puntuacion_1_5 ahora acepta decimales (float) para mayor granularidad.
    Valores permitidos: 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0
    """
    bloque: str
    puntuacion_1_5: Optional[float]  # Cambiado de int a float para escala decimal
    observabilidad: str  # ALTA | MEDIA | BAJA | NO_OBSERVABLE_OFF_RECORD
    confianza: float  # 0.0 - 1.0
    evidencia_principal: str
    evidencias_extra: List[str] = field(default_factory=list)
    razonamiento: str = ""
    recomendacion_accionable: str = ""
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario para compatibilidad con schema.py"""
        return {
            "bloque": self.bloque,
            "puntuacion_1_5": self.puntuacion_1_5,
            "observabilidad": self.observabilidad,
            "confianza": self.confianza,
            "evidencia_principal": self.evidencia_principal,
            "evidencias_extra": self.evidencias_extra,
            "razonamiento": self.razonamiento,
            "recomendacion_accionable": self.recomendacion_accionable,
            **self.metadata
        }

class BaseEvaluatorAgent(ABC):
    """
    Clase base abstracta para todos los agentes evaluadores.

    Incluye soporte para consultar ejemplos de buenas prácticas.
    """

    def __init__(self, nombre_bloque: str):
        self.nombre_bloque = nombre_bloque
        self.version = "4.0"
        self.temperatura = centauro_config.LLM_TEMPERATURE_EVALUACION
        self._ejemplos_cache = None  # Cache para ejemplos de buenas prácticas
    
    @abstractmethod
    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """
        Método principal de evaluación que cada agente debe implementar
        """
        pass
    
    def _extract_json_safe(self, raw_response: str) -> Dict:
        """Extrae JSON de forma robusta"""
        if not raw_response:
            raise ValueError("Respuesta vacía del LLM")
        
        clean = raw_response.replace("```json", "").replace("```", "").strip()
        
        import re
        match = re.search(r'\{.*\}', clean, flags=re.DOTALL)
        
        if not match:
            raise ValueError("No se encontró JSON en la respuesta")
        
        json_str = match.group(0)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON malformado en {self.nombre_bloque}: {e}")
            print(f"   Fragmento: {json_str[:200]}...")
            raise
    
    def _calcular_confianza(self, resultado_raw: Dict) -> float:
        """Calcula nivel de confianza basado en la calidad de la respuesta"""
        score = 1.0

        evidencia = resultado_raw.get("evidencia_principal", "")
        if not evidencia or len(evidencia) < centauro_config.MIN_EVIDENCE_LENGTH:
            score -= centauro_config.CONFIDENCE_PENALTY_SHORT_EVIDENCE
        if "no se pudo evaluar" in evidencia.lower():
            score -= centauro_config.CONFIDENCE_PENALTY_VAGUE_EVIDENCE

        razonamiento = resultado_raw.get("razonamiento", "")
        if len(razonamiento) < centauro_config.MIN_REASONING_LENGTH:
            score -= centauro_config.CONFIDENCE_PENALTY_SHORT_REASONING

        obs = resultado_raw.get("observabilidad", "MEDIA")
        if obs in ["BAJA", "NO_OBSERVABLE_OFF_RECORD"]:
            score -= centauro_config.CONFIDENCE_PENALTY_LOW_OBSERVABILITY

        return max(0.0, min(1.0, score))
    
    def _create_fallback_result(self, error_msg: str) -> EvaluationResult:
        """Genera resultado de fallback cuando la evaluación falla"""
        return EvaluationResult(
            bloque=self.nombre_bloque,
            puntuacion_1_5=None,
            observabilidad="ERROR_EVALUACION",
            confianza=0.0,
            evidencia_principal=f"Error: {error_msg}",
            evidencias_extra=[],
            razonamiento="La evaluación automática falló. Requiere revisión manual.",
            recomendacion_accionable="Revisar transcripción manualmente",
            metadata={"error": error_msg}
        )
    
    def _validar_evidencia_literal(self, evidencia: str, transcripcion: str) -> bool:
        """Valida que la evidencia citada exista realmente en la transcripción"""
        try:
            from rapidfuzz import fuzz
            evidencia_clean = evidencia.lower().strip()
            transcripcion_clean = transcripcion.lower()
            ratio = fuzz.partial_ratio(evidencia_clean, transcripcion_clean)
            return ratio >= centauro_config.SHERIFF_FUZZY_THRESHOLD
        except ImportError:
            return evidencia.lower() in transcripcion.lower()

    def _buscar_ejemplos_relevantes(self, transcripcion: str, max_ejemplos: int = None) -> List[str]:
        if max_ejemplos is None:
            max_ejemplos = centauro_config.RAG_TOP_K_BUENAS_PRACTICAS
        """
        Busca ejemplos de buenas prácticas relevantes para esta evaluación.

        Usa RAG para encontrar fragmentos similares de conversaciones exitosas.
        Los ejemplos se usan como INSPIRACIÓN, no como reglas rígidas.

        Args:
            transcripcion: Conversación a evaluar
            max_ejemplos: Máximo número de ejemplos a devolver

        Returns:
            Lista de textos de ejemplos relevantes
        """
        try:
            # Importar RAG dinámico
            from centauro.core.rag_dynamic import buscar_contexto_dinamico

            # Construir query específica para este bloque
            query = f"Ejemplo de buena práctica en {self.nombre_bloque}: {transcripcion[:500]}"

            # Buscar en la colección de buenas prácticas
            # Nota: El RAG debe tener indexados los ejemplos de inputs/docs/buenas_practicas/
            resultados = buscar_contexto_dinamico(
                query=query,
                collection_name="buenas_practicas",  # Colección específica
                k=max_ejemplos
            )

            if not resultados:
                return []

            # Extraer textos de ejemplos
            ejemplos = []
            for resultado in resultados[:max_ejemplos]:
                # Formato esperado del RAG: dict con 'text' y 'metadata'
                if isinstance(resultado, dict):
                    ejemplos.append(resultado.get('text', ''))
                else:
                    ejemplos.append(str(resultado))

            return [e for e in ejemplos if e]  # Filtrar vacíos

        except Exception as e:
            # Si falla (ej: no hay ejemplos indexados), continuar sin ejemplos
            print(f"   ℹ️ No se pudieron cargar ejemplos de buenas prácticas: {e}")
            return []

    def _enriquecer_contexto_con_ejemplos(self, contexto_base: str, transcripcion: str) -> str:
        """
        Añade ejemplos de buenas prácticas al contexto del prompt.

        IMPORTANTE: Los ejemplos son REFERENCIAS, no reglas absolutas.
        El agente debe usarlos como inspiración, no como checklist rígido.

        Args:
            contexto_base: Contexto original del manual
            transcripcion: Conversación a evaluar

        Returns:
            Contexto enriquecido con ejemplos
        """
        ejemplos = self._buscar_ejemplos_relevantes(transcripcion, max_ejemplos=2)

        if not ejemplos:
            return contexto_base

        # Añadir sección de ejemplos al final del contexto
        contexto_enriquecido = contexto_base + "\n\n"
        contexto_enriquecido += "="*80 + "\n"
        contexto_enriquecido += "📚 EJEMPLOS DE BUENAS PRÁCTICAS - USAR COMO GUÍA, NO COMO FRONTERA\n"
        contexto_enriquecido += "="*80 + "\n\n"

        contexto_enriquecido += "⚠️ ADVERTENCIA CRÍTICA SOBRE EL USO DE ESTOS EJEMPLOS:\n\n"

        contexto_enriquecido += "Estos ejemplos muestran UNA FORMA EXITOSA de hacer las cosas, NO LA ÚNICA.\n\n"

        contexto_enriquecido += "✅ SÍ ESTÁ PERMITIDO:\n"
        contexto_enriquecido += "  • Usar los ejemplos como INSPIRACIÓN para sugerir mejoras\n"
        contexto_enriquecido += "  • Citar técnicas específicas que funcionaron bien en los ejemplos\n"
        contexto_enriquecido += "  • Identificar PATRONES de comunicación exitosa\n"
        contexto_enriquecido += "  • Dar feedback constructivo basado en lo que se observa que funciona\n"
        contexto_enriquecido += "  • Reconocer cuando la conversación usa técnicas DIFERENTES pero EFECTIVAS\n\n"

        contexto_enriquecido += "❌ NO ESTÁ PERMITIDO:\n"
        contexto_enriquecido += "  • Penalizar porque la conversación no es EXACTAMENTE como el ejemplo\n"
        contexto_enriquecido += "  • Exigir que se use el mismo lenguaje o estructura del ejemplo\n"
        contexto_enriquecido += "  • Bajar la puntuación solo porque es diferente (si es efectivo)\n"
        contexto_enriquecido += "  • Tratar los ejemplos como un CHECKLIST obligatorio\n"
        contexto_enriquecido += "  • Ignorar técnicas válidas que no aparecen en los ejemplos\n\n"

        contexto_enriquecido += "💡 REGLA DE ORO:\n"
        contexto_enriquecido += "   Si la conversación logra el objetivo del bloque (investigar, cerrar, etc.)\n"
        contexto_enriquecido += "   usando un enfoque DIFERENTE pero EFECTIVO → Puntúa alto y RECONÓCELO.\n"
        contexto_enriquecido += "   Los ejemplos son para ENRIQUECER tu análisis, no para LIMITAR tu criterio.\n\n"

        contexto_enriquecido += "🎯 CÓMO USAR LOS EJEMPLOS CORRECTAMENTE:\n"
        contexto_enriquecido += "  1. Evalúa la conversación PRIMERO por sus propios méritos\n"
        contexto_enriquecido += "  2. Identifica qué funcionó bien y qué podría mejorar\n"
        contexto_enriquecido += "  3. LUEGO consulta los ejemplos para sugerencias CONCRETAS de mejora\n"
        contexto_enriquecido += "  4. Si encuentras técnicas exitosas NO presentes en los ejemplos → ¡Celébralas!\n"
        contexto_enriquecido += "  5. Menciona los ejemplos solo cuando sean RELEVANTES y ÚTILES\n\n"

        for i, ejemplo in enumerate(ejemplos, 1):
            contexto_enriquecido += f"--- Ejemplo de referencia {i} (NO obligatorio seguir) ---\n"
            # Truncar ejemplo si es muy largo (usar config)
            max_len = centauro_config.MAX_EJEMPLO_LENGTH_IN_PROMPT
            ejemplo_truncado = ejemplo[:max_len] + "..." if len(ejemplo) > max_len else ejemplo
            contexto_enriquecido += ejemplo_truncado + "\n\n"

        return contexto_enriquecido

    def __repr__(self):
        return f"<{self.__class__.__name__} bloque='{self.nombre_bloque}' v{self.version}>"