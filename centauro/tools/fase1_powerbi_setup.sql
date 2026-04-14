-- ============================================================
-- Centauro - Fase 1: Setup Power BI
-- Ejecutar en SQL Editor de Supabase (una sola vez)
-- ============================================================

-- ------------------------------------------------------------
-- PASO 1: Sincronizar columnas de evaluaciones
-- (si la tabla fue creada antes de añadir factor_determinante_compra
--  y fecha_seguimiento, o si tiene columnas antiguas)
-- ------------------------------------------------------------
ALTER TABLE evaluaciones
    DROP COLUMN IF EXISTS transcripcion_path,
    DROP COLUMN IF EXISTS fase_funnel,
    DROP COLUMN IF EXISTS resultado_general,
    DROP COLUMN IF EXISTS reporte_json_path,
    ADD COLUMN IF NOT EXISTS factor_determinante_compra TEXT,
    ADD COLUMN IF NOT EXISTS fecha_seguimiento TIMESTAMPTZ;

-- Añadir columna aliases a asesores (si no existe)
ALTER TABLE asesores
    ADD COLUMN IF NOT EXISTS aliases JSONB DEFAULT '[]';

-- ------------------------------------------------------------
-- PASO 2: Vistas para Power BI
-- ------------------------------------------------------------

-- Vista principal: una fila por evaluación con nombre del asesor
CREATE OR REPLACE VIEW v_evaluaciones_detalle AS
SELECT
    e.id                            AS evaluacion_id,
    e.fecha,
    e.opportunity_id,
    e.calificacion_global,
    -- Valor numérico para ordenar en gráficos (MALO=1, MEJORABLE=2, BUENO=3)
    CASE e.calificacion_global
        WHEN 'BUENO'     THEN 3
        WHEN 'MEJORABLE' THEN 2
        WHEN 'MALO'      THEN 1
        ELSE NULL
    END                             AS calificacion_global_num,
    e.archivo_origen,
    e.perfil_lead,
    e.objetivo_del_lead,
    e.factor_determinante_compra,
    e.barreras_principales,
    e.fecha_seguimiento,
    e.llamadas_api,
    e.tiempo_analisis_seg,
    a.nombre                        AS asesor_nombre
FROM evaluaciones e
JOIN asesores a ON a.id = e.asesor_id;

-- Vista detalle de bloques con calificación numérica
CREATE OR REPLACE VIEW v_calificaciones_detalle AS
SELECT
    cb.id,
    cb.evaluacion_id,
    cb.bloque,
    cb.calificacion,
    -- Valor numérico para ordenar correctamente en gráficos
    CASE cb.calificacion
        WHEN 'BUENO'     THEN 3
        WHEN 'MEJORABLE' THEN 2
        WHEN 'MALO'      THEN 1
        ELSE NULL
    END                             AS calificacion_num,
    cb.observabilidad,
    cb.confianza,
    cb.evidencia_principal,
    cb.razonamiento,
    cb.recomendacion_accionable,
    -- Datos de la evaluación padre
    e.fecha,
    e.opportunity_id,
    e.calificacion_global,
    a.nombre                        AS asesor_nombre
FROM calificaciones_bloque cb
JOIN evaluaciones e ON e.id = cb.evaluacion_id
JOIN asesores a ON a.id = e.asesor_id;

-- ------------------------------------------------------------
-- PASO 3: Usuario read-only para Power BI
-- Cambia 'tu_password_seguro' por una contraseña real antes de ejecutar
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
        CREATE USER powerbi_reader WITH PASSWORD 'tu_password_seguro';
    END IF;
END
$$;

-- Permisos sobre tablas y vistas existentes
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_reader;

-- Permisos automáticos para tablas/vistas futuras
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO powerbi_reader;

-- ------------------------------------------------------------
-- VERIFICACIÓN: ejecuta esto al final para confirmar
-- ------------------------------------------------------------
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'evaluaciones' ORDER BY ordinal_position;

-- SELECT table_name FROM information_schema.views
-- WHERE table_schema = 'public';
