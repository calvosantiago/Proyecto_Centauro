"""
MAIN.PY - Sistema Multi-Agente v2.0


"""
import os
import re   
import time
import json
from pathlib import Path

try:
    from docx import Document
except ImportError:
    Document = None

from centauro.config import settings
from centauro.rag import indexar_documentacion
from centauro.reports import generar_pdf

# ===== CAMBIO PRINCIPAL: Nuevo orquestador =====
from centauro.core import CentauroOrchestrator
# ================================================

# --- FUNCIONES DE LECTURA (SIN CAMBIOS) ---

def limpiar_formato_vtt(texto_crudo):
    """Elimina metadatos técnicos de archivos VTT"""
    texto = texto_crudo.replace("WEBVTT", "")
    texto = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}', '', texto)
    texto = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(-\d+)?', '', texto)
    texto = re.sub(r'<[^>]+>', '', texto)
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    texto_limpio = " ".join(lineas)
    return texto_limpio

def leer_word(ruta_archivo):
    """Extrae texto de archivos Word (Teams)"""
    if not Document:
        print("❌ ERROR: Falta librería 'python-docx'.")
        return ""
    
    try:
        doc = Document(ruta_archivo)
        transcript = []
        current_speaker = None
        current_text_buffer = []
        patron_teams = re.compile(r"^(.*?)\s+(\d{1,2}:\d{2}(?::\d{2})?)$")
        lines_found = 0 

        for para in doc.paragraphs:
            bloque_texto = para.text.replace('\r', '\n')
            sub_lineas = bloque_texto.split('\n')

            for linea in sub_lineas:
                texto = linea.strip()
                if not texto:
                    continue 
                texto_norm = re.sub(r'\s+', ' ', texto)
                match = patron_teams.match(texto_norm)

                if match:
                    lines_found += 1
                    if lines_found <= 3:
                        print(f"   🎯 Match: {match.group(1)}")

                    if current_speaker and current_text_buffer:
                        contenido = " ".join(current_text_buffer)
                        transcript.append(f"[{current_speaker}]: {contenido}")
                    
                    current_speaker = match.group(1).strip() 
                    current_text_buffer = [] 
                else:
                    if current_speaker:
                        current_text_buffer.append(texto)

        if current_speaker and current_text_buffer:
            contenido = " ".join(current_text_buffer)
            transcript.append(f"[{current_speaker}]: {contenido}")

        full_text = "\n\n".join(transcript)
        
        if not full_text:
            print("   ❌ FALLO: No se extrajo texto.")
        else:
            print(f"   ✅ ÉXITO: {lines_found} intervenciones detectadas.")

        return full_text

    except Exception as e:
        print(f"❌ Error leyendo Word {ruta_archivo}: {e}")
        return ""

def cargar_transcripcion(ruta_archivo):
    """Detector inteligente de formato (Word, VTT, TXT)"""
    # VALIDACIÓN CRÍTICA: Verificar longitud de nombre de archivo
    try:
        from centauro.utils import validar_archivo_para_procesamiento, generar_mensaje_error_usuario

        validacion = validar_archivo_para_procesamiento(ruta_archivo)

        if not validacion:
            # Generar mensaje de error amigable
            mensaje_error = generar_mensaje_error_usuario(validacion, "análisis de conversación")
            print("\n" + "="*60)
            print(mensaje_error)
            print("="*60 + "\n")
            return None
    except ImportError:
        # Si no existe el módulo de validaciones, continuar sin validar
        pass

    ext = ruta_archivo.suffix.lower()

    if ext == ".docx":
        print(f"   📄 Leyendo documento Word...")
        return leer_word(ruta_archivo)

    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            texto = f.read()

        if ext == ".vtt" or "WEBVTT" in texto[:50]:
            print(f"   🧹 Limpiando formato VTT...")
            return limpiar_formato_vtt(texto)

        return texto

    except Exception as e:
        print(f"❌ Error leyendo archivo {ruta_archivo}: {e}")
        return None

# --- MAIN (CON NUEVO ORQUESTADOR) ---

def main():
    print("🦄 INICIANDO PROYECTO CENTAURO v2.0 (Multi-Agente Optimizado)...")
    print("="*70)
    
    # 1. Asegurar directorios
    os.makedirs(settings.INPUTS_DIR / "docs", exist_ok=True)
    os.makedirs(settings.INPUTS_DIR / "transcripts", exist_ok=True)
    os.makedirs(settings.OUTPUTS_DIR, exist_ok=True)

    # 2. Indexar Manuales (RAG)
    print("\n📚 Paso 1: Indexando base de conocimiento...")
    indexar_documentacion()

    # 3. Buscar entrevistas
    carpeta = settings.INPUTS_DIR / "transcripts"
    archivos_transcripcion = (
        list(carpeta.glob("*.txt")) + 
        list(carpeta.glob("*.vtt")) + 
        list(carpeta.glob("*.docx"))
    )
    
    if not archivos_transcripcion:
        print("\n⚠️ No hay transcripciones en 'inputs/transcripts/'")
        print("   Formatos soportados: .txt, .vtt, .docx")
        return

    print(f"\n🚀 Paso 2: Procesando {len(archivos_transcripcion)} entrevista(s)...")
    print("="*70)

    # ===== CREAR ORQUESTADOR =====
    orchestrator = CentauroOrchestrator()
    # ==============================

    # 4. Bucle de Procesamiento
    for idx, archivo in enumerate(archivos_transcripcion, 1):
        print(f"\n{'='*70}")
        print(f"📂 [{idx}/{len(archivos_transcripcion)}] {archivo.name}")
        print(f"{'='*70}")
        
        # Cargar transcripción
        texto = cargar_transcripcion(archivo)
        if not texto: 
            print("   ⚠️ Archivo vacío o no legible, saltando...")
            continue
        
        # Iniciar cronómetro
        inicio_reloj = time.time()
        print("   ⏳ Analizando con sistema multi-agente...")

        # ===== EJECUTAR ANÁLISIS CON ORQUESTADOR =====
        try:
            reporte = orchestrator.analizar_entrevista_completa(
                nombre_archivo=archivo.stem,
                texto_crudo=texto
            )
        except Exception as e:
            print(f"\n   ❌ ERROR en análisis: {e}")
            print(f"   💡 Tip: Revisa que tu API key de OpenAI sea válida")
            continue
        # ==============================================
        
        # Cronómetro
        fin_reloj = time.time()
        tiempo_total = fin_reloj - inicio_reloj
        minutos = int(tiempo_total // 60)
        segundos = int(tiempo_total % 60)

        print(f"\n   ⏱️ Tiempo de análisis: {minutos} min {segundos} seg")
        
        # Generar outputs
        if reporte:
            # JSON
            json_path = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{archivo.stem}_v2.json"
            json_path.parent.mkdir(exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(reporte, f, indent=2, ensure_ascii=False)
            print(f"   💾 JSON guardado: {json_path.name}")
            
            # PDF
            print("   🎨 Generando PDF...")
            nombre_pdf = f"Reporte_{archivo.stem}_v2.pdf"
            generar_pdf(reporte, nombre_pdf)
            
            # Estadísticas de optimización
            if "meta" in reporte and "stats_optimizacion" in reporte["meta"]:
                stats = reporte["meta"]["stats_optimizacion"]
                print(f"\n   📊 Estadísticas:")
                print(f"      • Llamadas API: {stats.get('llamadas_api', 'N/A')}")
                print(f"      • Cache hits: {stats.get('cache_hits', 'N/A')}")
                print(f"      • Tokens ahorrados: ~{stats.get('tokens_ahorrados', 0):,}")
        else:
            print("   ❌ El análisis falló, no se generó reporte.")

    print(f"\n{'='*70}")
    print("✅ PROCESO COMPLETADO")
    print(f"{'='*70}")
    print(f"📁 Revisa tus reportes en: {settings.OUTPUTS_DIR}")
    print("   • PDFs en: outputs/Reportes_PDF/")
    print("   • JSONs en: outputs/Reportes_JSON/")
    print()

if __name__ == "__main__":
    main()