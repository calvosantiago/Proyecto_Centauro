"""
Agente Evaluador: Cierre y Próximos Pasos (v4.1)

Evalúa:
- Cómo el asesor cierra la conversación
- Establecimiento de próximos pasos
- Técnicas de cierre utilizadas

NUEVO v4.1:
- Detección de técnicas de cierre avanzadas
- Feedback personalizado con coaching de libros
- Bonificación por técnicas efectivas
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

    v4.1: Detecta y premia técnicas de cierre, genera coaching personalizado
    """

    def __init__(self):
        super().__init__(nombre_bloque="Cierre y próximos pasos")
        self.longitud_analisis = 2500  # Últimos 2500 caracteres

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa el cierre usando principalmente el final de la conversación"""

        # Extraer final de la conversación
        final_conversacion = transcripcion[-self.longitud_analisis:]

        # Detectar si la conversación terminó abruptamente (off-record)
        if self._detectar_fin_abrupto(final_conversacion):
            return self._crear_resultado_off_record()

        try:
            resultado_raw = self._evaluar_con_llm(final_conversacion, transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)

            # Validar que haya próximo paso concreto
            proximo_paso = resultado_raw.get("proximo_paso_concreto", "")
            if not proximo_paso or "vago" in proximo_paso.lower():
                print(f"   ⚠️ Próximo paso no suficientemente concreto")
                confianza *= 0.8

            # NUEVO: Detectar técnicas y enriquecer recomendación
            tecnicas_detectadas = resultado_raw.get("tecnicas_detectadas", [])
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            gap_para_5 = resultado_raw.get("gap_para_5", "")

            # Enriquecer con coaching si hay área de mejora clara
            if gap_para_5 and "N/A" not in gap_para_5:
                recomendacion_enriquecida = self.enriquecer_recomendacion_con_coaching(
                    recomendacion_base,
                    area_mejora="técnicas de cierre y compromiso"
                )
            else:
                recomendacion_enriquecida = recomendacion_base

            return EvaluationResult(
                bloque=self.nombre_bloque,
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_enriquecida,
                metadata={
                    "proximo_paso": proximo_paso,
                    "compromiso_fecha": resultado_raw.get("compromiso_fecha", False),
                    "tecnica_cierre": resultado_raw.get("tecnica_cierre", "ninguna"),
                    "recepcion_cliente": resultado_raw.get("recepcion_cliente", {}),
                    "tecnicas_detectadas": tecnicas_detectadas,
                    "gap_para_5": gap_para_5,
                    "feedback_personalizado": resultado_raw.get("feedback_personalizado", "")
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Cierre: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, final: str, transcripcion_completa: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion_completa)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de CIERRE Y PRÓXIMOS PASOS en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo cerró el [ASESOR] la conversación y qué próximos pasos estableció.

CONTEXTO DEL MANUAL:
{manual_enriquecido}

IMPORTANTE SOBRE CIERRE EN VENTA CONSULTIVA:
En este contexto, el "cierre exitoso" NO es necesariamente que el lead diga "SÍ, lo compro".
El objetivo suele ser avanzar al siguiente paso del proceso:
- Envío de documentación al comité de admisiones
- Compromiso de enviar CV/titulación
- Agendar llamada de seguimiento
- Programar entrevista de admisión

CRITERIOS ESPECÍFICOS (Escala DECIMAL 1.0-5.0):
⚠️ USA TODA LA ESCALA. Si el cierre es excelente, da 4.5 o 5.0.

1.0-1.5 = PASIVO / SIN CIERRE
   - Termina con "Piénsalo y me dices", sin próximo paso concreto

2.0-2.5 = DÉBIL / PRÓXIMO PASO VAGO
   - Propone algo sin concreción ("Te mando info"), sin fecha ni hora

3.0 = ADMINISTRATIVO / PASO DEFINIDO SIN TÉCNICA
   - Propone próximo paso concreto pero no usa técnica de cierre
   - No resume acuerdos ni maneja dudas con liderazgo

3.5 = CORRECTO CON INTENTO DE COMPROMISO
   - Paso concreto + pide compromiso básico (menciona fecha)

4.0 = BUENO / CIERRE ESTRUCTURADO
   - Resume lo acordado, próximo paso + fecha concreta
   - Pide compromiso explícito, verifica dudas finales

4.5 = MUY BUENO
   - Añade resumen de beneficios antes de cerrar
   - O usa técnica de cierre (doble alternativa, asuntivo)
   - Lead confirma compromiso

5.0 = EXCELENTE / CIERRE CONSULTIVO
   - Resume beneficios clave vinculados al lead ANTES de cerrar
   - Usa técnica de cierre efectiva
   - Maneja dudas finales sin perder momentum
   - Lead confirma compromiso con claridad

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
  }},
  "tecnicas_detectadas": ["lista de técnicas que usó, ej: 'doble alternativa', 'resumen beneficios', 'cierre asuntivo'"],
  "feedback_personalizado": "Mensaje DIRECTO al asesor reconociendo algo ESPECÍFICO que hizo bien y sugiriendo UNA mejora concreta con ejemplo de frase"
}}

🎯 FEEDBACK PERSONALIZADO - INSTRUCCIONES CRÍTICAS:
El campo "feedback_personalizado" debe ser un mensaje que el asesor pueda leer y sentir que es PARA ÉL/ELLA.

MALO (genérico): "El asesor debería usar técnicas de cierre"
BUENO (personalizado): "Bien hecho al proponer enviar el formulario hoy. Para subir al siguiente nivel, antes de cerrar podrías haber resumido: 'María, hemos visto que el MBA encaja con tu objetivo de liderar equipos y la modalidad flexible te permite seguir trabajando. ¿Te parece que avancemos con la documentación?'"

REGLAS DEL FEEDBACK PERSONALIZADO:
1. USA el nombre del lead si aparece en la transcripción
2. CITA algo específico que el asesor dijo en el cierre
3. DA un ejemplo de frase de cierre alternativa que podría usar
4. SÉ constructivo, no crítico
5. Máximo 3-4 líneas, directo al grano

REGLAS CRÍTICAS:
- NO evalúes si el lead dijo "SÍ" a comprar - evalúa TÉCNICA del asesor
- Un lead que dice "Lo pensaré" después de un buen cierre = 4.0 si usó técnica
- EVIDENCIAS LITERALES OBLIGATORIAS: Copia exacta, NUNCA parafrasees

⚠️ CALIBRACIÓN JUSTA:
- USA TODA LA ESCALA: si el cierre es excelente, da 4.5 o 5.0
- NO limites artificialmente las notas. Si cumple los criterios, puntúa en consecuencia
- Un asesor que resume, propone fecha, usa técnica y el lead confirma merece 4.5+
- USA DECIMALES: Si está entre 3.0 y 4.0, usa 3.5
- En "gap_para_5" explica QUÉ FALTÓ específicamente (ej: "Faltó resumir beneficios clave antes del cierre")
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta mejorar
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
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