from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# --- SUB-MODELOS ---

class RecepcionCliente(BaseModel):
    estado: Literal["ALINEADO", "NEUTRO", "RESISTENTE", "NO_DISPONIBLE", "DESCONOCIDO"] = "DESCONOCIDO"
    evidencia: str = ""

class BloqueEvaluacion(BaseModel):
    bloque: str
    calificacion: Optional[str] = Field(None, description="MALO | MEJORABLE | BUENO. Null si no es observable")
    observabilidad: str = "ALTA" # ALTA|MEDIA|BAJA|NO_OBSERVABLE_OFF_RECORD
    confianza: float = 0.0
    evidencia_principal: str = ""
    evidencias_extra: List[str] = []
    razonamiento: str = ""
    recomendacion_accionable: str = ""

    # Campo especial solo para el bloque de cierre (opcional en otros)
    recepcion_cliente: Optional[RecepcionCliente] = None

class CoberturaRevision(BaseModel):
    tramo_1_inicio: str = "sin_hallazgos_en_tramo"
    tramo_2_exploracion: str = "sin_hallazgos_en_tramo"
    tramo_3_desarrollo: str = "sin_hallazgos_en_tramo"
    tramo_4_objeciones: str = "sin_hallazgos_en_tramo"
    tramo_5_cierre: str = "sin_hallazgos_en_tramo"
    alerta_cobertura: str = "OK" # OK | cobertura_insuficiente

class ResumenContextual(BaseModel):
    perfil_lead: str = "..."
    fase_funnel: str = "..."
    objetivo_del_lead: str = "..."
    barreras_principales: List[str] = []
    resultado_general: str = "..."

class MomentoClave(BaseModel):
    tramo: str
    evento: str
    cita: str

class FeedbackResumido(BaseModel):
    fortalezas: List[str] = []
    areas_mejora: List[str] = []

class MetaData(BaseModel):
    version_modelo: str = "Centauro_V11_HeadOfSales"
    flags_tecnicos: dict = {}

# --- MODELO RAÍZ (Match exacto con tu JSON) ---

class ReporteCalidad(BaseModel):
    asesor: str = "Desconocido" # Se rellena en Python
    meta: MetaData = Field(default_factory=MetaData) # Se rellena en Python
    
    resumen_contextual: ResumenContextual
    cobertura_revision: CoberturaRevision
    momentos_clave: List[MomentoClave] = []
    evaluacion_por_bloques: List[BloqueEvaluacion]
    calificacion_global: Optional[str] = None  # MALO | MEJORABLE | BUENO
    feedback_resumido: FeedbackResumido