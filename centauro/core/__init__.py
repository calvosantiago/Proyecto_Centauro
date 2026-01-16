"""
Módulo Core: Lógica central del sistema multi-agente

INSTRUCCIÓN: REEMPLAZA el contenido de centauro/core/__init__.py con esto
"""
from .rag_dynamic import DynamicRAGAgent
from .orchestrator import CentauroOrchestrator
from .config_agents import OptimizacionConfig

__all__ = [
    'DynamicRAGAgent',
    'CentauroOrchestrator',
    'OptimizacionConfig'
]