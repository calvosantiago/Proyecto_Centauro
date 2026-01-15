import os
import re   
import time
from pathlib import Path

# --- NUEVO: Importación para leer Word ---
try:
    from docx import Document
except ImportError:
    Document = None  # Marcamos como no disponible si falta la librería

# Importamos tus módulos
from centauro.config import settings
from centauro.analyze import analizar_entrevista
from centauro.rag import indexar_documentacion
from centauro.reports import generar_pdf 

# --- FUNCIONES DE LECTURA Y LIMPIEZA ---

def limpiar_formato_vtt(texto_crudo):
    """
    Elimina la 'basura' técnica de los archivos VTT para ahorrar tokens y mejorar la lectura.
    """
    # 1. Eliminar cabecera WEBVTT
    texto = texto_crudo.replace("WEBVTT", "")

    # 2. Eliminar Timestamps (Ej: 00:18:03.194 --> 00:18:06.593)
    texto = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}', '', texto)

    # 3. Eliminar UUIDs/IDs de bloque (Ej: 48665a40-f0b6-49a2...)
    texto = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(-\d+)?', '', texto)

    # 4. Eliminar etiquetas de estilo (<v Speaker>, <b>, etc.)
    texto = re.sub(r'<[^>]+>', '', texto)

    # 5. Limpieza final: Quitar líneas vacías y unir párrafos
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    texto_limpio = " ".join(lineas)
    
    return texto_limpio

def leer_word(ruta_archivo):
    """
    Extrae texto de un .docx con formato Teams.
    SOLUCIÓN FINAL: Gestiona 'Soft Returns' (Shift+Enter) dividiendo por '\\n'.
    """
    if not Document:
        print("❌ ERROR: Falta librería 'python-docx'.")
        return ""
    
    try:
        doc = Document(ruta_archivo)
        transcript = []
        
        current_speaker = None
        current_text_buffer = []

        # Regex: Busca "Cualquier cosa" + espacios + "Hora".
        # Ahora funcionará porque le pasaremos las líneas limpias y separadas.
        patron_teams = re.compile(r"^(.*?)\s+(\d{1,2}:\d{2}(?::\d{2})?)$")
        
        lines_found = 0 

        for para in doc.paragraphs:
            # --- EL TRUCO MAESTRO ---
            # Un párrafo de Word puede contener saltos de línea manuales (\n).
            # Los separamos para analizarlos uno por uno como si fueran párrafos distintos.
            bloque_texto = para.text.replace('\r', '\n') # Normalizar saltos
            sub_lineas = bloque_texto.split('\n')

            for linea in sub_lineas:
                texto = linea.strip()
                
                if not texto:
                    continue 

                # Limpieza de espacios dobles o raros
                texto_norm = re.sub(r'\s+', ' ', texto)

                match = patron_teams.match(texto_norm)

                if match:
                    lines_found += 1
                    # Chivato de éxito (solo las primeras 3 veces)
                    if lines_found <= 3:
                        print(f"   🎯 Match: {match.group(1)}")

                    # Guardar bloque anterior
                    if current_speaker and current_text_buffer:
                        contenido = " ".join(current_text_buffer)
                        transcript.append(f"[{current_speaker}]: {contenido}")
                    
                    # Nuevo turno
                    current_speaker = match.group(1).strip() 
                    current_text_buffer = [] 
                    
                else:
                    # Es contenido hablado
                    if current_speaker:
                        current_text_buffer.append(texto)

        # Guardar último bloque
        if current_speaker and current_text_buffer:
            contenido = " ".join(current_text_buffer)
            transcript.append(f"[{current_speaker}]: {contenido}")

        full_text = "\n\n".join(transcript)
        
        if not full_text:
            print("   ❌ FALLO: No se extrajo texto. Revisa el DEBUG anterior.")
        else:
            print(f"   ✅ ÉXITO: Diarización completada ({lines_found} intervenciones).")

        return full_text

    except Exception as e:
        print(f"❌ Error leyendo Word {ruta_archivo}: {e}")
        return ""

def cargar_transcripcion(ruta_archivo):
    """Detector inteligente de formato (Word, VTT, TXT)."""
    ext = ruta_archivo.suffix.lower()

    # CASO 1: Archivo Word (.docx)
    if ext == ".docx":
        print(f"   📄 Leyendo documento Word (Teams Mode)...")
        return leer_word(ruta_archivo)

    # CASO 2: Archivos de Texto (.txt / .vtt)
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            texto = f.read()
            
        # DETECTAR SI ES VTT: Por extensión o contenido
        if ext == ".vtt" or "WEBVTT" in texto[:50]:
            print(f"   🧹 Limpiando formato VTT (quitando timestamps y IDs)...")
            return limpiar_formato_vtt(texto)
        
        # Si es TXT normal, pasa tal cual
        return texto
        
    except Exception as e:
        print(f"❌ Error leyendo archivo de texto {ruta_archivo}: {e}")
        return None

# --- MAIN ---

def main():
    print("🦄 INICIANDO PROYECTO CENTAURO (v2.6 Universal Input)...")
    
    # 1. Asegurar directorios
    os.makedirs(settings.INPUTS_DIR / "docs", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "transcripts", exist_ok=True)
    os.makedirs(settings.OUTPUTS_DIR, exist_ok=True)

    # 2. Indexar Manuales (RAG)
    print("\n📚 Actualizando memoria RAG...")
    indexar_documentacion()

    # 3. Buscar entrevistas (TXT, VTT y ahora DOCX)
    carpeta = settings.INPUTS_DIR / "transcripts"
    archivos_transcripcion = list(carpeta.glob("*.txt")) + \
                             list(carpeta.glob("*.vtt")) + \
                             list(carpeta.glob("*.docx"))
    
    if not archivos_transcripcion:
        print("⚠️ No hay transcripciones en 'inputs/transcripts/'. Pon archivos .txt, .vtt o .docx ahí.")
        return

    print(f"\n🚀 Se encontraron {len(archivos_transcripcion)} entrevistas. Procesando...")

    # 4. Bucle de Procesamiento
    for archivo in archivos_transcripcion:
        print(f"\n--------------------------------------------------")
        print(f"🎧 Analizando: {archivo.name}")
        
        # AQUI OCURRE LA LECTURA Y LIMPIEZA
        texto = cargar_transcripcion(archivo)
        
        if not texto: continue
        # --- 2. INICIAMOS EL CRONÓMETRO AQUÍ ---
        inicio_reloj = time.time()
        print("   ⏳ Enviando a la IA... (Esto puede tardar 1-2 minutos)")

        # A) EJECUTAR ANÁLISIS
        # El texto ya llega limpio (si era VTT) o estructurado (si era Word)
        reporte = analizar_entrevista(archivo.name, texto)
        # --- 3. PARAMOS EL CRONÓMETRO AQUÍ ---
        fin_reloj = time.time()
        tiempo_total = fin_reloj - inicio_reloj
        minutos = int(tiempo_total // 60)
        segundos = int(tiempo_total % 60)

        print(f"   ⏱️ Tiempo de análisis: {minutos} min {segundos} seg")
        
        # B) GENERAR PDF
        if reporte:
            print("   🎨 Generando Informe PDF Premium...")
            nombre_pdf = f"Reporte_{archivo.stem}.pdf"
            
            # Convertimos a dict seguro para evitar errores de Pydantic
            if hasattr(reporte, 'model_dump'):
                datos_para_pdf = reporte.model_dump()
            else:
                datos_para_pdf = reporte

            generar_pdf(datos_para_pdf, nombre_pdf)
        else:
            print("   ❌ El análisis falló, no se generará PDF.")

    print("\n✅ CICLO TERMINADO. Revisa la carpeta 'outputs/'.")

if __name__ == "__main__":
    main()