"""
Módulo de Agentes Especializados
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from .diarization_agent import DiarizationAgent
from .apertura_agent import AperturaAgent

__all__ = [
    'BaseEvaluatorAgent',
    'EvaluationResult',
    'DiarizationAgent',
    'AperturaAgent',
]