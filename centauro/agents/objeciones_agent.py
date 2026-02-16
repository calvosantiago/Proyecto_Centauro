"""
Agente Evaluador: Manejo de Objeciones

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\objeciones_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class ObjecionesAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo el asesor maneja las dudas y resistencias del cliente
    
    Criterios clave:
    - Valida la objeción (no la ignora ni minimiza)
    - Aísla la objeción real del pretexto
    - Usa técnicas estructuradas (feel-felt-found, etc.)
    - No presiona, ayuda a resolver
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Manejo de objeciones")
    
    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa el manejo de objeciones"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar que se detectaron objeciones
            objeciones_detectadas = resultado_raw.get("objeciones_identificadas", [])
            
            if len(objeciones_detectadas) == 0:
                print(f"   ℹ️ No se detectaron objeciones en la conversación")
                # No es malo, simplemente no hubo objeciones
                resultado_raw["observabilidad"] = "NO_OBSERVABLE"
                resultado_raw["calificacion"] = None

            # NOTA: El coaching se aplica en batch desde el orchestrator para optimizar llamadas API
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_base,
                metadata={
                    "num_objeciones": len(objeciones_detectadas),
                    "objeciones_identificadas": objeciones_detectadas,
                    "tecnica_detectada": resultado_raw.get("tecnica_detectada", "ninguna")
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Objeciones: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de MANEJO DE OBJECIONES en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo manejó el [ASESOR] las dudas y resistencias del cliente.

CONTEXTO DEL MANUAL:
{manual_enriquecido}

IMPORTANTE: Si NO hay objeciones claras del [LEAD], marca observabilidad "NO_OBSERVABLE" y calificacion: null

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

🔴 MALO — cuando el asesor maneja la objeción de forma contraproducente:
   - Ignora o minimiza la objeción del lead
   - Se pone a la defensiva ("No es caro, otros cobran más")
   - Presiona al lead sin escucharle ("Tienes que decidirte ya")
   - Genera más resistencia en vez de reducirla

🟡 MEJORABLE — cuando el asesor responde pero sin técnica ni profundidad:
   - Responde con información correcta pero de forma mecánica
   - No valida la preocupación ni profundiza en el porqué de la objeción
   - El lead queda igual de dudoso después de la respuesta
   - Intenta resolver pero no usa ninguna técnica estructurada

🟢 BUENO — cuando el asesor maneja la objeción con técnica y el lead suaviza su postura:
   - Valida la objeción ("Entiendo tu preocupación...")
   - Profundiza para entender la objeción real ("¿Es solo el tiempo o hay algo más?")
   - Usa técnica estructurada (feel-felt-found, boomerang, aislamiento, etc.)
   - El lead suaviza su resistencia o expresa más apertura

TIPOS COMUNES DE OBJECIONES:
- Precio ("Es caro", "No tengo presupuesto")
- Tiempo ("No tengo tiempo", "Es muy largo")
- Autoridad ("Tengo que consultarlo", "Mi empresa debe aprobarlo")
- Necesidad ("No estoy seguro si lo necesito")
- Urgencia ("Lo pensaré", "Más adelante")

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO" | null,
  "observabilidad": "ALTA" | "NO_OBSERVABLE",
  "evidencia_principal": "[LEAD]: Objeción principal... [ASESOR]: Respuesta... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Validación de la objeción... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción posterior... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Validó? ¿Aisló? ¿Usó técnica? ¿Resolvió o generó más resistencia? ¿Por qué esa calificación?",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases adaptadas a ESTA conversación. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "objeciones_identificadas": ["tipo de objeción 1", "tipo 2"],
  "tecnica_detectada": "feel-felt-found" | "boomerang" | "aislamiento" | "ninguna"
}}

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene

REGLAS CRÍTICAS:
- Evidencias LITERALES de la transcripción (COPY-PASTE exacto)
- Si no hay objeciones → observabilidad "NO_OBSERVABLE" y calificacion: null
- NO evalúes si el lead compró, evalúa si el ASESOR manejó bien la resistencia
- Una objeción bien manejada puede dejar al lead pensando (eso es OK)
⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta (o null si no hay objeciones).
- BUENO requiere validación + alguna técnica + que el lead suavice su postura.
- MEJORABLE es responder correctamente pero sin técnica ni profundidad.
- MALO cuando el asesor agrava la situación o ignora la objeción.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Identifica y evalúa el manejo de objeciones en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_objeciones")
        return self._extract_json_safe(resp)