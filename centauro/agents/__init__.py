"""
Paquete de Agentes Evaluadores - Proyecto Centauro v5.0

Agentes disponibles:
- DiarizationAgent: Identifica speakers en la transcripción
- InvestigacionAgent: Evalúa la fase de investigación/necesidades
- PropuestaValorAgent: Evalúa la propuesta de valor
- AdmisionEconomicaAgent: Evalúa admisión y propuesta económica
- ObjecionesAgent: Evalúa el manejo de objeciones
- CierreAgent: Evalúa el cierre y próximos pasos
- EstiloAgent: Evalúa el estilo y comunicación
"""
from .diarization_agent import DiarizationAgent
from .investigacion_agent import InvestigacionAgent
from .propuesta_valor_agent import PropuestaValorAgent
from .admision_economica_agent import AdmisionEconomicaAgent
from .objeciones_agent import ObjecionesAgent
from .cierre_agent import CierreAgent
from .estilo_agent import EstiloAgent

__all__ = [
    'DiarizationAgent',
    'InvestigacionAgent',
    'PropuestaValorAgent',
    'AdmisionEconomicaAgent',
    'ObjecionesAgent',
    'CierreAgent',
    'EstiloAgent',
]
