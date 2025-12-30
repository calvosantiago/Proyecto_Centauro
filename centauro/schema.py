from typing import List, Optional
from pydantic import BaseModel

class ItemEvaluacion(BaseModel):
    criterio: str
    cumple: bool = False  # Mantenemos para compatibilidad con el PDF
    puntuacion: int = 1   # NUEVO: Escala 1-5
    cita_evidencia: str
    importancia: str = "MEDIA"
    razonamiento: str = "Sin razonamiento."
    referencia_manual: str = "General"
    feedback: str = "Sin comentarios."

class ReporteCalidad(BaseModel):
    asesor: str = "Desconocido"
    resumen_ejecutivo: str = "Sin resumen."
    puntos_fuertes: List[ItemEvaluacion] = []
    areas_mejora: List[ItemEvaluacion] = []
    nota_final_0_10: float = 0.0