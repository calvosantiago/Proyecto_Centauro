from pydantic import BaseModel
from typing import List, Optional

class ItemEvaluacion(BaseModel):
    criterio: str
    cumple: bool
    cita_evidencia: str
    referencia_manual: str
    feedback: str
    razonamiento: str
    importancia: str  # <--- NUEVO: "CRITICO", "ALTA", "MEDIA", "BAJA"

class ReporteCalidad(BaseModel):
    asesor: str
    resumen_ejecutivo: str
    puntos_fuertes: List[ItemEvaluacion]
    areas_mejora: List[ItemEvaluacion]
    # La nota la calcularemos en Python, pero dejamos el campo para guardarla
    nota_final_0_10: float