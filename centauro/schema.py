from typing import List, Optional, Any
from pydantic import BaseModel, Field

# --- NIVEL 1: HECHOS OBSERVABLES (EXTRACTOR) ---

class EventoClave(BaseModel):
    fase: str = Field(..., description="Fase de la llamada (ej: Sondeo, Cierre)")
    evento: str = Field(..., description="Descripción del hecho (ej: 'Cliente menciona dolor por precio')")
    cita_evidencia: str = Field(..., description="Texto literal transcrito")
    timestamp_aprox: Optional[str] = Field(None, description="Momento aprox (Inicio/Mitad/Fin) o Timecode")

# --- NIVEL 2: EVALUACIÓN (EVALUADOR) ---

class BloqueEvaluacion(BaseModel):
    id_bloque: str
    titulo: str
    puntuacion_1_5: Optional[int] = Field(None, description="Nota 1-5. Null si es Off-Record")
    observabilidad: str = Field("ALTA", description="ALTA, MEDIA, BAJA o NULA (Off-Record)")
    
    # Estado: EVALUADO, OFF_RECORD, SIN_EVIDENCIA
    estado_evaluacion: str = "EVALUADO" 
    
    evidencias_validadas: List[str] = Field(default_factory=list, description="Lista de citas que sustentan la nota")
    razonamiento: str = "Sin razonamiento."
    recomendaciones_accionables: Optional[str] = None

# --- NIVEL 3: REPORTE FINAL (AUDITOR) ---

class ScorecardFinal(BaseModel):
    promedio_calculado_1_5: float = 0.0
    nota_final_0_10: float = 0.0
    calificacion_cualitativa: str = "Pendiente" # A, B, C, D
    semaforo: str = "GRIS" # VERDE, AMARILLO, ROJO

class ResumenContextual(BaseModel):
    perfil_lead: str = "Desconocido"
    fase_funnel: str = "Desconocida"
    nivel_dificultad: str = "Medio"
    intencion_compra: str = "Desconocida"

class FeedbackResumido(BaseModel):
    fortalezas: List[str] = []
    areas_mejora: List[str] = []

class MetaData(BaseModel):
    version_modelo: str = "Centauro_v3_Tridente"
    flags_tecnicos: dict = {} # ej: {"recording_started_late": True}

# --- OBJETO RAÍZ ---

class ReporteCalidad(BaseModel):
    asesor: str = "Desconocido"
    meta: MetaData = Field(default_factory=MetaData)
    resumen_contextual: ResumenContextual = Field(default_factory=ResumenContextual)
    
    # Timeline de hechos (Lo que PASÓ)
    timeline_momentos_clave: List[EventoClave] = []
    
    # Evaluación (Lo que OPINAMOS)
    evaluacion_por_bloques: List[BloqueEvaluacion] = []
    
    # Nota Final
    scorecard_final: ScorecardFinal = Field(default_factory=ScorecardFinal)
    feedback_resumido: FeedbackResumido = Field(default_factory=FeedbackResumido)