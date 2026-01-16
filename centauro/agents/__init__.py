"""
Módulo de Agentes Especializados
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from .diarization_agent import DiarizationAgent
from .apertura_agent import AperturaAgent
from .deteccion_agent import DeteccionNecesidadesAgent
from .presentacion_agent import PresentacionAgent
from .objeciones_agent import ObjecionesAgent
from .cierre_agent import CierreAgent
from .estilo_agent import EstiloAgent

__all__ = [
    'BaseEvaluatorAgent',
    'EvaluationResult',
    'DiarizationAgent',
    'AperturaAgent',
    'DeteccionNecesidadesAgent',
    'PresentacionAgent',
    'ObjecionesAgent',
    'CierreAgent',
    'EstiloAgent',
]