import json
import re
from .llm_client import consultar_gpt

def extraer_json_diarizacion(respuesta_raw: str) -> dict:
    """Helper local para limpiar JSONs de diarización"""
    if not respuesta_raw: return {}
    limpio = respuesta_raw.replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", limpio, flags=re.S)
    json_str = m.group(0) if m else limpio
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        print(f"      ⚠️ JSON roto en chunk de diarización. Usando texto original.")
        return {}

def pre_procesar_texto(texto: str) -> list:
    """
    Intenta restaurar la estructura de diálogo si el texto viene como un bloque sólido.
    Divide por puntos, interrogaciones y saltos de línea existentes.
    """
    # 1. Si ya tiene saltos de línea (como en los [source]), los respetamos
    if texto.count('\n') > len(texto) / 200: 
        # Si hay bastantes enters (1 cada 200 chars aprox), asumimos que tiene estructura
        return [linea.strip() for linea in texto.split('\n') if linea.strip()]

    # 2. Si es un muro de texto, forzamos división por puntuación
    print("      🔧 Detectado 'Muro de Texto'. Re-estructurando por frases...")
    # Regex: Divide cuando encuentra (. ? !) seguido de espacio o final de línea
    frases = re.split(r'(?<=[.?!])\s+', texto)
    return [f.strip() for f in frases if f.strip()]

def identificar_interlocutores(texto_crudo: str, nombre_asesor: str, log_id: str) -> str:
    """
    Identifica [ASESOR] vs [LEAD] forzando la separación de diálogos.
    """
    print(f"   🗣️ Identificando interlocutores (Asesor: {nombre_asesor})...")
    
    # PASO 1: Re-estructuración (Cirugía de texto)
    lineas = pre_procesar_texto(texto_crudo)
    
    # PASO 2: Chunking Inteligente (Agrupamos líneas, no caracteres ciegos)
    tamano_chunk_max = 2000 # Bajamos tamaño para mayor precisión
    texto_total_diarizado = ""
    
    chunks = []
    chunk_actual = []
    len_actual = 0
    
    for linea in lineas:
        chunk_actual.append(linea)
        len_actual += len(linea)
        
        # Cortamos si nos pasamos de tamaño
        if len_actual >= tamano_chunk_max:
            chunks.append("\n".join(chunk_actual))
            chunk_actual = []
            len_actual = 0
            
    if chunk_actual: chunks.append("\n".join(chunk_actual))

    print(f"      ℹ️ Procesando {len(chunks)} bloques de diálogo...")

    # PASO 3: Prompt "Rompehielos" (Detectar cambios de turno)
    prompt_base = f"""
ERES UN EXPERTO EN TRANSCRIPCIONES.
Tu objetivo es reconstruir un diálogo entre un ASESOR ({nombre_asesor}) y un LEAD (Cliente).
El texto de entrada puede estar desordenado o pegado.

ROLES:
- [ASESOR]: Vende, explica el máster OBS, metodología, precios, becas.
- [LEAD]: Pregunta, duda, habla de su trabajo, su vida, objeciones.

TU MISIÓN OBLIGATORIA:
1. Lee cada frase y decide quién la dice.
2. **DETECTA EL CAMBIO DE TURNO:** Si el Asesor hace una pregunta y luego viene una respuesta, DEBES insertar un salto de línea y cambiar la etiqueta a [LEAD].
3. Si el texto es un párrafo largo del mismo hablante, mantén la etiqueta.
4. Usa las "Anclas Semánticas":
   - Asesor: "Matrícula", "Admisión", "Validar perfil", "Universidad de Barcelona".
   - Lead: "Precio", "Mi jefe", "Horario", "Lo pensaré", "Trabajo en...".

FORMATO DE SALIDA (JSON):
{{
  "texto_diarizado": "[ASESOR]: Hola, ¿cómo estás?\\n[LEAD]: Bien gracias.\\n[ASESOR]: Cuéntame de ti."
}}
"""

    for i, chunk in enumerate(chunks):
        try:
            # print(f"      - Procesando parte {i+1}...") 
            resp_str = consultar_gpt(
                prompt_base, 
                f"FRAGMENTO {i+1}:\n{chunk}", 
                referencia_log=f"{log_id}_diar_{i+1}"
            )
            
            data = extraer_json_diarizacion(resp_str)
            fragmento = data.get("texto_diarizado", chunk)
            
            # Limpieza de seguridad
            fragmento = fragmento.replace('\"', '"')
            texto_total_diarizado += fragmento + "\n"
            
        except Exception as e:
            print(f"      ⚠️ Error en bloque {i+1}: {e}")
            texto_total_diarizado += chunk + "\n"

    return texto_total_diarizado