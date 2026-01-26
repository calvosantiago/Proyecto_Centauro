"""
Módulo Core v4.0: Lógica central del sistema multi-agente

Incluye:
- RAG dinámico
- Orquestador multi-agente
- Sistema de memoria
- Gestión de asesores
- Chat handler
"""
from .rag_dynamic import DynamicRAGAgent
from .orchestrator import CentauroOrchestrator
from .config_agents import OptimizacionConfig
from .memoria import memory_manager, MemoryManager, AsesorProfile
from .gestion_asesores import gestion_asesores, GestionAsesores
from .chat_handler import ChatHandler

__all__ = [
    'DynamicRAGAgent',
    'CentauroOrchestrator',
    'OptimizacionConfig',
    'memory_manager',
    'MemoryManager',
    'AsesorProfile',
    'gestion_asesores',
    'GestionAsesores',
    'ChatHandler'
]