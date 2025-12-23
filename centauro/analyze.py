import json
from .config import settings
from .rag import buscar_contexto
from .llm_client import consultar_gpt
from .schema import ReporteCalidad
from .privacy import redact_pii  # Importamos tu módulo de seguridad

def analizar_entrevista(nombre_archivo, texto_transcripcion):
    print(f"🔍 Buscando reglas para: {nombre_archivo}")
    
    # --- 1. CAPA DE PRIVACIDAD (GDPR) ---
    print("🛡️ Aplicando capa de privacidad...")
    resultado_privacidad = redact_pii(texto_transcripcion)
    texto_seguro = resultado_privacidad.text
    
    # Log opcional de seguridad
    if sum(resultado_privacidad.stats.values()) > 0:
        print(f"   🔒 Datos sensibles ocultados: {resultado_privacidad.stats}")
    
    # --- 2. RECUPERACIÓN DE CONTEXTO (RAG) ---
    # Buscamos en ChromaDB las reglas relevantes
    contexto_manual = buscar_contexto("Criterios de evaluación calidad saludo cierre objeciones")
    
    # --- 3. DEFINICIÓN DEL PROMPT ---
    ejemplo_json = """
    {
        "asesor": "Nombre o 'Desconocido'",
        "resumen_ejecutivo": "Resumen breve",
        "puntos_fuertes": [
            {
                "criterio": "Saludo", 
                "cumple": true, 
                "cita_evidencia": "Hola...", 
                "referencia_manual": "manual.txt", 
                "feedback": "Correcto"
            }
        ],
        "areas_mejora": [
            {
                "criterio": "Cierre", 
                "cumple": false, 
                "cita_evidencia": "Adios...", 
                "referencia_manual": "manual.txt", 
                "feedback": "Incorrecto"
            }
        ],
        "nota_final_0_10": 5
    }
    """

    # AÑADIMOS LA INSTRUCCIÓN DE INFERENCIA DE HABLANTES
    sistema = f"""
    Eres CENTAURO, un auditor de calidad comercial.
    
    MANUAL DE CRITERIOS (LA LEY):
    {contexto_manual}
    
    INSTRUCCIONES:
    1. Evalúa basándote EXCLUSIVAMENTE en el manual.
    2. Si el asesor hace algo no documentado, ignóralo.
    3. DEBES devolver un JSON válido siguiendo EXACTAMENTE este ejemplo:
    {ejemplo_json}

    IMPORTANTE SOBRE LA TRANSCRIPCIÓN:
    La transcripción puede no indicar explícitamente quién habla en cada línea (o no tener nombres).
    Tu tarea es INFERIR por el CONTEXTO del diálogo:
    - Quién es el ASESOR (quien explica, vende, saluda en nombre de la empresa).
    - Quién es el CLIENTE/CANDIDATO (quien pregunta, responde dudas personales).
    """
    
    # Usamos el texto seguro (sin DNI/Teléfonos)
    usuario = f"""
    Analiza esta transcripción (datos personales ocultados con [REDACTED]):
    {texto_seguro}
    """
    
    print("🧠 Consultando a GPT-4o-mini...")
    
    # --- CAMBIO AQUÍ: Pasamos el nombre del archivo para el Excel de gastos ---
    respuesta_json_str = consultar_gpt(sistema, usuario, referencia_log=nombre_archivo)
    
    # --- 4. PROCESAMIENTO ---
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
        # Imprimimos un trozo de la respuesta para depurar si falla el JSON
        print(f"DEBUG - Respuesta de la IA: {respuesta_json_str[:200]}...") 
        return None