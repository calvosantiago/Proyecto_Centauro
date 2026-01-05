import json
from .llm_client import consultar_gpt

def extraer_json_diarizacion(respuesta_raw: str) -> dict:
    """Helper local para limpiar JSONs de diarización"""
    import re
    if not respuesta_raw: return {}
    limpio = respuesta_raw.replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", limpio, flags=re.S)
    json_str = m.group(0) if m else limpio
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        print(f"      ⚠️ JSON roto en chunk de diarización. Usando texto original.")
        return {}

def identificar_interlocutores(texto_crudo: str, nombre_asesor: str, log_id: str) -> str:
    """
    Identifica quién es el [ASESOR] y quién el [LEAD] en una transcripción plana.
    Usa chunking para manejar textos largos y anclas semánticas para precisión.
    """
    print(f"   🗣️ Identificando interlocutores (Asesor: {nombre_asesor})...")
    
    # 1. Chunking (Dividir texto largo)
    tamano_chunk = 3000 
    texto_total_diarizado = ""
    lineas = texto_crudo.split('\n')
    chunks = []
    chunk_actual = []
    len_actual = 0
    
    for linea in lineas:
        chunk_actual.append(linea)
        len_actual += len(linea)
        if len_actual >= tamano_chunk:
            chunks.append("\n".join(chunk_actual))
            chunk_actual = []
            len_actual = 0
    if chunk_actual: chunks.append("\n".join(chunk_actual))

    print(f"      ℹ️ Procesando {len(chunks)} bloques de texto...")

    # 2. Prompt con Anclas Semánticas (Nivel 1 de Seguridad)
    prompt_base = f"""
ERES UN EDITOR DE GUIONES EXPERTO. 
Tu tarea es separar el diálogo entre el ASESOR ({nombre_asesor}) y el LEAD (Cliente).

INPUT: Fragmento de una llamada de venta de OBS Business School.
OUTPUT: JSON con campo "texto_diarizado".

🔍 PISTAS CLAVE (ANCLAS SEMÁNTICAS):
- EL [ASESOR] (Vendedor) SUELE DECIR: "OBS", "Universidad de Barcelona", "Máster", "Metodología", "Campus", "Beca", "Matrícula", "Admisión", "¿Alguna duda?", "Plan de estudios", "Validar perfil".
- EL [LEAD] (Cliente) SUELE DECIR: "Precio", "Costo", "Mi trabajo", "Horario", "Tengo que pensarlo", "Lo consultaré", "Experiencia laboral", "Trabajo en...".

REGLAS:
1. Añade `[ASESOR]:` o `[LEAD]:` al inicio de cada frase según el contexto.
2. NO RESUMAS NI CAMBIES PALABRAS. Devuelve el texto LITERAL palabra por palabra.
3. Si el fragmento empieza a mitad de frase, intenta inferir el rol por el contexto anterior.

EJEMPLO SALIDA JSON:
{{
  "texto_diarizado": "[ASESOR]: Hola, buenos días.\\n[LEAD]: Hola, quería información sobre el máster."
}}
OUTPUT MUST BE VALID JSON.
"""

    for i, chunk in enumerate(chunks):
        try:
            # Feedback visual de progreso
            # print(f"      - Bloque {i+1}/{len(chunks)}...")
            
            resp_str = consultar_gpt(
                prompt_base, 
                f"FRAGMENTO {i+1}:\n{chunk}", 
                referencia_log=f"{log_id}_diar_{i+1}"
            )
            
            data = extraer_json_diarizacion(resp_str)
            # Si falla el JSON, usamos el chunk original para no perder datos
            fragmento = data.get("texto_diarizado", chunk)
            texto_total_diarizado += fragmento + "\n"
            
        except Exception as e:
            print(f"      ⚠️ Error procesando bloque {i+1}: {e}. Se mantiene texto original.")
            texto_total_diarizado += chunk + "\n"

    return texto_total_diarizado