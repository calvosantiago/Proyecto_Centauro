import os
import re  # <--- IMPORTANTE: Necesario para la limpieza
from pathlib import Path

# Importamos tus módulos
from centauro.config import settings
from centauro.analyze import analizar_entrevista
from centauro.rag import indexar_documentacion
from centauro.reports import generar_pdf 

def limpiar_formato_vtt(texto_crudo):
    """
    Elimina la 'basura' técnica de los archivos VTT para ahorrar tokens y mejorar la lectura.
    """
    # 1. Eliminar cabecera WEBVTT
    texto = texto_crudo.replace("WEBVTT", "")

    # 2. Eliminar Timestamps (Ej: 00:18:03.194 --> 00:18:06.593)
    # Patrón: digitos:digitos:digitos.digitos --> ...
    texto = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}', '', texto)

    # 3. Eliminar UUIDs/IDs de bloque (Ej: 48665a40-f0b6-49a2...)
    texto = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(-\d+)?', '', texto)

    # 4. Eliminar etiquetas de estilo (<v Speaker>, <b>, etc.)
    texto = re.sub(r'<[^>]+>', '', texto)

    # 5. Limpieza final: Quitar líneas vacías y unir párrafos
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    texto_limpio = " ".join(lineas)
    
    return texto_limpio

def cargar_transcripcion(ruta_archivo):
    """Lee el archivo y aplica limpieza si es necesario."""
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            texto = f.read()
            
        # DETECTAR SI ES VTT: Por extensión o contenido
        if ruta_archivo.suffix.lower() == ".vtt" or "WEBVTT" in texto[:50]:
            print(f"   🧹 Limpiando formato VTT (quitando timestamps y IDs)...")
            return limpiar_formato_vtt(texto)
        
        # Si es TXT normal, pasa tal cual
        return texto
        
    except Exception as e:
        print(f"❌ Error leyendo {ruta_archivo}: {e}")
        return None

def main():
    print("🦄 INICIANDO PROYECTO CENTAURO (v2.5 Clean Input)...")
    
    # 1. Asegurar directorios
    os.makedirs(settings.INPUTS_DIR / "docs", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "transcripts", exist_ok=True)
    os.makedirs(settings.OUTPUTS_DIR, exist_ok=True)

    # 2. Indexar Manuales (RAG)
    print("\n📚 Actualizando memoria RAG...")
    indexar_documentacion()

    # 3. Buscar entrevistas
    archivos_transcripcion = list((settings.INPUTS_DIR / "transcripts").glob("*.txt")) + \
                             list((settings.INPUTS_DIR / "transcripts").glob("*.vtt"))
    
    if not archivos_transcripcion:
        print("⚠️ No hay transcripciones en 'inputs/transcripts/'. Pon archivos .txt o .vtt ahí.")
        return

    print(f"\n🚀 Se encontraron {len(archivos_transcripcion)} entrevistas. Procesando...")

    # 4. Bucle de Procesamiento
    for archivo in archivos_transcripcion:
        print(f"\n--------------------------------------------------")
        print(f"🎧 Analizando: {archivo.name}")
        
        # AQUI OCURRE LA LIMPIEZA AHORA
        texto = cargar_transcripcion(archivo)
        
        if not texto: continue

        # A) EJECUTAR ANÁLISIS
        reporte = analizar_entrevista(archivo.name, texto)
        
        # B) GENERAR PDF
        if reporte:
            print("   🎨 Generando Informe PDF Premium...")
            nombre_pdf = f"Reporte_{archivo.stem}.pdf"
            datos_para_pdf = reporte.model_dump()
            generar_pdf(datos_para_pdf, nombre_pdf)
        else:
            print("   ❌ El análisis falló, no se generará PDF.")

    print("\n✅ CICLO TERMINADO. Revisa la carpeta 'outputs/'.")

if __name__ == "__main__":
    main()