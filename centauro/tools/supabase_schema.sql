-- ============================================================
-- Centauro - Schema para Supabase (PostgreSQL)
-- Ejecutar en SQL Editor de Supabase para crear las tablas
-- ============================================================

-- Asesores (reemplaza JSONs individuales en outputs/perfiles_asesores/)
CREATE TABLE IF NOT EXISTS asesores (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    nombre_normalizado TEXT NOT NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activo BOOLEAN DEFAULT TRUE
);

-- Una fila por evaluacion
CREATE TABLE IF NOT EXISTS evaluaciones (
    id BIGSERIAL PRIMARY KEY,
    asesor_id BIGINT NOT NULL REFERENCES asesores(id),
    opportunity_id TEXT,                -- ej: "2021-002579270", nullable
    fecha TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    calificacion_global TEXT CHECK (calificacion_global IN ('MALO', 'MEJORABLE', 'BUENO')),
    archivo_origen TEXT,
    -- Resumen contextual (del orquestador)
    perfil_lead TEXT,
    objetivo_del_lead TEXT,
    factor_determinante_compra TEXT,    -- factor clave que determinará la compra del lead
    barreras_principales JSONB DEFAULT '[]',
    fecha_seguimiento TIMESTAMPTZ,      -- fecha y hora del seguimiento comprometido
    -- Stats de procesamiento
    llamadas_api INTEGER,
    tiempo_analisis_seg REAL,
    reporte_pdf_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Una fila por bloque por evaluacion (6 bloques x evaluacion)
CREATE TABLE IF NOT EXISTS calificaciones_bloque (
    id BIGSERIAL PRIMARY KEY,
    evaluacion_id BIGINT NOT NULL REFERENCES evaluaciones(id) ON DELETE CASCADE,
    bloque TEXT NOT NULL,
    calificacion TEXT CHECK (calificacion IN ('MALO', 'MEJORABLE', 'BUENO')),
    observabilidad TEXT,
    confianza REAL,
    evidencia_principal TEXT,
    razonamiento TEXT,
    recomendacion_accionable TEXT
);

-- Cache de datos del lead desde Fabric/Power BI
CREATE TABLE IF NOT EXISTS oportunidades (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id TEXT NOT NULL UNIQUE,
    pilar TEXT,
    pais TEXT,
    edad INTEGER,
    programa TEXT,
    entrega_documentacion BOOLEAN,
    matriculado BOOLEAN,
    datos_extra JSONB DEFAULT '{}',
    fecha_sync TIMESTAMPTZ DEFAULT NOW()
);

-- Log de predicciones ML (Fase 3, futuro)
CREATE TABLE IF NOT EXISTS predicciones (
    id BIGSERIAL PRIMARY KEY,
    evaluacion_id BIGINT REFERENCES evaluaciones(id),
    opportunity_id TEXT,
    fecha_prediccion TIMESTAMPTZ DEFAULT NOW(),
    modelo_version TEXT,
    prob_matriculacion REAL,
    prob_entrega_doc REAL,
    features_json JSONB
);

-- Indices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_evaluaciones_asesor ON evaluaciones(asesor_id);
CREATE INDEX IF NOT EXISTS idx_evaluaciones_opportunity ON evaluaciones(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_evaluaciones_fecha ON evaluaciones(fecha);
CREATE INDEX IF NOT EXISTS idx_calificaciones_evaluacion ON calificaciones_bloque(evaluacion_id);
CREATE INDEX IF NOT EXISTS idx_oportunidades_opportunity ON oportunidades(opportunity_id);
