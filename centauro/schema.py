from pydantic import BaseModel
from typing import List, Optional

class ItemEvaluacion(BaseModel):
    criterio: str
    cumple: bool
    cita_evidencia: str
    referencia_manual: str
    feedback: str
    razonamiento: str  # <--- NUEVO CAMPO: Aquí la IA explicará su lógica

class ReporteCalidad(BaseModel):
    asesor: str
    resumen_ejecutivo: str
    puntos_fuertes: List[ItemEvaluacion]
    areas_mejora: List[ItemEvaluacion]
    nota_final_0_10: float