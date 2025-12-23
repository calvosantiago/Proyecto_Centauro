import re
import os
from pathlib import Path
from centauro.config import settings
from centauro.rag import indexar_documentacion
from centauro.analyze import analizar_entrevista

def limpiar_vtt(texto_vtt):
    """
    Limpieza agresiva para VTTs sin identificación de hablante.
    Elimina UUIDs, tiempos y cabeceras, dejando solo el flujo de conversación.
    """
    lines = texto_vtt.splitlines()
    clean_lines = []

    # Patrón para detectar los UUIDs largos (ej: c4fdd677-2ee3...)
    uuid_pattern = re.compile(r"^[a-fA-F0-9\-]{20,}.*$")

    for line in lines:
        line = line.strip()

        # 1. Saltar líneas vacías o cabecera
        if not line or line == "WEBVTT":
            continue

        # 2. Saltar Timestamps (00:00:00 --> ...)
        if "-->" in line:
            continue

        # 3. Saltar los códigos UUID extraños
        if uuid_pattern.match(line):
            continue

        # 4. Si sobrevive a los filtros, es TEXTO hablado
        clean_lines.append(line)

    # Unimos todo con saltos de línea
    return "\n".join(clean_lines)

def leer_transcripcion(ruta: Path):
    """
    Lee el archivo y aplica limpieza si es .vtt
    """
    try:
        contenido = ruta.read_text(encoding="utf-8")
        
        # Si es un archivo VTT, lo limpiamos antes de devolverlo
        if ruta.suffix.lower() == ".vtt":
            print(f"   🧹 Detectado VTT: Limpiando metadatos y timestamps...")
            return limpiar_vtt(contenido)
            
        # Si es TXT, lo devolvemos tal cual
        return contenido
        
    except Exception as e:
        print(f"❌ Error leyendo {ruta.name}: {e}")
        return ""

def main():
    settings.OUTPUTS_DIR.mkdir(exist_ok=True)
    
    # 1. Indexar manuales
    indexar_documentacion()
    
    # --- BLOQUE DE DEBUG (EL CHIVATO) ---
    # Esto te dirá exactamente dónde está mirando Python
    ruta_absoluta = settings.TRANSCRIPTS_DIR.resolve()
    print(f"\n👀 DEPURACIÓN: Buscando entrevistas en:")
    print(f"   📂 {ruta_absoluta}")
    
    if ruta_absoluta.exists():
        print(f"   📄 Archivos encontrados en esa carpeta: {os.listdir(ruta_absoluta)}")
    else:
        print(f"   ❌ ¡ALERTA! La carpeta no existe.")
    # ------------------------------------

    # 2. Procesar entrevistas (Buscamos TXT y VTT)
    archivos_txt = list(settings.TRANSCRIPTS_DIR.glob("*.txt"))
    archivos_vtt = list(settings.TRANSCRIPTS_DIR.glob("*.vtt"))
    entrevistas = archivos_txt + archivos_vtt
    
    if not entrevistas:
        print("\n⚠️ No hay entrevistas válidas (.txt o .vtt) para procesar.")
        return

    print(f"\n--- Procesando {len(entrevistas)} entrevistas ---")
    for entrevista in entrevistas:
        print(f"Analizando: {entrevista.name}...")
        
        texto_limpio = leer_transcripcion(entrevista)
        
        if texto_limpio:
            # Enviamos el texto limpio al auditor
            analizar_entrevista(entrevista.name, texto_limpio)

if __name__ == "__main__":
    main()