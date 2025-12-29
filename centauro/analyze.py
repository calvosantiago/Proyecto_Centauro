import json
import re
from .config import settings
from .rag import buscar_contexto
from .llm_client import consultar_gpt
from .schema import ReporteCalidad, ItemEvaluacion
from .privacy import redact_pii

# --- SISTEMA DE PONDERACIÓN ---
PESOS = {
    "CRITICO": 10.0, 
    "ALTA": 5.0,     
    "MEDIA": 3.0,    
    "BAJA": 1.0      
}

def limpiar_tokens(texto):
    """Limpieza base."""
    if not texto: return []
    texto = texto.lower()
    texto = texto.replace("€", "").replace("$", "").replace(".", "").replace(",", "")
    texto = re.sub(r'[^\w\s]', '', texto)
    tokens = texto.split()
    stopwords = {'de', 'el', 'la', 'que', 'en', 'y', 'a', 'los', 'un', 'una', 'es', 'por', 'del', 'con', 'las', 'al', 'lo', 'se', 'su', 'mi'}
    return [t for t in tokens if t not in stopwords and len(t) > 1]

def validar_por_tokens(reporte_json, texto_original):
    """
    SHERIFF 4.3: Validación Existencial + Validación Semántica (Legal).
    """
    tokens_texto_original = set(limpiar_tokens(texto_original))
    
    lista_fuertes = reporte_json.get("puntos_fuertes") or []
    lista_mejora = reporte_json.get("areas_mejora") or []
    todos_items = lista_fuertes + lista_mejora
    
    reporte_json["puntos_fuertes"] = []
    reporte_json["areas_mejora"] = []

    for item in todos_items:
        # Defaults para Pydantic
        if "referencia_manual" not in item: item["referencia_manual"] = "General"
        if "feedback" not in item: item["feedback"] = "Revisión automática"

        evidencia = item.get("cita_evidencia", "")
        criterio_nombre = item.get("criterio", "").lower()
        cumple_original = item.get("cumple", False)
        
        # 1. Filtro Básico
        if not cumple_original or "NO ENCONTRADO" in evidencia or not evidencia:
            item["cumple"] = False
            reporte_json["areas_mejora"].append(item)
            continue

        tokens_evidencia = limpiar_tokens(evidencia)
        
        if not tokens_evidencia:
            item["cumple"] = False
            reporte_json["areas_mejora"].append(item)
            continue

        # 2. CHECK EXISTENCIAL: ¿Está la frase en el audio?
        aciertos = 0
        for token in tokens_evidencia:
            if token in tokens_texto_original:
                aciertos += 1
        
        ratio = aciertos / len(tokens_evidencia)
        
        # Umbral base de existencia
        umbral_existencia = 0.60 
        if len(tokens_evidencia) <= 3: umbral_existencia = 0.80

        existe_en_audio = ratio >= umbral_existencia

        # 3. CHECK SEMÁNTICO (NUEVO): ¿Tiene sentido lo que dice?
        es_legal = "legal" in criterio_nombre or "grabación" in criterio_nombre
        contenido_valido = True
        
        if es_legal:
            # Palabras raíz obligatorias para que sea un aviso legal
            palabras_clave_legal = ["grab", "monit", "calidad", "aviso", "legal"]
            # Verificamos si ALGUNA palabra clave está en la evidencia encontrada
            tiene_keyword = any(k in evidencia.lower() for k in palabras_clave_legal)
            
            if not tiene_keyword:
                print(f"   🚨 SHERIFF SEMÁNTICO: '{evidencia}' existe, pero NO es un aviso legal.")
                contenido_valido = False
                item["razonamiento"] = "La frase existe pero NO contiene términos legales (grabar, calidad, monitorizar)."

        # 4. VEREDICTO FINAL
        if existe_en_audio and contenido_valido:
            item["cumple"] = True
            reporte_json["puntos_fuertes"].append(item)
        else:
            # Si falló por existencia
            if not existe_en_audio:
                print(f"   🚨 SHERIFF EXISTENCIAL: '{evidencia}' no está en el audio (Ratio: {ratio:.2f})")
                item["razonamiento"] = f"Alucinación: La frase no existe en el audio (Coincidencia: {ratio:.0%})"
            
            item["cumple"] = False
            item["cita_evidencia"] = f"NO VALIDADO: {evidencia}"
            reporte_json["areas_mejora"].append(item)

    return reporte_json

def calcular_nota_ponderada(puntos_fuertes, areas_mejora):
    puntos_totales = 0.0
    puntos_posibles = 0.0
    todos_items = puntos_fuertes + areas_mejora
    if not todos_items: return 0.0

    for item in todos_items:
        importancia = getattr(item, 'importancia', 'MEDIA').upper()
        cumple = getattr(item, 'cumple', False)
        peso = PESOS.get(importancia, 1.0)
        puntos_posibles += peso
        if cumple: puntos_totales += peso
            
    if puntos_posibles == 0: return 0.0
    nota = (puntos_totales / puntos_posibles) * 10
    return round(nota, 2)

def analizar_entrevista(nombre_archivo, texto_transcripcion):
    print(f"🔍 Analizando: {nombre_archivo}")
    
    # Privacidad
    resultado_privacidad = redact_pii(texto_transcripcion)
    texto_seguro = resultado_privacidad.text
    
    # Debug
    debug_dir = settings.OUTPUTS_DIR / "Input_Debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    with open(debug_dir / f"DEBUG_{nombre_archivo}.txt", "w", encoding="utf-8") as f:
        f.write(texto_seguro)

    # RAG
    contexto_manual = buscar_contexto("Argumentación producto metodología ranking partners networking cierre objeciones legal")
    
    # Limpieza nombre
    base = nombre_archivo.rsplit(".", 1)[0]
    if base.startswith("entrevista_"):
        base = base[len("entrevista_"):]
    nombre_limpio = base.replace("_", " ").strip()

    # --- TU PROMPT DETALLADO Y RICO ---
    ejemplo_json = """
    {
        "asesor": "Paola Suarez",
        "resumen_ejecutivo": "...",
        "puntos_fuertes": [
            { "criterio": "1. Inicio (Saludo)", "cumple": true, "cita_evidencia": "Hola soy Paola", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "BAJA" },
            { "criterio": "6. Legal (Grabación)", "cumple": true, "cita_evidencia": "Esta llamada se graba", "referencia_manual": "Manual Legal", "feedback": "Cumple normativa", "razonamiento": "...", "importancia": "MEDIA" }
        ],
        "areas_mejora": [],
        "nota_final_0_10": 0 
    }
    """

    sistema = f"""
    Eres un AUDITOR DE VENTAS CONSULTIVAS.
    
    TUS FUENTES:
    1. REGLAS: <MANUAL>{contexto_manual}</MANUAL>
    2. DATOS: <AUDIO_REAL>El texto del usuario</AUDIO_REAL>
    
    METADATOS: Asesor: "{nombre_limpio}"
    
    MANDATO OBLIGATORIO: EVALÚA ESTAS 6 FASES (NO TE SALTES NINGUNA).
    
    1. INICIO (Saludo) -> [Imp: BAJA]
       - Busca: Cualquier saludo cordial ("Hola", "Buenos días").
       
    2. SONDEO (Necesidades) -> [Imp: ALTA]
       - Busca: Preguntas abiertas sobre el alumno (perfil, objetivos, trabajo).
       
    3. ARGUMENTACIÓN (Valor) -> [Imp: ALTA]
       - ¿Mencionó ALGÚN valor diferencial? (Ranking, Metodología, Claustro, Título, Online).
       - No hace falta que diga todo. Con argumentar el valor es suficiente.
       
    4. OBJECIONES / ECONOMÍA -> [Imp: ALTA]
       - ¡IMPORTANTE! NO BUSQUES UN PRECIO FIJO.
       - Busca CUALQUIER conversación económica: Precios (5000, 7500, 12000...), palabras como "Euros", "Dólares", "Inversión", "Matrícula", "Beca", "Descuento", "Abono".
       - Si habla de dinero o resuelve dudas -> TRUE.
       
    5. CIERRE (Siguientes Pasos) -> [Imp: ALTA]
       - ¿Propuso avanzar? (Comité, Documentación, Validación perfil).
       - ¿Propuso formas de pago? (Financiación, Contado).
       - Cualquiera vale como Cierre.
       
    6. LEGAL (Grabación) -> [Imp: MEDIA]
       - CRÍTICO: Busca palabras raíz: "Grabar", "Calidad", "Monitor", "Grabación".
       - SI NO APARECEN ESAS PALABRAS, MARCA FALSE. NO INVENTES LA FRASE.

    REGLA DE EVIDENCIA (EXTRACCIÓN):
    - Extrae el fragmento del audio donde ocurre la acción.
    - No corrijas errores del audio. Cópialo tal cual.

    Estructura JSON obligatoria:
    {ejemplo_json}
    """
    
    usuario = f"<AUDIO>\n{texto_seguro}\n</AUDIO>"
    
    print("🧠 Consultando a GPT-4o-mini...")
    respuesta_raw = consultar_gpt(sistema, usuario, referencia_log=nombre_archivo)
    
    try:
        respuesta_limpia = respuesta_raw.replace("```json", "").replace("```", "").strip()
        datos = json.loads(respuesta_limpia)
        if "ReporteCalidad" in datos: datos = datos["ReporteCalidad"]
        
        print(f"👮‍♂️ Aplicando validación SEMÁNTICA (Sheriff 4.3)...")
        datos_validados = validar_por_tokens(datos, texto_seguro)
        
        puntos_fuertes = [ItemEvaluacion(**i) for i in datos_validados.get("puntos_fuertes", [])]
        areas_mejora = [ItemEvaluacion(**i) for i in datos_validados.get("areas_mejora", [])]
        
        nota = calcular_nota_ponderada(puntos_fuertes, areas_mejora)
        
        reporte = ReporteCalidad(
            asesor=datos.get("asesor", nombre_limpio),
            resumen_ejecutivo=datos.get("resumen_ejecutivo", "Sin resumen"),
            puntos_fuertes=puntos_fuertes,
            areas_mejora=areas_mejora,
            nota_final_0_10=nota
        )
        
        json_path = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{nombre_archivo}_reporte.json"
        json_path.parent.mkdir(exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(reporte.model_dump_json(indent=2))
            
        print(f"✅ Reporte generado. Nota: {nota}/10")
        return reporte

    except Exception as e:
        print(f"❌ Error procesando datos: {e}")
        return None