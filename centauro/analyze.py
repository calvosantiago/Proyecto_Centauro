import json
import re
from pathlib import Path
from .config import settings
from .rag import buscar_contexto
from .llm_client import consultar_gpt
from .schema import ReporteCalidad, ItemEvaluacion
from .privacy import redact_pii

# PESOS AJUSTADOS: Las habilidades blandas y el cierre pesan más
PESOS = {
    "CRITICO": 3.0,  # Multiplicador fuerte para habilidades clave
    "ALTA": 2.0,
    "MEDIA": 1.5,
    "BAJA": 1.0
}

def limpiar_tokens(texto):
    """Limpieza estándar para validación."""
    if not texto: return []
    texto = texto.lower().replace("€", "").replace("$", "").replace(".", "").replace(",", "")
    texto = re.sub(r'[^\w\s]', '', texto)
    tokens = texto.split()
    stopwords = {'de', 'el', 'la', 'que', 'en', 'y', 'a', 'los', 'un', 'una', 'es', 'por', 'del', 'con'}
    return [t for t in tokens if t not in stopwords and len(t) > 1]

def validar_evidencia(cita, texto_original):
    """
    Sheriff Simplificado: Verifica que la cita exista en el texto.
    Devuelve True/False y un ratio de confianza.
    """
    tokens_cita = limpiar_tokens(cita)
    tokens_texto = set(limpiar_tokens(texto_original))
    
    if not tokens_cita: return False, 0.0
    
    aciertos = sum(1 for t in tokens_cita if t in tokens_texto)
    ratio = aciertos / len(tokens_cita)
    
    # Umbral flexible (0.60 permite pequeñas variaciones de transcripción)
    return ratio >= 0.60, ratio

def calcular_nota_final(items):
    """Calcula nota ponderada basada en puntuación 1-5."""
    if not items: return 0.0
    
    total_puntos = 0.0
    total_peso_maximo = 0.0
    
    for item in items:
        peso = PESOS.get(item.importancia.upper(), 1.0)
        # La puntuación va de 1 a 5.
        # Normalizamos: 1->0.2, 5->1.0
        puntos_normalizados = (item.puntuacion) / 5.0 
        
        total_puntos += (puntos_normalizados * 10) * peso
        total_peso_maximo += 10 * peso 
        
    if total_peso_maximo == 0: return 0.0
    
    nota = (total_puntos / total_peso_maximo) * 10
    return round(nota, 2)

def analizar_entrevista(nombre_archivo, texto_transcripcion):
    print(f"🔍 Analizando (Modelo V3 - Competencias): {nombre_archivo}")
    
    # 1. Privacidad y Contexto
    res_priv = redact_pii(texto_transcripcion)
    texto_seguro = res_priv.text
    
    # Debug Input
    debug_dir = settings.OUTPUTS_DIR / "Input_Debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    nombre_corto_debug = Path(nombre_archivo).stem[:50].replace(" ", "_")
    with open(debug_dir / f"DEBUG_{nombre_corto_debug}.txt", "w", encoding="utf-8") as f:
        f.write(texto_seguro)

    contexto_manual = buscar_contexto("Venta consultiva metodologia cierre empatia")
    base_nombre = Path(nombre_archivo).stem.replace("_", " ")

    # 2. DEFINICIÓN DE RÚBRICA (La clave del cambio)
    ejemplo_json = """
    {
        "asesor": "Nombre",
        "resumen_ejecutivo": "El asesor demostró gran empatía...",
        "competencias_clave": [
            { 
                "criterio": "Sondeo Profundo", 
                "puntuacion": 4, 
                "cita_evidencia": "¿Qué te motiva a estudiar esto ahora?", 
                "razonamiento": "Hizo preguntas abiertas pero faltó profundizar en el dolor del cliente.",
                "importancia": "ALTA"
            }
        ],
        "habilidades_blandas": [
             { 
                "criterio": "Escucha Activa", 
                "puntuacion": 5, 
                "cita_evidencia": "Entiendo perfectamente que te preocupe el tiempo...", 
                "razonamiento": "Validó las emociones del cliente antes de rebatir.",
                "importancia": "CRITICO"
            }
        ]
    }
    """

    prompt_sistema = f"""
    Eres un DIRECTOR DE VENTAS DE ÉLITE y experto en metodología consultiva.
    Tu trabajo NO es verificar un checklist robótico. Tu trabajo es EVALUAR LA CALIDAD de la interacción.

    CONTEXTO:
    Estás evaluando a asesores académicos de alto nivel. 
    - Un novato (Grado D) sigue el guion mecánicamente.
    - Un experto (Grado A) conecta, escucha, adapta el mensaje y persuade.
    
    TUS CRITERIOS DE EVALUACIÓN (Escala 1-5):
    1 = Muy Deficiente (No lo hace o lo hace mal).
    3 = Cumplidor (Lo hace mecánicamente/robot).
    5 = Excelente (Lo hace de forma natural, estratégica y persuasiva).

    EVALÚA ESTAS COMPETENCIAS (HARD SKILLS):
    1. SONDEO (Imp: ALTA): ¿Hace preguntas profundas o solo superficiales? ¿Entiende el "por qué" del cliente?
    2. VALOR (Imp: ALTA): ¿Vende beneficios adaptados al cliente o recita características genéricas?
    3. CIERRE (Imp: ALTA): ¿Es proactivo pidiendo el compromiso? ¿Maneja el precio con seguridad?
    4. LEGAL (Imp: BAJA): ¿Menciona la grabación? (Si lo hace: 5, si no: 1).

    EVALÚA ESTAS HABILIDADES (SOFT SKILLS) - ESTO DIFERENCIA A LOS TOP PERFORMERS:
    1. ESCUCHA ACTIVA (Imp: CRITICO): ¿Deja hablar? ¿Retoma palabras del cliente? ¿Valida emociones?
    2. MANEJO DE OBJECIONES (Imp: CRITICO): ¿Rebate con argumentos o solo repite información? ¿Muestra empatía?
    3. TONO Y CONFIANZA (Imp: MEDIA): ¿Transmite autoridad y seguridad?

    FUENTES: <MANUAL>{contexto_manual}</MANUAL>
    
    Salida JSON OBLIGATORIA:
    {ejemplo_json}
    """

    usuario = f"<TRANSCRIPCION>\n{texto_seguro}\n</TRANSCRIPCION>"

    print("🧠 Consultando a GPT-4o-mini (Modo Coach)...")
    respuesta_raw = consultar_gpt(prompt_sistema, usuario, referencia_log=nombre_archivo)

    try:
        data = json.loads(respuesta_raw.replace("```json", "").replace("```", "").strip())
        if "ReporteCalidad" in data: data = data["ReporteCalidad"] # Soporte legacy
        
        # Unificamos listas
        todos_items_raw = data.get("competencias_clave", []) + data.get("habilidades_blandas", [])
        
        items_procesados = []

        for item_dict in todos_items_raw:
            # Rellenar defaults
            if "referencia_manual" not in item_dict: item_dict["referencia_manual"] = "Metodología General"
            if "feedback" not in item_dict: item_dict["feedback"] = item_dict.get("razonamiento", "")
            
            # Validar existencia de la cita (Sheriff Ligero)
            valido, ratio = validar_evidencia(item_dict.get("cita_evidencia", ""), texto_seguro)
            
            # Penalización por alucinación
            if not valido:
                print(f"   🚨 Cita no encontrada: '{item_dict.get('cita_evidencia')}' (Ratio: {ratio:.2f})")
                item_dict["puntuacion"] = 1 # Castigo máximo
                item_dict["razonamiento"] += f" [PENALIZACIÓN: La evidencia citada no aparece en el audio.]"
                item_dict["cita_evidencia"] = "NO ENCONTRADO EN AUDIO"
            
            # Convertir a objeto Pydantic
            item_obj = ItemEvaluacion(**item_dict)
            
            # Lógica de compatibilidad para PDF (Cumple si nota >= 3)
            if item_obj.puntuacion >= 3:
                item_obj.cumple = True
            else:
                item_obj.cumple = False
                
            items_procesados.append(item_obj)
        
        # Calcular Nota
        nota_final = calcular_nota_final(items_procesados)
        
        # Separar para el reporte PDF
        puntos_fuertes = [i for i in items_procesados if i.puntuacion >= 3]
        areas_mejora = [i for i in items_procesados if i.puntuacion < 3]
        
        reporte = ReporteCalidad(
            asesor=data.get("asesor", base_nombre),
            resumen_ejecutivo=data.get("resumen_ejecutivo", ""),
            puntos_fuertes=puntos_fuertes,
            areas_mejora=areas_mejora,
            nota_final_0_10=nota_final
        )

        # Guardar JSON (Nombre seguro)
        nombre_safe = re.sub(r'[^\w\-_]', '_', Path(nombre_archivo).stem)[:50]
        ruta_json = settings.OUTPUTS_DIR / "Reportes_JSON" / f"{nombre_safe}_reporte.json"
        ruta_json.parent.mkdir(exist_ok=True)
        
        with open(ruta_json, "w", encoding="utf-8") as f:
            f.write(reporte.model_dump_json(indent=2))
            
        print(f"✅ Reporte Generado: {ruta_json.name}")
        print(f"⭐️ NOTA CALIDAD: {nota_final}/10")
        
        return reporte

    except Exception as e:
        print(f"❌ Error procesando {nombre_archivo}: {e}")
        return None