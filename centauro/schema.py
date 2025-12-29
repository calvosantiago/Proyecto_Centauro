from typing import List, Optional
from pydantic import BaseModel

class ItemEvaluacion(BaseModel):
    criterio: str
    cumple: bool
    cita_evidencia: str
    importancia: str = "MEDIA"
    
    # --- CAMBIO CLAVE: Campos con valor por defecto ---
    # Si la IA no los envía, Pydantic usará estos valores en vez de dar error.
    razonamiento: str = "Sin razonamiento detallado."
    referencia_manual: str = "General"
    feedback: str = "Sin comentarios adicionales."

class ReporteCalidad(BaseModel):
    asesor: str = "Desconocido"
    resumen_ejecutivo: str = "Sin resumen disponible."
    puntos_fuertes: List[ItemEvaluacion] = []
    areas_mejora: List[ItemEvaluacion] = []
    nota_final_0_10: float = 0.0