from pathlib import Path
import re
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
    # Busca líneas que tengan letras, números y guiones, y sean largas (más de 20 chars)
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
        # Si la línea parece un código (sin espacios o con estructura de ID)
        if uuid_pattern.match(line):
            continue

        # 4. Si sobrevive a los filtros, es TEXTO hablado
        clean_lines.append(line)

    # Unimos todo con saltos de línea
    return "\n".join(clean_lines)

def main():
    settings.OUTPUTS_DIR.mkdir(exist_ok=True)
    
    # 1. Indexar manuales
    indexar_documentacion()
    
    # 2. Procesar entrevistas
    entrevistas = list(settings.TRANSCRIPTS_DIR.glob("*.txt"))
    
    if not entrevistas:
        print("No hay entrevistas en inputs/transcripts/ para procesar.")
        return

    print(f"--- Procesando {len(entrevistas)} entrevistas ---")
    for entrevista in entrevistas:
        print(f"Analizando: {entrevista.name}...")
        texto = entrevista.read_text(encoding="utf-8")
        analizar_entrevista(entrevista.name, texto)

if __name__ == "__main__":
    main()
