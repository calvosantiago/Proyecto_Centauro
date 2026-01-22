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
    
    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """Evalúa el manejo de objeciones"""
        
        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar que se detectaron objeciones
            objeciones_detectadas = resultado_raw.get("objeciones_identificadas", [])
            
            if len(objeciones_detectadas) == 0:
                print(f"   ℹ️ No se detectaron objeciones en la conversación")
                # No es malo, simplemente no hubo objeciones
                resultado_raw["observabilidad"] = "NO_OBSERVABLE"
                resultado_raw["puntuacion_1_5"] = None
            
            return EvaluationResult(
                bloque=self.nombre_bloque,
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", ""),
                metadata={
                    "num_objeciones": len(objeciones_detectadas),
                    "objeciones_identificadas": objeciones_detectadas,
                    "tecnica_detectada": resultado_raw.get("tecnica_detectada", "ninguna")
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Objeciones: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado"""
        
        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de MANEJO DE OBJECIONES en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo manejó el [ASESOR] las dudas y resistencias del cliente.

CONTEXTO DEL MANUAL:
{manual}

IMPORTANTE: Si NO hay objeciones claras del [LEAD], marca observabilidad "NO_OBSERVABLE" y puntuacion_1_5: null

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = PÉSIMO / DEFENSIVO
   - Ignora o minimiza la objeción
   - Se pone a la defensiva ("No es caro, otros cobran más")
   - Presiona al lead ("Tienes que decidirte ya")
   - Genera más resistencia

2 = INSUFICIENTE / RESPUESTA DÉBIL
   - Responde superficialmente sin resolver la duda real
   - No valida la preocupación del lead
   - Da información pero no persuade
   - El lead queda igual de dudoso

3 = CORRECTO / MANEJO ESTÁNDAR (Robot)
   - Responde con información correcta
   - Intenta resolver pero de forma mecánica
   - No profundiza en el PORQUÉ de la objeción
   - Funcional pero no elimina la resistencia

4 = BUENO / TÉCNICA ESTRUCTURADA
   - Valida la objeción ("Entiendo tu preocupación...")
   - Aísla la objeción real ("¿Es solo el tiempo o hay algo más?")
   - Usa técnica (feel-felt-found, boomerang, etc.)
   - Resuelve con ejemplos o casos
   - El lead suaviza su postura

5 = MAESTRÍA / TRANSFORMACIÓN
   - Valida emocionalmente ("Tiene sentido que pienses así")
   - Convierte la objeción en motivo para comprar
   - Usa storytelling o social proof efectivo
   - Genera micro-compromiso ("Si resolvemos esto, ¿seguimos?")
   - El lead pasa de resistencia a apertura

TIPOS COMUNES DE OBJECIONES:
- Precio ("Es caro", "No tengo presupuesto")
- Tiempo ("No tengo tiempo", "Es muy largo")
- Autoridad ("Tengo que consultarlo", "Mi empresa debe aprobarlo")
- Necesidad ("No estoy seguro si lo necesito")
- Urgencia ("Lo pensaré", "Más adelante")

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "NO_OBSERVABLE",
  "evidencia_principal": "[LEAD]: Objeción principal... [ASESOR]: Respuesta... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Validación de la objeción... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción posterior... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Validó? ¿Aisló? ¿Usó técnica? ¿Resolvió o generó más resistencia? ¿Qué faltó para la nota siguiente?",
  "recomendacion_accionable": "Acción específica (sin repetir lo ya logrado)",
  "gap_para_5": "Si nota es 3 o 4, explica ESPECÍFICAMENTE qué faltó para alcanzar el 5. Si nota es 5, pon 'N/A - Ya alcanzado'",
  "objeciones_identificadas": ["tipo de objeción 1", "tipo 2"],
  "tecnica_detectada": "feel-felt-found" | "boomerang" | "aislamiento" | "ninguna"
}}

REGLAS CRÍTICAS:
- Evidencias LITERALES de la transcripción (COPY-PASTE exacto)
- Si no hay objeciones → observabilidad "NO_OBSERVABLE" y puntuacion_1_5: null
- NO evalúes si el lead compró, evalúa si el ASESOR manejó bien la resistencia
- Una objeción bien manejada puede dejar al lead pensando (eso es OK)
- ⚠️ IMPORTANTE: El 5/5 ES ALCANZABLE si cumple todos los criterios de MAESTRÍA
- Si la ejecución es excelente, NO te limites a dar 4
- En "gap_para_5" sé específico (ej: "Faltó usar social proof o caso de éxito")
- En "recomendacion_accionable" NO repitas lo que ya hizo bien
"""
        
        prompt_usuario = f"""
Identifica y evalúa el manejo de objeciones en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_objeciones")
        return self._extract_json_safe(resp)