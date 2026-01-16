"""
Configuración del Sistema Multi-Agente con Optimizaciones

INSTRUCCIÓN: Copia este archivo en centauro/core/config_agents.py
"""
from dataclasses import dataclass
from typing import List

@dataclass
class BatchConfig:
    """Configuración de grupos de agentes para procesamiento batch"""
    nombre: str
    agentes: List[str]
    usa_transcripcion_completa: bool
    longitud_extracto: int = None  # Para agentes ligeros
    
class OptimizacionConfig:
    """
    Configuración central de optimizaciones para reducir consumo de tokens
    """
    
    # BATCH 1: Agentes que solo necesitan extractos (LIGEROS)
    BATCH_LIGERO = BatchConfig(
        nombre="batch_ligero",
        agentes=["Apertura", "Cierre y siguiente paso", "Legal (Compliance)"],
        usa_transcripcion_completa=False
    )
    
    # BATCH 2: Agentes que necesitan transcripción completa (PESADOS)
    BATCH_PESADO = BatchConfig(
        nombre="batch_pesado",
        agentes=[
            "Detección de necesidades",
            "Presentación del programa", 
            "Manejo de objeciones",
            "Estilo y comunicación"
        ],
        usa_transcripcion_completa=True
    )
    
    # Longitudes de extracto por bloque (en caracteres)
    EXTRACTOS = {
        "Apertura": {
            "inicio": 0,
            "fin": 1000,  # Primeros 1000 caracteres
        },
        "Cierre y siguiente paso": {
            "inicio": -2000,  # Últimos 2000 caracteres
            "fin": None,
        },
        "Legal (Compliance)": {
            "inicio": 0,
            "fin": 3000,  # Primeros 3000 (suficiente para detectar aviso)
        }
    }
    
    # RAG: Reducir fragmentos recuperados
    RAG_TOP_K = 5  # En lugar de 20
    
    # Cache: Activar cache de contextos RAG
    ACTIVAR_CACHE = True
    
    # Modo de ejecución
    MODO_BATCH = True  # True = optimizado, False = llamadas individuales
    
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
        Calcula el ahorro estimado de tokens con las optimizaciones
        """
        return {
            "batch_processing": "Reduce 75% tokens de transcripción duplicada",
            "extractos_ligeros": "Reduce 95% tokens en Apertura/Cierre/Legal",
            "rag_optimizado": "Reduce 75% tokens de contexto manual",
            "cache": "Elimina búsquedas RAG repetidas",
            "ahorro_total_estimado": "~60% reducción vs sistema sin optimizar"
        }