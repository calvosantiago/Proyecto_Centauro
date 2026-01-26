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

CRITERIOS ESPECÍFICOS (Escala DECIMAL 1.0-5.0):
⚠️ USA DECIMALES: 3.0, 3.5, 4.0, 4.5, etc.

🎯 CALIBRACIÓN: La mayoría de llamadas deben estar en 3.0-3.5 (correcto).

1.0-1.5 = PASIVO / SIN CIERRE
   - Termina con "Piénsalo y me dices"
   - No propone próximo paso concreto
   - Despedida genérica sin acción
   EJEMPLO: "[ASESOR]: Bueno, cualquier duda me escribes. ¡Suerte!"

2.0-2.5 = DÉBIL / PRÓXIMO PASO VAGO
   - Propone algo sin concreción: "Te mando info"
   - NO establece fecha ni hora
   - Lead puede ignorar fácilmente
   EJEMPLO: "[ASESOR]: Te envío el brochure por correo. [LEAD]: OK."

3.0 = ADMINISTRATIVO / PASO DEFINIDO SIN TÉCNICA ⭐ (MÁS COMÚN)
   - Propone próximo paso concreto: "Te envío el formulario"
   - Pero NO usa técnica de cierre
   - No resume acuerdos ni maneja dudas con liderazgo
   EJEMPLO: "[ASESOR]: Te mando el formulario de admisión. [LEAD]: Vale, gracias."

3.5 = CORRECTO CON INTENTO DE COMPROMISO
   - Todo lo del 3.0 PERO pide compromiso básico
   - Ejemplo: menciona fecha aunque el lead no confirma claramente
   EJEMPLO: "[ASESOR]: Te lo envío hoy y me lo devuelves esta semana, ¿vale? [LEAD]: Sí, lo reviso."

4.0 = BUENO / CIERRE ESTRUCTURADO
   - Resume lo acordado: "Entonces quedamos en que..."
   - Próximo paso + fecha CONCRETA
   - Pide compromiso explícito: "¿Te viene bien el martes?"
   - Verifica dudas finales con liderazgo
   EJEMPLO: "[ASESOR]: Perfecto María. Entonces quedamos: te envío el formulario hoy, tú me lo devuelves el viernes, y el lunes tenemos la entrevista de admisión. ¿Te viene bien a las 10am? [LEAD]: Sí, perfecto."

4.5 = MUY BUENO / CASI MAESTRÍA
   - Todo lo del 4.0 PERO añade resumen de beneficios antes de cerrar
   - O usa UNA técnica de cierre (doble alternativa o asuntivo)

5.0 = MAESTRÍA / CIERRE CONSULTIVO (RARO)
   - Resume beneficios clave ANTES de cerrar
   - Usa técnica de cierre efectiva (doble alternativa o asuntivo)
   - Maneja dudas de último minuto SIN perder momentum
   - Genera entusiasmo visible en el lead
   - Lead confirma compromiso claramente
   EJEMPLO: "[ASESOR]: María, hemos visto que el máster cubre exactamente tu gap en finanzas y además la modalidad flexible encaja con tu horario de trabajo. Perfecto. Ahora el siguiente paso es la entrevista de admisión, ¿prefieres que la hagamos el martes a las 10 o el jueves a las 15? [LEAD]: El martes perfecto. [ASESOR]: Genial, agendo martes 10am. Te envío la confirmación ahora y nos vemos entonces. ¿Alguna duda de último momento? [LEAD]: No, todo claro. ¡Gracias!"

TÉCNICAS DE CIERRE COMUNES:
- Doble alternativa: "¿Prefieres que te llame martes o jueves?"
- Asuntivo: "Entonces te envío el formulario hoy y tú me lo devuelves el viernes, ¿perfecto?"
- Resumen-acción: "Hemos visto que X encaja con tu objetivo Y. El siguiente paso es Z."

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3.0,  ← USA DECIMALES: 3.0, 3.5, 4.0, etc.
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
- NO evalúes si el lead dijo "SÍ" a comprar - evalúa TÉCNICA del asesor
- Un lead que dice "Lo pensaré" después de un buen cierre = 4.0 si usó técnica
- EVIDENCIAS LITERALES OBLIGATORIAS: Copia exacta, NUNCA parafrasees

⚠️ CALIBRACIÓN ESTRICTA:
- El 3.0 es "CORRECTO" - NO es malo, es lo esperado en mayoría de casos
- NO des 4.0+ solo porque "fue decente" - el 4.0 requiere resumen + fecha + compromiso verificado
- El 5.0 requiere: resumen beneficios + técnica de cierre + manejo dudas + entusiasmo del lead
- USA DECIMALES: Si está entre 3.0 y 4.0, usa 3.5
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