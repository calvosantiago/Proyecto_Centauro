import os
import time
from pathlib import Path

# Importamos tus módulos
from centauro.config import settings
from centauro.analyze import analizar_entrevista
from centauro.rag import indexar_documentacion
# 1. IMPORTAMOS EL GENERADOR DE PDF <--- NUEVO
from centauro.reports import generar_pdf 

def cargar_transcripcion(ruta_archivo):
    """Lee el archivo de texto o VTT."""
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            texto = f.read()
            # Aquí podrías añadir una limpieza extra si es VTT
            return texto
    except Exception as e:
        print(f"❌ Error leyendo {ruta_archivo}: {e}")
        return None

def main():
    print("🦄 INICIANDO PROYECTO CENTAURO (v2.4 Final)...")
    
    # 1. Asegurar directorios
    os.makedirs(settings.INPUTS_DIR / "docs", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "transcripts", exist_ok=True)
    os.makedirs(settings.OUTPUTS_DIR, exist_ok=True)

    # 2. Indexar Manuales (RAG)
    print("\n📚 Actualizando memoria RAG...")
    indexar_documentacion()

    # 3. Buscar entrevistas para procesar
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
        
        texto = cargar_transcripcion(archivo)
        if not texto: continue

        # A) EJECUTAR ANÁLISIS (Llama a analyze.py)
        reporte = analizar_entrevista(archivo.name, texto)
        
        # B) GENERAR PDF (Si el análisis fue exitoso)
        if reporte:
            print("   🎨 Generando Informe PDF Premium...")
            
            # Nombre del archivo de salida
            nombre_pdf = f"Reporte_{archivo.stem}.pdf"
            
            # ⚠️ CONVERSIÓN CLAVE: Pasamos el objeto a Diccionario (.model_dump)
            # para que el generador de PDF lo entienda.
            datos_para_pdf = reporte.model_dump()
            
            # LLAMADA A LA FUNCIÓN DE PDF <--- AQUÍ OCURRE LA MAGIA
            generar_pdf(datos_para_pdf, nombre_pdf)
            
        else:
            print("   ❌ El análisis falló, no se generará PDF.")

    print("\n✅ CICLO TERMINADO. Revisa la carpeta 'outputs/'.")

if __name__ == "__main__":
    main()