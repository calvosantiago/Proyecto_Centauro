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
    
    # Guardamos debug
    debug_path = settings.OUTPUTS_DIR / f"DEBUG_INPUT_{nombre_archivo}.txt"
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(texto_seguro)
    
    # 2. RAG
    contexto_manual = buscar_contexto("Guía completa de criterios de evaluación y checklist de calidad")

    # 3. Prompt Híbrido
    base = nombre_archivo.rsplit(".", 1)[0]
    if base.startswith("entrevista_"):
        base = base[len("entrevista_"):]
    nombre_limpio = base.replace("_", " ").strip()

    # CAMBIO CLAVE: Un ejemplo JSON COMPLETO para que la IA sepa que debe evaluar TODO
    ejemplo_json = """
    {
        "asesor": "Paola Suarez",
        "resumen_ejecutivo": "La asesora conecta bien y explica el producto, pero olvida el aviso legal crítico.",
        "puntos_fuertes": [
            {
                "criterio": "Saludo", 
                "cumple": true, 
                "cita_evidencia": "Hola, buenos días", 
                "referencia_manual": "manual_saludo.txt", 
                "feedback": "Saludo correcto y amable.",
                "razonamiento": "Cumple la intención de iniciar la conversación."
            },
            {
                "criterio": "Cierre de Venta", 
                "cumple": true, 
                "cita_evidencia": "¿Te parece bien si reservamos?", 
                "referencia_manual": "manual_cierre.txt", 
                "feedback": "Buen intento de cierre.",
                "razonamiento": "Propone claramente el siguiente paso."
            }
        ],
        "areas_mejora": [
            {
                "criterio": "Aviso Grabación", 
                "cumple": false, 
                "cita_evidencia": "NO ENCONTRADO", 
                "referencia_manual": "manual_legal.txt", 
                "feedback": "Fallo crítico: No avisa de la grabación.",
                "razonamiento": "No se encontraron las palabras clave obligatorias (grabar, calidad, monitorizar)."
            }
        ],
        "nota_final_0_10": 6.5
    }
    """

    sistema = f"""
    Eres CENTAURO, un auditor de calidad comercial.
    Tu misión es evaluar la entrevista COMPLETA basándote en el manual.
    
    MANUAL DE CRITERIOS:
    {contexto_manual}
    
    METADATOS:
    - Asesor: "{nombre_limpio}"
    
    -----------------------------------------------------------------------
    ⚖️ CRITERIOS DE EVALUACIÓN HÍBRIDOS (POLI BUENO / POLI MALO)
    -----------------------------------------------------------------------
    
    TIPO A: CRITERIOS LEGALES Y TÉCNICOS (AVISO GRABACIÓN, LOPD, DNI) -> ¡SÉ ESTRICTO!
       - Regla: "Palabras Clave o Falso".
       - Para el "Aviso de Grabación", si no encuentras palabras como "grabar", "calidad", "monitorizar" o "registro", marca FALSE.
       - Cita evidencia: "NO ENCONTRADO" si no está literal.
       - Razón: "No se encontraron palabras clave legales".

    TIPO B: CRITERIOS SOCIALES Y COMERCIALES (SALUDO, EMPATÍA, CIERRE) -> ¡SÉ FLEXIBLE!
       - Regla: "Intención sobre Literalidad".
       - Si el manual dice "Decir Buenos Días" y el asesor dice "Hola", marca TRUE.
       - Evalúa si el asesor logró el objetivo comunicativo del criterio.

    -----------------------------------------------------------------------
    INSTRUCCIONES FINALES:
    1. EVALÚA TODO: No te quedes solo en el aviso legal. Revisa Saludo, Sondeo, Argumentación, Objeciones y Cierre.
    2. RAZONAMIENTO: Explica en cada punto por qué cumple o falla.
    3. NOTA MATEMÁTICA: (Puntos Cumplidos / Total Evaluados) * 10.
    
    Estructura JSON obligatoria (Usa este esquema completo):
    {ejemplo_json}
    """
    
    usuario = f"""
    AUDITA ESTA TRANSCRIPCIÓN COMPLETA:
    {texto_seguro}
    """
    
    print("🧠 Consultando a GPT-4o-mini (Modo Híbrido)...")
    
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