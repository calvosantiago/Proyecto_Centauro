"""
Agente Evaluador: Cierre y Próximos Pasos

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\cierre_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt
import re

class CierreAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo el asesor cierra la conversación y establece próximos pasos
    
    IMPORTANTE: El cierre NO es necesariamente una venta inmediata.
    En venta consultiva de formación, el objetivo suele ser:
    - Comprometer envío de documentación al comité de admisiones
    - Agendar próxima llamada/reunión
    - Establecer fecha concreta para siguiente paso
    
    Criterios clave:
    - Define próximo paso claro y específico
    - Genera compromiso (fecha/hora)
    - Resume lo acordado
    - Usa técnica de cierre (no solo "piénsalo")
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Cierre y próximos pasos")
        self.longitud_analisis = 2500  # Últimos 2500 caracteres
    
    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """Evalúa el cierre usando principalmente el final de la conversación"""
        
        # Extraer final de la conversación
        final_conversacion = transcripcion[-self.longitud_analisis:]
        
        # Detectar si la conversación terminó abruptamente (off-record)
        if self._detectar_fin_abrupto(final_conversacion):
            return self._crear_resultado_off_record()
        
        try:
            resultado_raw = self._evaluar_con_llm(final_conversacion, transcripcion, contexto_manual)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar que haya próximo paso concreto
            proximo_paso = resultado_raw.get("proximo_paso_concreto", "")
            if not proximo_paso or "vago" in proximo_paso.lower():
                print(f"   ⚠️ Próximo paso no suficientemente concreto")
                confianza *= 0.8
            
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
                    "proximo_paso": proximo_paso,
                    "compromiso_fecha": resultado_raw.get("compromiso_fecha", False),
                    "tecnica_cierre": resultado_raw.get("tecnica_cierre", "ninguna"),
                    "recepcion_cliente": resultado_raw.get("recepcion_cliente", {})
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Cierre: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, final: str, transcripcion_completa: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado"""
        
        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de CIERRE Y PRÓXIMOS PASOS en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo cerró el [ASESOR] la conversación y qué próximos pasos estableció.

CONTEXTO DEL MANUAL:
{manual}

IMPORTANTE SOBRE CIERRE EN VENTA CONSULTIVA:
En este contexto, el "cierre exitoso" NO es necesariamente que el lead diga "SÍ, lo compro".
El objetivo suele ser avanzar al siguiente paso del proceso:
- Envío de documentación al comité de admisiones
- Compromiso de enviar CV/titulación
- Agendar llamada de seguimiento
- Programar entrevista de admisión

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = PASIVO / SIN CIERRE
   - Termina con "Piénsalo y me dices"
   - No propone próximo paso concreto
   - No genera ningún compromiso
   - Despedida genérica sin acción

2 = DÉBIL / PRÓXIMO PASO VAGO
   - Propone algo pero sin concreción ("Te mando info")
   - No establece fecha ni hora
   - No genera compromiso del lead
   - El lead puede ignorar fácilmente

3 = ADMINISTRATIVO / PASO DEFINIDO SIN TÉCNICA
   - Propone próximo paso concreto ("Te envío el formulario")
   - Pero no usa técnica de cierre
   - No resume acuerdos
   - No maneja dudas finales con liderazgo

4 = BUENO / CIERRE ESTRUCTURADO
   - Resume lo acordado ("Entonces quedamos en que...")
   - Propone próximo paso + fecha concreta
   - Pide compromiso explícito ("¿Te viene bien el martes?")
   - Verifica dudas finales
   - Genera sensación de avance

5 = MAESTRÍA / CIERRE CONSULTIVO
   - Todo lo anterior PLUS:
   - Usa técnica de cierre (doble alternativa, asuntivo, etc.)
   - Maneja dudas de último minuto sin perder momentum
   - Resume beneficios clave antes de cerrar
   - Genera entusiasmo en el lead sobre el próximo paso
   - El lead confirma compromiso de forma clara

TÉCNICAS DE CIERRE COMUNES:
- Doble alternativa: "¿Prefieres que te llame martes o jueves?"
- Asuntivo: "Entonces te envío el formulario hoy y tú me lo devuelves el viernes, ¿perfecto?"
- Resumen-acción: "Hemos visto que X encaja con tu objetivo Y. El siguiente paso es Z."

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "NO_OBSERVABLE_OFF_RECORD",
  "evidencia_principal": "[ASESOR]: Frase del cierre con próximo paso... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Resumen de acuerdos... (COPY-PASTE LITERAL)",
    "[LEAD]: Respuesta confirmando compromiso... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Propuso paso concreto? ¿Usó técnica? ¿Generó compromiso? ¿Manejó dudas finales? ¿Qué faltó para la nota siguiente?",
  "recomendacion_accionable": "Acción específica para mejorar (sin repetir lo ya logrado)",
  "gap_para_5": "Si nota es 3 o 4, explica ESPECÍFICAMENTE qué faltó para alcanzar el 5. Si nota es 5, pon 'N/A - Ya alcanzado'",
  "proximo_paso_concreto": "Descripción del próximo paso acordado",
  "compromiso_fecha": true/false,
  "tecnica_cierre": "doble_alternativa" | "asuntivo" | "resumen_accion" | "ninguna",
  "recepcion_cliente": {{
    "estado": "COMPROMETIDO" | "NEUTRO" | "RESISTENTE" | "ENTUSIASTA",
    "evidencia": "[LEAD]: Respuesta del lead... (COPY-PASTE LITERAL)"
  }}
}}

REGLAS CRÍTICAS:
- NO evalúes si el lead dijo "SÍ" a comprar
- Evalúa si el ASESOR aplicó buena técnica de cierre para avanzar
- Un lead que dice "Lo pensaré" después de un buen cierre es válido (nota 4 si usó técnica)
- EVIDENCIAS LITERALES OBLIGATORIAS: Copia exacta de la transcripción, NUNCA parafrasees
- ⚠️ IMPORTANTE: El 5/5 ES ALCANZABLE si cumple todos los criterios de MAESTRÍA
- Si la ejecución es realmente excelente (resumen + técnica + compromiso + manejo dudas), NO te limites a dar 4
- En "gap_para_5" explica QUÉ FALTÓ específicamente (ej: "Faltó resumir beneficios clave antes del cierre")
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta mejorar
"""
        
        prompt_usuario = f"""
Contexto completo (para entender el flujo):
{transcripcion_completa[:1000]}
[...]

FINAL DE LA CONVERSACIÓN (enfócate aquí):
{final}

Evalúa el cierre y próximos pasos en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_cierre")
        return self._extract_json_safe(resp)
    
    def _detectar_fin_abrupto(self, final: str) -> bool:
        """Detecta si la grabación cortó antes del cierre"""
        final_lower = final.lower()
        
        indicadores = [
            "continuará",
            "seguimos hablando",
            "ahora tengo que",
            "me está entrando otra llamada"
        ]
        
        for indicador in indicadores:
            if indicador in final_lower:
                return True
        
        # Si el final tiene menos de 200 chars y no hay despedida
        if len(final) < 200:
            despedidas = ["gracias", "hasta", "adiós", "perfecto", "genial"]
            tiene_despedida = any(d in final_lower for d in despedidas)
            if not tiene_despedida:
                return True
        
        return False
    
    def _crear_resultado_off_record(self) -> EvaluationResult:
        """Resultado para casos donde la grabación cortó antes del cierre"""
        return EvaluationResult(
            bloque=self.nombre_bloque,
            puntuacion_1_5=None,
            observabilidad="NO_OBSERVABLE_OFF_RECORD",
            confianza=1.0,
            evidencia_principal="Grabación finalizó antes del cierre (corte detectado)",
            evidencias_extra=[],
            razonamiento=(
                "La conversación parece haber sido interrumpida o la grabación finalizó "
                "antes del cierre formal. No se puede evaluar este bloque."
            ),
            recomendacion_accionable="Verificar que la grabación capture la conversación completa hasta la despedida"
        )