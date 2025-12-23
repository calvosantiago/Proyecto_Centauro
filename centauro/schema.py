from pydantic import BaseModel, Field
from typing import List, Optional

class Hallazgo(BaseModel):
    criterio: str = Field(..., description="Nombre del criterio evaluado según el manual")
    cumple: bool = Field(..., description="True si lo hizo bien, False si falló")
    cita_evidencia: str = Field(..., description="Frase exacta dicha por el asesor en la transcripción")
    referencia_manual: str = Field(..., description="Nombre del documento o sección del manual que justifica esto")
    feedback: str = Field(..., description="Consejo constructivo para el asesor")

class ReporteCalidad(BaseModel):
    asesor: str = Field(..., description="Nombre del asesor si se detecta")
    resumen_ejecutivo: str
    puntos_fuertes: List[Hallazgo]
    areas_mejora: List[Hallazgo]
    nota_final_0_10: int