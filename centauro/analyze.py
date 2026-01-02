import json
import re
from pathlib import Path
from .config import settings
from .rag import buscar_contexto
from .llm_client import consultar_gpt
from .schema import (
    ReporteCalidad, MetaData, ResumenContextual, 
    EventoClave, BloqueEvaluacion, ScorecardFinal, FeedbackResumido
)
from .privacy import redact_pii

try:
    from rapidfuzz import fuzz
except ImportError:
    print("⚠️ FALTA RAPIDFUZZ. Ejecuta: pip install rapidfuzz")
    fuzz = None

# --- CONFIGURACIÓN DE PESOS OBS ---
PESOS_BLOQUES = {
    "apertura": 1.0,          # MEDIA
    "necesidades": 3.0,       # CRITICO
    "presentacion": 2.0,      # ALTA
    "objeciones": 3.0,        # CRITICO
    "cierre": 3.0,            # CRITICO
    "estilo": 2.0,            # ALTA
    "legal": 1.0              # BAJA
}

def limpiar_texto_base(texto: str):
    """Normalización para fuzzy matching."""
    if not texto: return ""
    return texto.lower().strip().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")

def extraer_json_robusto(respuesta_raw: str) -> dict:
    if not respuesta_raw: raise ValueError("Respuesta vacía")
    limpio = respuesta_raw.replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", limpio, flags=re.S)
    if not m:
        try: return json.loads(limpio)
        except: raise ValueError("No JSON found")
    return json.loads(m.group(0))

def validar_y_auditar_sheriff(reporte: ReporteCalidad, texto_transcripcion: str):
    """
    ETAPA AUDITOR (SHERIFF V3):
    1. Verifica existencia de evidencias (Timeline y Bloques).
    2. Aplica reglas de negocio "Off-Record" (si recording_started_late).
    3. Penaliza bloques sin evidencia real.
    """
    texto_lower = limpiar_texto_base(texto_transcripcion)
    
    # 1. VERIFICAR FLAG "RECORDING STARTED LATE"
    # Si la IA detectó que empezó tarde, forzamos NULA observabilidad en Apertura y Legal
    inicio_tardio = reporte.meta.flags_tecnicos.get("recording_started_late", False)
    
    # 2. AUDITAR BLOQUES
    for bloque in reporte.evaluacion_por_bloques:
        # A) Regla Off-Record Automática
        es_bloque_afectado = bloque.id_bloque in ["apertura", "legal"]
        if inicio_tardio and es_bloque_afectado:
            bloque.puntuacion_1_5 = None # Anular nota
            bloque.observabilidad = "NULA (OFF-RECORD)"
            bloque.estado_evaluacion = "OFF_RECORD"
            bloque.razonamiento = "[SISTEMA] Grabación iniciada tardíamente. Se asume cumplimiento previo."
            continue

        # B) Validación de Evidencias (Fuzzy)
        evidencias_reales = []
        for cita in bloque.evidencias_validadas:
            if len(cita) < 5: continue
            
            clean_cita = limpiar_texto_base(cita)
            # Umbral 65: Tolerancia a errores de transcripción humanos
            if fuzz:
                ratio = fuzz.token_set_ratio(clean_cita, texto_lower)
                valido = ratio >= 65
            else:
                valido = clean_cita in texto_lower
                
            if valido:
                evidencias_reales.append(cita)
        
        # C) Penalización por Alucinación
        # Si la IA dio nota > 1 pero no hay evidencias reales -> Bajamos a 1
        # Excepción: Bloques "Estilo" a veces son subjetivos, somos más laxos (permitimos 0 evidencias si razonamiento es sólido)
        es_subjetivo = bloque.id_bloque == "estilo"
        
        if bloque.puntuacion_1_5 is not None and bloque.puntuacion_1_5 > 1:
            if len(evidencias_reales) == 0 and not es_subjetivo:
                print(f"   🚨 Sheriff: Alucinación en '{bloque.id_bloque}'. Nota bajada a 1.")
                bloque.puntuacion_1_5 = 1
                bloque.razonamiento += " [AUDITOR: Evidencia no encontrada en audio. Penalización aplicada.]"
                bloque.estado_evaluacion = "SIN_EVIDENCIA"
            
            # Penalización Soft Skills (Necesidades/Objeciones) si hay poca evidencia
            elif bloque.id_bloque in ["necesidades", "objeciones"] and len(evidencias_reales) < 2 and bloque.puntuacion_1_5 >= 4:
                bloque.puntuacion_1_5 -= 1
                bloque.razonamiento += " [AUDITOR: Se reduce nota por falta de evidencia distribuida.]"

        # Actualizamos la lista con solo las validadas
        bloque.evidencias_validadas = evidencias_reales

    return reporte

def calcular_scorecard_final(reporte: ReporteCalidad):
    """Calcula la nota ponderada ignorando los bloques OFF_RECORD."""
    total_puntos = 0.0
    total_peso = 0.0
    
    for bloque in reporte.evaluacion_por_bloques:
        # Ignorar Off-Record o Nulos
        if bloque.puntuacion_1_5 is None: continue
        
        peso = PESOS_BLOQUES.get(bloque.id_bloque, 1.0)
        
        # Normalización OBS (1-5) -> (0-100%)
        # 1=0, 2=0.25, 3=0.5, 4=0.75, 5=1.0
        puntos_norm = (bloque.puntuacion_1_5 - 1) / 4.0
        
        total_puntos += (puntos_norm * 10) * peso
        total_peso += 10 * peso
        
    if total_peso == 0:
        nota_final = 0.0
    else:
        nota_final = round((total_puntos / total_peso) * 10, 2)
        
    # Asignar al reporte
    reporte.scorecard_final.promedio_calculado_1_5 = 0 # (Opcional, calculable inverso)
    reporte.scorecard_final.nota_final_0_10 = nota_final
    
    # Cualitativo
    if nota_final >= 9: reporte.scorecard_final.calificacion_cualitativa = "A (Excelencia)"
    elif nota_final >= 7.5: reporte.scorecard_final.calificacion_cualitativa = "B (Bueno)"
    elif nota_final >= 5: reporte.scorecard_final.calificacion_cualitativa = "C (Aprobado)"
    else: reporte.scorecard_final.calificacion_cualitativa = "D (Deficiente)"
    
    return reporte

def analizar_entrevista(nombre_archivo, texto_transcripcion):
    print(f"🔍 Analizando (Centauro V3 Tridente): {nombre_archivo}")
    
    res_priv = redact_pii(texto_transcripcion)
    texto_seguro = res_priv.text
    
    # Debug
    debug_dir = settings.OUTPUTS_DIR / "Input_Debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    nombre_safe = re.sub(r'[^\w\-_]', '_', Path(nombre_archivo).stem)[:50]
    with open(debug_dir / f"DEBUG_{nombre_safe}.txt", "w", encoding="utf-8") as f:
        f.write(texto_seguro)

    contexto_manual = buscar_contexto("Venta consultiva metodologia cierre empatia legal")
    base_nombre = Path(nombre_archivo).stem.replace("_", " ")

    # --- PROMPT ARQUITECTÓNICO V3 (Extractor -> Evaluador) ---
    sistema = f"""
ACTÚA COMO: Head of Sales Coaching de OBS Business School.
OBJETIVO: Auditar una llamada de venta consultiva.
TU ENFOQUE: Severidad media-alta. Buscas calidad real, no cumplimiento robótico.

### FASE 1: EXTRACTOR DE HECHOS (La Verdad)
Primero, analiza el texto y extrae los hechos objetivos.
- **Detección de Inicio Tardío:** ¿La llamada empieza con saludos ("Hola", "Buenos días") o ya están hablando de temas profundos?
  - Si empieza ya iniciada -> `recording_started_late: true`.
- **Línea de Tiempo:** Identifica 3-6 momentos clave (Objeción de precio, Cierre, Pregunta de dolor). Cita textualmente.

### FASE 2: EVALUADOR (El Juicio)
Evalúa del 1 al 5 cada bloque usando SOLO los hechos extraídos.

**RÚBRICA OBS (Estándar de Oro):**
- **1 (Deficiente):** No lo hace o es contraproducente.
- **3 (Cumplidor):** Correcto pero robótico/administrativo.
- **5 (Excelente):** Estratégico, empático, personalizado y persuasivo.

**BLOQUES A EVALUAR:**
1. `apertura`: Presentación y conexión. (Si `started_late` -> Nota null).
2. `necesidades`: Preguntas profundas vs superficiales.
3. `presentacion`: Vinculación de beneficios vs lectura de temario.
4. `objeciones`: Empatía y revalorización vs discusión.
5. `cierre`: Proactividad y compromiso de pago.
6. `estilo`: Seguridad y tono experto.
7. `legal`: Mención de grabación. (Si `started_late` -> Nota null).

**REGLAS DE SALIDA:**
- Si no hay evidencia suficiente, sé honesto: baja confianza o nota baja.
- En Soft Skills (Necesidades, Objeciones), aporta MÚLTIPLES evidencias en la lista.

FUENTES: <MANUAL>{contexto_manual}</MANUAL>
"""
    
    # JSON Schema implícito en la instrucción (reforzamos con ejemplo one-shot si fuera necesario, 
    # pero usaremos response_format json_object y Pydantic se encarga luego).
    # Para mayor robustez, inyectamos la estructura esperada:
    
    estructura_json = """
    ESTRUCTURA JSON OBLIGATORIA:
    {
      "meta": { "flags_tecnicos": { "recording_started_late": boolean } },
      "resumen_contextual": { "perfil_lead": "...", "fase_funnel": "..." },
      "timeline_momentos_clave": [ { "fase": "...", "evento": "...", "cita_evidencia": "..." } ],
      "evaluacion_por_bloques": [
        { 
          "id_bloque": "necesidades", "titulo": "Detección de Necesidades",
          "puntuacion_1_5": 4, "observabilidad": "ALTA",
          "evidencias_validadas": ["Cita 1...", "Cita 2..."],
          "razonamiento": "..."
        }
      ],
      "feedback_resumido": { "fortalezas": [], "areas_mejora": [] }
    }
    """
    
    prompt_completo = sistema + "\n" + estructura_json
    usuario = f"<TRANSCRIPCION>\n{texto_seguro}\n</TRANSCRIPCION>"
    
    print("🧠 Consultando a GPT-4o-mini (Tridente V3)...")
    respuesta_raw = consultar_gpt(prompt_completo, usuario, referencia_log=nombre_archivo)
    
    try:
        data = extraer_json_robusto(respuesta_raw)
        
        # Conversión a Pydantic (Validación de estructura)
        # Nota: Ajustamos el modelo si faltan campos opcionales
        reporte = ReporteCalidad(**data)
        reporte.asesor = base_nombre # Rellenamos nombre fichero

        # --- ETAPA 3: AUDITOR (Sheriff) ---
        print("👮‍♂️ Sheriff V3: Auditando evidencias y Off-Record...")
        reporte = validar_y_auditar_sheriff(reporte, texto_seguro)
        
        # Cálculo final
        reporte = calcular_scorecard_final(reporte)

        # Guardar
        ruta_json = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{nombre_safe}_reporte.json"
        ruta_json.parent.mkdir(exist_ok=True)
        
        with open(ruta_json, "w", encoding="utf-8") as f:
            f.write(reporte.model_dump_json(indent=2))
            
        print(f"✅ Reporte Generado: {ruta_json.name}")
        print(f"⭐️ NOTA FINAL: {reporte.scorecard_final.nota_final_0_10}/10")
        
        return reporte

    except Exception as e:
        print(f"❌ Error procesando {nombre_archivo}: {e}")
        # import traceback; traceback.print_exc()
        return None