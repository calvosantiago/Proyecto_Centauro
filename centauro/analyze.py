import json
from .config import settings
from .rag import buscar_contexto
from .llm_client import consultar_gpt
from .schema import ReporteCalidad
from .privacy import redact_pii

def analizar_entrevista(nombre_archivo, texto_transcripcion):
    print(f"🔍 Buscando reglas para: {nombre_archivo}")
    
    # 1. Privacidad y Debug
    resultado_privacidad = redact_pii(texto_transcripcion)
    texto_seguro = resultado_privacidad.text
    
    # GUARDAR LO QUE LEE LA IA (CRÍTICO PARA QUE TÚ VERIFIQUES)
    debug_path = settings.OUTPUTS_DIR / f"DEBUG_INPUT_{nombre_archivo}.txt"
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(texto_seguro)
    
    # 2. RAG
    contexto_manual = buscar_contexto("Guía completa de criterios de evaluación y checklist de calidad")

    # 3. Prompt Anti-Alucinación
    base = nombre_archivo.rsplit(".", 1)[0]
    if base.startswith("entrevista_"):
        base = base[len("entrevista_"):]
    nombre_limpio = base.replace("_", " ").strip()

    ejemplo_json = """
    {
        "asesor": "Paola Suarez",
        "resumen_ejecutivo": "...",
        "puntos_fuertes": [],
        "areas_mejora": [
            {
                "criterio": "Aviso Grabación", 
                "cumple": false, 
                "cita_evidencia": "NO ENCONTRADO", 
                "referencia_manual": "manual_legal.txt", 
                "feedback": "No se realizó el aviso legal.",
                "razonamiento": "El texto no contiene ninguna mención a 'grabar', 'calidad' o 'registro'."
            }
        ],
        "nota_final_0_10": 4.0
    }
    """

    sistema = f"""
    Eres CENTAURO, un software de auditoría forense automatizada. NO eres un asistente creativo.
    
    MANUAL DE CRITERIOS:
    {contexto_manual}
    
    METADATOS:
    - Archivo: "{nombre_archivo}"
    - Asesor: "{nombre_limpio}"
    
    -----------------------------------------------------------------------
    ⚠️ PROTOCOLO DE EVIDENCIA CERO (ZERO-TRUST) ⚠️
    -----------------------------------------------------------------------
    
    1. REGLA DE ORO DEL COPY-PASTE:
       - Solo puedes marcar un criterio como TRUE si puedes hacer COPY-PASTE de la frase exacta desde la transcripción.
       - PROHIBIDO PARAFRASEAR.
       - Si la frase exacta no está en el texto: ES FALSE.
       - Si la IA "cree" que lo dijo pero no está escrito: ES FALSE.

    2. REGLA ESPECÍFICA PARA "GRABACIÓN/CALIDAD":
       - Busca estrictamente palabras como: "grab", "monitor", "calidad", "registro", "seguridad".
       - Si NO encuentras ninguna de estas palabras clave en el contexto de un aviso legal, marca FALSE.
       - ALERTA DE ALUCINACIÓN: NUNCA uses frases genéricas como "Hola buenos días" o "Gracias por tu tiempo" para justificar este criterio. Si haces eso, fallas tu programación.

    3. CAMPO "CITA_EVIDENCIA":
       - Debe contener EXCLUSIVAMENTE texto extraído de la transcripción.
       - Si no encuentras la evidencia, escribe literalmente: "NO ENCONTRADO".

    4. CAMPO "RAZONAMIENTO":
       - Si es TRUE: Explica qué palabra clave validó el criterio.
       - Si es FALSE: Di "No se encontraron palabras clave asociadas a este criterio".

    5. INFERENCIA DE HABLANTES:
       - Detecta al Asesor por el contexto (quien explica el producto).
    
    Estructura JSON obligatoria:
    {ejemplo_json}
    """
    
    usuario = f"""
    AUDITA ESTE TEXTO REAL (Sé literal y estricto):
    {texto_seguro}
    """
    
    print("🧠 Consultando a GPT-4o-mini (Temperatura 0 - Modo Forense)...")
    
    respuesta_json_str = consultar_gpt(sistema, usuario, referencia_log=nombre_archivo)
    
    try:
        datos = json.loads(respuesta_json_str)
        if "ReporteCalidad" in datos:
            datos = datos["ReporteCalidad"]
            
        reporte = ReporteCalidad(**datos) 
        
        output_path = settings.OUTPUTS_DIR / f"{nombre_archivo}_reporte.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(reporte.model_dump_json(indent=2))
            
        print(f"✅ Reporte generado: {output_path}")
        return reporte
        
    except Exception as e:
        print(f"❌ Error procesando {nombre_archivo}: {e}")
        return None