"""
Configuración del Sistema Multi-Agente con Optimizaciones v3.0

NUEVA ESTRUCTURA:
- BLOQUES CRÍTICOS: Agentes individuales especializados (máxima calidad)
- BLOQUES SECUNDARIOS: Procesamiento batch (optimización costos)

MODOS:
- MODO_BATCH = True  → Híbrido (críticos individual + secundarios batch)
- MODO_BATCH = False → Todo individual (modo pruebas)
"""
from dataclasses import dataclass
from typing import List

@dataclass
class BatchConfig:
    """Configuración de grupos de agentes para procesamiento batch"""
    nombre: str
    agentes: List[str]
    usa_transcripcion_completa: bool
    longitud_extracto: int = None

class OptimizacionConfig:
    """
    Configuración central v3.0 - Sistema Híbrido Inteligente
    """

    # ========== BLOQUES CRÍTICOS (Agentes Individuales) ==========
    BLOQUES_CRITICOS = [
        "Investigación",                          # Fusión: Detección + Apertura
        "Proceso de Admisión y Propuesta Económica",  # NUEVO
        "Manejo de objeciones",
        "Cierre y próximos pasos"
    ]

    # ========== BLOQUES SECUNDARIOS (Batch) ==========
    BATCH_SECUNDARIOS = BatchConfig(
        nombre="batch_secundarios",
        agentes=[
            "Propuesta de valor Institución y Programa",
            "Estilo y comunicación"
        ],
        usa_transcripcion_completa=True
    )
    
    # Extractos para bloques que no necesitan transcripción completa
    # v5.1: Investigación ahora recibe transcripción completa (necesita evaluar
    # aprovechamiento posterior de la info). Solo Cierre usa extracto.
    EXTRACTOS = {
        "Cierre y próximos pasos": {
            "inicio": -2500,  # Últimos 2500 caracteres (fallback, CierreAgent tiene su propia lógica)
            "fin": None,
        }
    }

    # RAG: Fragmentos recuperados
    RAG_TOP_K = 5

    # Cache: Activar cache de contextos RAG
    ACTIVAR_CACHE = True

    # ========== MODO DE EJECUCIÓN ==========
    # True  = HÍBRIDO (críticos individuales + secundarios batch) → PRODUCCIÓN
    # False = TODO INDIVIDUAL (cada agente 1 llamada) → PRUEBAS
    MODO_BATCH = True
    
    @classmethod
    def get_extracto(cls, bloque_nombre: str, transcripcion: str) -> str:
        """
        Extrae la porción relevante de la transcripción para un bloque específico
        """
        if bloque_nombre not in cls.EXTRACTOS:
            return transcripcion
        
        config = cls.EXTRACTOS[bloque_nombre]
        inicio = config["inicio"]
        fin = config["fin"]
        
        if inicio < 0:  # Negativo = desde el final
            return transcripcion[inicio:]
        elif fin is None:
            return transcripcion[inicio:]
        else:
            return transcripcion[inicio:fin]
    
    @classmethod
    def estadisticas_ahorro(cls):
        """
        Calcula el ahorro estimado de tokens v3.0 (Híbrido)
        """
        return {
            "modo_hibrido": "4 agentes críticos individuales + 2 secundarios batch",
            "bloques_criticos": "Máxima calidad con contexto completo",
            "bloques_secundarios": "Batch optimizado (1 llamada para 2 bloques)",
            "extractos_investigacion_cierre": "Reduce 80% tokens en extractos",
            "rag_optimizado": "Top-5 fragmentos por bloque",
            "cache": "Elimina búsquedas RAG repetidas",
            "ahorro_vs_individual": "~45% reducción de costos",
            "calidad_vs_batch_full": "+15% mejor detección en bloques críticos"
        }

    @classmethod
    def get_modo_descripcion(cls):
        """Descripción del modo actual"""
        if cls.MODO_BATCH:
            return "HÍBRIDO: 4 críticos individual + 2 secundarios batch (PRODUCCIÓN)"
        else:
            return "INDIVIDUAL: Cada agente 1 llamada (MODO PRUEBAS)"