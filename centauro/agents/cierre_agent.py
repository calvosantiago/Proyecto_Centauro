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

            # Detectar técnicas
            tecnicas_detectadas = resultado_raw.get("tecnicas_detectadas", [])
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")

            # NOTA: El coaching se aplica en batch desde el orchestrator para optimizar llamadas API

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
                    "proximo_paso": proximo_paso,
                    "compromiso_fecha": resultado_raw.get("compromiso_fecha", False),
                    "tecnica_cierre": resultado_raw.get("tecnica_cierre", "ninguna"),
                    "recepcion_cliente": resultado_raw.get("recepcion_cliente", {}),
                    "tecnicas_detectadas": tecnicas_detectadas,
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

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

🔴 MALO — cuando el asesor no cierra o lo hace de forma pasiva:
   - Termina con "Piénsalo y me dices" sin ningún próximo paso concreto
   - Propone algo vago sin concreción ("Te mando info") sin fecha ni compromiso
   - No genera ningún avance real en el proceso de venta

🟡 MEJORABLE — cuando el asesor propone un próximo paso pero sin técnica:
   - Define un próximo paso concreto pero no usa ninguna técnica de cierre
   - No resume lo acordado ni maneja dudas finales con liderazgo
   - El lead acepta sin mayor compromiso emocional o convicción

🟢 BUENO — cuando el asesor cierra con estructura y el lead confirma compromiso:
   - Resume lo acordado y propone próximo paso con fecha concreta
   - Usa alguna técnica de cierre (doble alternativa, asuntivo, resumen-acción)
   - Pide compromiso explícito y el lead lo confirma con claridad

TÉCNICAS DE CIERRE COMUNES:
- Doble alternativa: "¿Prefieres que te llame martes o jueves?"
- Asuntivo: "Entonces te envío el formulario hoy y tú me lo devuelves el viernes, ¿perfecto?"
- Resumen-acción: "Hemos visto que X encaja con tu objetivo Y. El siguiente paso es Z."

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "NO_OBSERVABLE_OFF_RECORD",
  "evidencia_principal": "[ASESOR]: Frase del cierre con próximo paso... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Resumen de acuerdos... (COPY-PASTE LITERAL)",
    "[LEAD]: Respuesta confirmando compromiso... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Propuso paso concreto? ¿Usó técnica? ¿Generó compromiso? ¿Manejó dudas finales? ¿Por qué esa calificación?",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases adaptadas a ESTA conversación. Máx 6-8 líneas. NO copies texto literal de los libros.",
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

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene (ej: "Como sugiere Cialdini...")

REGLAS CRÍTICAS:
- NO evalúes si el lead dijo "SÍ" a comprar - evalúa TÉCNICA del asesor
- Un lead que dice "Lo pensaré" después de un buen cierre = 4.0 si usó técnica
- EVIDENCIAS LITERALES OBLIGATORIAS: Copia exacta, NUNCA parafrasees

⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta.
- BUENO no requiere un cierre de libro, requiere próximo paso + fecha + alguna técnica + compromiso del lead.
- MEJORABLE es cuando define un paso pero sin técnica ni resumen.
- MALO cuando no hay próximo paso real o termina con "piénsalo".
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta mejorar.
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
            calificacion=None,
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