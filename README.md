# Centauro

Sistema multi-agente para auditar la calidad de llamadas de venta consultiva (OBS Business School). Procesa transcripciones, aplica RAG con manuales, evalua la conversacion por bloques con LLM, valida evidencias (Sheriff) y genera reportes en JSON/PDF. Registra el costo en tokens.

## Objetivo tecnico
Centauro automatiza una auditoria QA de llamadas de venta consultiva. Su diseno prioriza:
- Evidencia literal y trazable a la transcripcion.
- Reduccion de tokens (batching + extractos + top-k reducido).
- Control de alucinaciones (Sheriff).
- Reportes ejecutivos consistentes en JSON/PDF.

## Arquitectura (vista tecnica)
- **Entrada / Orquestacion**: `main.py` coordina ingest, RAG, analisis y salida.
- **Core**: `centauro/core/`
  - `orchestrator.py`: pipeline multi-agente, batching y Sheriff.
  - `rag_dynamic.py`: RAG adaptativo por bloque con cache.
  - `config_agents.py`: politica de optimizacion (batch, extractos, top-k).
- **Agentes**: `centauro/agents/`
  - `diarization_agent.py`: diariza transcripciones en distintos formatos.
  - agentes por bloque: apertura, deteccion, presentacion, objeciones, cierre, estilo.
  - `base_agent.py`: interfaz comun + utilidades de validacion.
- **Servicios**:
  - `centauro/llm_client.py`: acceso OpenAI, control de costos.
  - `centauro/config.py`: rutas, modelos, entorno.
- **Datos**:
  - `centauro/schema.py`: schema del reporte (Pydantic).
  - `centauro/privacy.py`: redaccion de PII antes de analisis.
- **Outputs**:
  - `centauro/reports.py`: render PDF corporativo.
  - JSON y PDF en `outputs/Reportes_JSON` y `outputs/Reportes_PDF`.

## Flujo end-to-end (pipeline)
1. **Ingest**: `main.py` crea directorios y llama a `indexar_documentacion()`.
2. **Lectura**: detecta formato de transcripcion (Word/VTT/TXT) y limpia metadatos.
3. **Diarizacion**: `DiarizationAgent` etiqueta ASESOR/LEAD.
4. **Contexto**: `DynamicRAGAgent` extrae temas y recupera fragmentos relevantes.
5. **Evaluacion**:
   - Batch ligero: apertura, cierre, legal (extractos).
   - Batch pesado: deteccion, presentacion, objeciones, estilo (transcripcion completa).
6. **Sheriff**: valida evidencia literal, penaliza notas si hay alucinaciones.
7. **Sintesis**: calcula score global y genera feedback.
8. **Salida**: JSON + PDF + registro de costos.

## Trade-offs y decisiones
- **Batching** reduce llamadas/tokens pero exige prompts con formato JSON estricto.
- **Extractos** minimizan costo en bloques ligeros pero pueden omitir contexto si hay cortes.
- **RAG top-k reducido** disminuye tokens a costa de menor cobertura documental.
- **Sheriff** prioriza evidencia literal, puede bajar notas incluso con buen analisis semantico.

## Componentes principales

### Entrada y orquestacion
- `main.py`: punto de entrada. Prepara carpetas, indexa manuales, procesa transcripciones y genera reportes.

### Core
- `centauro/core/orchestrator.py`: pipeline multi-agente y Sheriff.
- `centauro/core/rag_dynamic.py`: RAG adaptativo por bloque con cache.
- `centauro/core/config_agents.py`: batching, extractos y top-k reducido.

### RAG
- `centauro/rag.py`: indexacion de manuales en ChromaDB y busqueda de contexto.
- `centauro/inspect_rag.py`: inspeccion de la base vectorial.

### Agentes evaluadores
- `centauro/agents/base_agent.py`: clase base y utilidades.
- `apertura_agent.py`: saludo, presentacion, rapport.
- `deteccion_agent.py`: preguntas y escucha activa.
- `presentacion_agent.py`: beneficios vs caracteristicas y encaje.
- `objeciones_agent.py`: manejo de dudas y resistencias.
- `cierre_agent.py`: proximos pasos y tecnica de cierre.
- `estilo_agent.py`: tono, vocabulario, empatia, ritmo.

### Diarizacion
- `centauro/agents/diarization_agent.py`: soporta Word, VTT con speakers, VTT con UUID y texto libre.
- `centauro/diarization_legacy.py`: version anterior basada en chunks + LLM.

### Datos y privacidad
- `centauro/schema.py`: esquema Pydantic del reporte.
- `centauro/privacy.py`: redaccion de PII (email, telefono, DNI/NIE, IBAN).

### Reportes
- `centauro/reports.py`: PDF corporativo con score global, tarjetas por bloque y feedback.

### LLM y costos
- `centauro/llm_client.py`: llamadas a OpenAI y registro de costos en `outputs/control_gastos.csv`.

## Estructura de carpetas
```
.
|-- main.py
|-- requirements.txt
|-- inputs/
|   |-- docs/
|   |-- transcripts/
|-- outputs/
|   |-- Reportes_JSON/
|   |-- Reportes_PDF/
|-- centauro/
|   |-- agents/
|   |-- core/
|   |-- config.py
|   |-- llm_client.py
|   |-- rag.py
|   |-- reports.py
|   |-- schema.py
|   |-- privacy.py
|   |-- inspect_rag.py
|   |-- analyze_legacy.py
|   |-- diarization_legacy.py
|-- tests/
```

## Requisitos
- Python 3.10+ recomendado.
- Variables de entorno en `.env`:
  - `OPENAI_API_KEY`

Instalacion:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso rapido
1. Coloca manuales `.txt` en `inputs/docs`.
2. Coloca transcripciones en `inputs/transcripts`.
3. Ejecuta:
```bash
python main.py
```

## Tests
```bash
python tests\test_diarization_agent.py
python tests\test_optimizaciones.py
```

## Ejemplos de salida

### Ejemplo de JSON (fragmento)
```json
{
  "asesor": "Juan Perez",
  "puntuacion_global_1_5": 3.6,
  "evaluacion_por_bloques": [
    {
      "bloque": "Apertura",
      "puntuacion_1_5": 4,
      "observabilidad": "ALTA",
      "confianza": 0.9,
      "evidencia_principal": "[ASESOR]: Hola, soy Ana de OBS Business School, gracias por tu tiempo.",
      "evidencias_extra": [
        "[ASESOR]: Te llamo por tu interes en el programa de Data Science."
      ],
      "razonamiento": "Presentacion clara y saludo profesional con encuadre inicial.",
      "recomendacion_accionable": "Agregar validacion explicita de agenda antes de iniciar."
    }
  ],
  "feedback_resumido": {
    "fortalezas": ["Apertura"],
    "areas_mejora": ["Cierre y siguiente paso"]
  }
}
```

### Ejemplo de PDF (contenido esperado)
- Score global 1-5 en cabecera.
- Tarjetas por bloque con nota, evidencia y recomendacion accionable.
- Pagina final con fortalezas y areas de mejora.

## Diagrama de flujo (texto)
```
inputs/docs --> RAG (ChromaDB) ---------------------------+
inputs/transcripts --> lectura/limpieza --> diarizacion   |
                                  |                      |
                                  +--> RAG dinamico -----+
                                  |                      |
                                  +--> batch ligero ------> Sheriff --> sintesis --> JSON/PDF
                                  |
                                  +--> batch pesado ------^
```

## Troubleshooting

### 1) No se generan reportes
- Verifica que haya archivos en `inputs/transcripts`.
- Revisa que `outputs/` exista (main.py lo crea).
- Si hay errores LLM, valida `OPENAI_API_KEY` en `.env`.

### 2) RAG devuelve vacio
- Asegura manuales `.txt` en `inputs/docs`.
- Ejecuta `python main.py` para reindexar.
- Usa `centauro/inspect_rag.py` para inspeccionar colecciones.

### 3) JSON malformado desde el LLM
- Revisa logs de errores en consola.
- Asegura prompts con `response_format=json_object`.
- Reduce temperatura (ya esta en 0).

### 4) Evidencias no verificables (Sheriff ajusta notas)
- Revisa si la transcripcion esta bien diarizada.
- Si hay ruido/errores de diarizacion, mejora la entrada o ajusta umbral de validacion.

### 5) Errores de dependencias
- Confirma el entorno activo: `python -V` y `pip -V`.
- Reinstala: `pip install -r requirements.txt`.

## Configuracion avanzada
- `centauro/core/config_agents.py`:
  - `MODO_BATCH`: alterna batch vs evaluacion individual.
  - `RAG_TOP_K`: controla tamano del contexto recuperado.
  - `EXTRACTOS`: ajusta longitudes por bloque.
- `centauro/llm_client.py`:
  - `MODEL_NAME` y tarifas de costo.
  - Registro de gastos en `outputs/control_gastos.csv`.

## Notas de diseno
- Modo batch reduce tokens y llamadas a la API.
- Sheriff ajusta puntuaciones si no encuentra evidencia literal.
- RAG dinamico reduce top-k y cachea contextos.
