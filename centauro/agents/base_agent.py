"""
Base Agent: Template para todos los agentes evaluadores
Define la interfaz común y utilidades compartidas

INSTRUCCIÓN: Copia TODO este archivo en centauro/agents/base_agent.py
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from dataclasses import dataclass, field
import json

@dataclass
class EvaluationResult:
    """Resultado estandarizado de evaluación"""
    bloque: str
    puntuacion_1_5: Optional[int]
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
    """
    
    def __init__(self, nombre_bloque: str):
        self.nombre_bloque = nombre_bloque
        self.version = "2.0"
        self.temperatura = 0.0
    
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
        if not evidencia or len(evidencia) < 20:
            score -= 0.3
        if "no se pudo evaluar" in evidencia.lower():
            score -= 0.3
        
        razonamiento = resultado_raw.get("razonamiento", "")
        if len(razonamiento) < 50:
            score -= 0.2
        
        obs = resultado_raw.get("observabilidad", "MEDIA")
        if obs in ["BAJA", "NO_OBSERVABLE_OFF_RECORD"]:
            score -= 0.2
        
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
            return ratio >= 80
        except ImportError:
            return evidencia.lower() in transcripcion.lower()
    
    def __repr__(self):
        return f"<{self.__class__.__name__} bloque='{self.nombre_bloque}' v{self.version}>"