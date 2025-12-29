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
    """
    Limpieza inteligente para el Sheriff 4.1:
    - Quita símbolos de moneda (€, $) y puntuación (., ,).
    - Permite que '5.000' coincida con '5000'.
    """
    if not texto: return []
    
    # 1. Pasamos a minúsculas
    texto = texto.lower()
    
    # 2. Reemplazamos símbolos de moneda y puntos de miles por nada
    # Así "7.500€" se convierte en "7500"
    texto = texto.replace("€", "").replace("$", "").replace(".", "").replace(",", "")
    
    # 3. Quitamos cualquier otro caracter raro
    texto_limpio = re.sub(r'[^\w\s]', '', texto)
    
    tokens = texto_limpio.split()
    
    # 4. Filtramos palabras vacías (stopwords)
    stopwords = {'de', 'el', 'la', 'que', 'en', 'y', 'a', 'los', 'un', 'una', 'es', 'por', 'del', 'con', 'las', 'al', 'lo', 'se'}
    
    return [t for t in tokens if t not in stopwords and len(t) > 1]

def validar_por_tokens(reporte_json, texto_original):
    """SHERIFF 4.1: Validación robusta para cifras y descuentos."""
    
    # Limpiamos el texto original igual que la evidencia (quitando puntos de miles, etc)
    tokens_texto_original = set(limpiar_tokens(texto_original))
    
    # Recuperamos todos los items para procesar
    todos_items = reporte_json.get("puntos_fuertes", []) + reporte_json.get("areas_mejora", [])
    
    # Reiniciamos listas
    reporte_json["puntos_fuertes"] = []
    reporte_json["areas_mejora"] = []

    for item in todos_items:
        evidencia = item.get("cita_evidencia", "")
        cumple_original = item.get("cumple", False)
        
        # Si ya venía como fallo o no tiene evidencia, pasa directo a mejora
        if not cumple_original or "NO ENCONTRADO" in evidencia:
            item["cumple"] = False
            reporte_json["areas_mejora"].append(item)
            continue

        tokens_evidencia = limpiar_tokens(evidencia)
        
        if not tokens_evidencia or len(evidencia) < 3:
            item["cumple"] = False
            item["feedback"] = "IA Error: Evidencia insuficiente."
            reporte_json["areas_mejora"].append(item)
            continue

        # CONTAMOS ACIERTOS (Intersección de conjuntos)
        aciertos = 0
        for token in tokens_evidencia:
            if token in tokens_texto_original:
                aciertos += 1
        
        ratio_acierto = aciertos / len(tokens_evidencia)
        
        # Umbral flexible (60%): Permite que la IA se equivoque en alguna palabra, 
        # pero exige que los números y conceptos clave estén.
        if ratio_acierto >= 0.60:
            item["cumple"] = True
            reporte_json["puntos_fuertes"].append(item)
        else:
            print(f"   🚨 CITA RECHAZADA: '{evidencia}' (Coincidencia: {ratio_acierto:.2%})")
            item["cumple"] = False
            item["cita_evidencia"] = f"NO VALIDADO: {evidencia}"
            item["razonamiento"] = "La evidencia citada no coincide suficientemente con el audio."
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
    print(f"🔍 Buscando reglas para: {nombre_archivo}")
    
    # 1. Privacidad
    resultado_privacidad = redact_pii(texto_transcripcion)
    texto_seguro = resultado_privacidad.text
    
    # 2. RAG
    contexto_manual = buscar_contexto("Argumentación producto metodología ranking partners networking cierre objeciones legal")

    # 3. Prompt
    base = nombre_archivo.rsplit(".", 1)[0]
    if base.startswith("entrevista_"):
        base = base[len("entrevista_"):]
    nombre_limpio = base.replace("_", " ").strip()

    ejemplo_json = """
    {
        "asesor": "Paola Suarez",
        "resumen_ejecutivo": "...",
        "puntos_fuertes": [
            { "criterio": "1. Inicio (Saludo)", "cumple": true, "cita_evidencia": "Hola soy Paola", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "BAJA" },
            { "criterio": "2. Sondeo (Necesidades)", "cumple": true, "cita_evidencia": "¿Qué experiencia tienes?", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "ALTA" },
            { "criterio": "3. Argumentación (Valor)", "cumple": true, "cita_evidencia": "Tenemos el Ranking X", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "ALTA" },
            { "criterio": "4. Objeciones / Precio", "cumple": true, "cita_evidencia": "La inversión se queda en 5200", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "ALTA" },
            { "criterio": "5. Cierre (Siguientes Pasos)", "cumple": true, "cita_evidencia": "Pasamos a comité", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "ALTA" },
            { "criterio": "6. Legal (Grabación)", "cumple": true, "cita_evidencia": "Esta llamada se graba", "referencia_manual": "...", "feedback": "...", "razonamiento": "...", "importancia": "MEDIA" }
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
       - Busca palabras raíz: "Grabar", "Calidad", "Monitor".
       - Si no está -> FALSE.

    REGLA DE EVIDENCIA (EXTRACCIÓN):
    - Extrae el fragmento del audio donde ocurre la acción.
    - No corrijas errores del audio. Cópialo tal cual.

    Estructura JSON obligatoria:
    {ejemplo_json}
    """
    
    usuario = f"""
    <AUDIO_REAL>
    {texto_seguro}
    </AUDIO_REAL>
    """
    
    print("🧠 Consultando a GPT-4o-mini...")
    
    respuesta_json_str = consultar_gpt(sistema, usuario, referencia_log=nombre_archivo)
    
    try:
        datos = json.loads(respuesta_json_str)
        if "ReporteCalidad" in datos:
            datos = datos["ReporteCalidad"]
            
        print(f"👮‍♂️ Validando evidencias (Sheriff 4.1 Flexible)...")
        datos_validados = validar_por_tokens(datos, texto_seguro)
        
        puntos_fuertes = [ItemEvaluacion(**item) for item in datos_validados.get("puntos_fuertes", [])]
        areas_mejora = [ItemEvaluacion(**item) for item in datos_validados.get("areas_mejora", [])]
        
        nota_real = calcular_nota_ponderada(puntos_fuertes, areas_mejora)
        
        reporte = ReporteCalidad(
            asesor=datos.get("asesor", "Desconocido"),
            resumen_ejecutivo=datos.get("resumen_ejecutivo", ""),
            puntos_fuertes=puntos_fuertes,
            areas_mejora=areas_mejora,
            nota_final_0_10=nota_real
        )
        
        output_path = settings.OUTPUTS_DIR / f"{nombre_archivo}_reporte.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(reporte.model_dump_json(indent=2))
            
        print(f"✅ Reporte generado: {output_path}")
        print(f"⭐️ NOTA FINAL: {nota_real}/10")
        return reporte
        
    except Exception as e:
        print(f"❌ Error procesando {nombre_archivo}: {e}")
        return None