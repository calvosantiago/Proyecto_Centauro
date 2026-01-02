from typing import List, Optional, Any
from pydantic import BaseModel, Field

# --- NIVEL 1: HECHOS OBSERVABLES (EXTRACTOR) ---

class EventoClave(BaseModel):
    fase: str = Field(..., description="Fase de la llamada (ej: Sondeo, Cierre)")
    evento: str = Field(..., description="Descripción del hecho (ej: 'Cliente menciona dolor por precio')")
    cita_evidencia: str = Field(..., description="Texto literal transcrito")
    timestamp_aprox: Optional[str] = Field(None, description="Momento aprox (Inicio/Mitad/Fin) o Timecode")

class EvidenciaSpan(BaseModel):
    tipo: str = Field(..., description="principal|secundaria")
    timestamp_inicio: Optional[float] = Field(None, description="Inicio en segundos si existe")
    timestamp_fin: Optional[float] = Field(None, description="Fin en segundos si existe")
    start_idx: Optional[int] = Field(None, description="Indice inicio en texto")
    end_idx: Optional[int] = Field(None, description="Indice fin en texto")
    texto: str = Field(..., description="Evidencia literal del transcript")

class EventoExtraido(BaseModel):
    tipo: str = Field(..., description="Apertura|Necesidades|Propuesta|Objecion|Cierre|Estilo|Legal")
    evento: str = Field(..., description="Hecho observable resumido")
    evidencia: str = Field(..., description="Texto literal transcrito")
    timestamp_inicio: Optional[float] = Field(None, description="Inicio en segundos si existe")
    timestamp_fin: Optional[float] = Field(None, description="Fin en segundos si existe")
    start_idx: Optional[int] = Field(None, description="Indice inicio en texto")
    end_idx: Optional[int] = Field(None, description="Indice fin en texto")
    locutor_probable: str = Field("desconocido", description="agente|lead|desconocido")
    confianza_evento: float = Field(0.5, description="0-1 confianza")

class ObservabilityItem(BaseModel):
    bloque: str = Field(..., description="Bloque evaluable")
    estado: str = Field(..., description="ALTA|MEDIA|BAJA|NO_OBSERVABLE_OFF_RECORD")
    motivo: Optional[str] = Field(None, description="Motivo si no observable")

class ExtractorOutput(BaseModel):
    meta: "MetaData" = Field(default_factory=lambda: MetaData(version_modelo="Centauro_Extractor_v1"))
    resumen_contextual: "ResumenContextual" = Field(default_factory=lambda: ResumenContextual())
    events: List[EventoExtraido] = []
    observability: List[ObservabilityItem] = []

# --- NIVEL 2: EVALUACIÓN (EVALUADOR) ---

class BloqueEvaluacion(BaseModel):
    id_bloque: str
    titulo: str
    puntuacion_1_5: Optional[int] = Field(None, description="Nota 1-5. Null si es Off-Record")
    observabilidad: str = Field("ALTA", description="ALTA, MEDIA, BAJA o NULA (Off-Record)")
    
    # Estado: EVALUADO, OFF_RECORD, SIN_EVIDENCIA
    estado_evaluacion: str = "EVALUADO" 
    
    evidencias: List[EvidenciaSpan] = Field(default_factory=list, description="Evidencias con spans/timestamps")
    evidencias_validadas: List[str] = Field(default_factory=list, description="Citas validadas por auditoria")
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

class AuditoriaResultado(BaseModel):
    contradicciones_detectadas: List[str] = []
    evidencias_invalidas: List[str] = []
    accion_sugerida: str = "mantener"

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
    # Transparencia
    lista_no_observable: List[ObservabilityItem] = []
    auditoria: AuditoriaResultado = Field(default_factory=AuditoriaResultado)

    # Campos amigables para PDF
    resumen_ejecutivo: str = "Sin resumen disponible."
    puntos_fuertes: List[dict] = []
    areas_mejora: List[dict] = []
