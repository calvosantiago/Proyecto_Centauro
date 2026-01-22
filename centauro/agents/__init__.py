"""
Módulo de Agentes Especializados v3.0

NUEVA ESTRUCTURA:
- InvestigacionAgent (fusiona Apertura + Detección)
- PropuestaValorAgent (renombrado de Presentación)
- AdmisionEconomicaAgent (NUEVO)
- ObjecionesAgent (sin cambios)
- CierreAgent (sin cambios)
- EstiloAgent (sin cambios)
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from .diarization_agent import DiarizationAgent

# Nuevos agentes v3.0
from .investigacion_agent import InvestigacionAgent
from .propuesta_valor_agent import PropuestaValorAgent
from .admision_economica_agent import AdmisionEconomicaAgent

# Agentes sin cambios
from .objeciones_agent import ObjecionesAgent
from .cierre_agent import CierreAgent
from .estilo_agent import EstiloAgent

# Legacy (mantener para compatibilidad temporal)
from .apertura_agent import AperturaAgent
from .deteccion_agent import DeteccionNecesidadesAgent
from .presentacion_agent import PresentacionAgent

__all__ = [
    'BaseEvaluatorAgent',
    'EvaluationResult',
    'DiarizationAgent',
    # v3.0
    'InvestigacionAgent',
    'PropuestaValorAgent',
    'AdmisionEconomicaAgent',
    'ObjecionesAgent',
    'CierreAgent',
    'EstiloAgent',
    # Legacy
    'AperturaAgent',
    'DeteccionNecesidadesAgent',
    'PresentacionAgent',
]