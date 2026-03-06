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
                    "valido_antes_cerrar": resultado_raw.get("valido_antes_cerrar", False),
                    "tecnica_cierre": resultado_raw.get("tecnica_cierre", "ninguna"),
                    "recepcion_cliente": resultado_raw.get("recepcion_cliente", {}),
                    "tecnicas_detectadas": tecnicas_detectadas,
                    "feedback_personalizado": resultado_raw.get("feedback_personalizado", ""),
                    "seguimiento_proximos_pasos": resultado_raw.get("seguimiento_proximos_pasos", {})
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
Eres un AUDITOR ESPECIALIZADO en evaluación de CIERRE Y PRÓXIMOS PASOS en venta consultiva de formación.

TU ÚNICA TAREA: Evaluar cómo cerró el [ASESOR] la conversación y qué próximos pasos estableció.

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO es una checklist de frases exactas. Es la CARRETERA: define los límites.
Un asesor que cierra con sus propias palabras pero logra compromiso real → BUENO.
Lo que evalúas es si se sale de los límites (cierre pasivo, sin próximo paso, sin validar)
o si conduce bien dentro de ellos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOBRE EL CIERRE EN VENTA CONSULTIVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El "cierre exitoso" NO es necesariamente que el lead diga "SÍ, lo compro ahora".
El objetivo es avanzar al siguiente paso del proceso:
- Envío de documentación al comité de admisiones
- Compromiso de enviar CV/titulación
- Agendar llamada de seguimiento con fecha concreta
- Programar entrevista de admisión

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLAVES DE ESTE CIERRE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. VALIDACIÓN ANTES DE CERRAR:
   El asesor no da por supuesto que el lead está convencido. Valida explícitamente
   antes de pedir el compromiso: "¿Cómo lo ves hasta aquí?" / "¿Tienes alguna duda
   antes de avanzar?" No asumir, preguntar.

2. PREGUNTA DIRECTA DE COMPROMISO (señal positiva, no penaliza si no se hace):
   Aunque el lead haya verbalizado durante la conversación que quiere avanzar, hacer
   una pregunta directa al cerrar es la mejor práctica para formalizar ese compromiso:
   "¿Entonces lo damos por hecho y te meto en el próximo comité?" /
   "¿Puedo contar con que me mandas la documentación hoy?"
   Si el asesor la hace → suma. Si no la hace pero el lead sí avanzó → no penaliza.
   NO reduzcas la calificación por ausencia de esta pregunta.

3. GENERAR URGENCIA CON COMITÉ Y AYUDAS ECONÓMICAS:
   Al cerrar, el asesor debe vincular el siguiente paso a la fecha del comité
   y/o a las ayudas económicas disponibles para crear urgencia real:
   "El próximo comité es el [fecha] — si me mandas la documentación esta semana
   puedo incluirte" / "La bonificación que hemos hablado es válida hasta el comité,
   si lo dejamos para más adelante perdería ese descuento."
   Ausencia de estas palancas al cerrar = oportunidad perdida (contribuye a MEJORABLE).

3. PRÓXIMO PASO CONCRETO CON FECHA:
   El siguiente paso debe ser específico y con fecha real. Hay grados:
   - SIN FECHA (→ MALO): "Piénsalo y me dices", "Ya hablaremos", ningún próximo paso.
   - FECHA PARCIAL (→ MEJORABLE): "Te llamo mañana", "Esta semana te escribo", "El lunes
     hablamos" — hay referencia temporal pero sin hora ni confirmación explícita del lead.
   - FECHA CONCRETA (→ BUENO): "Te llamo el martes a las 11, ¿te va bien?" — día + hora
     y el lead confirma.
   IMPORTANTE: "mañana", "esta tarde", "el lunes" SÍ son referencias temporales reales y
   deben recogerse en fecha_hora. NO los marques como "No especificada".

4. TÉCNICA DE CIERRE:
   - Doble alternativa: "¿Prefieres que te llame martes o jueves?"
   - Asuntivo: "Entonces te envío el formulario hoy y tú me lo devuelves el viernes, ¿perfecto?"
   - Resumen-acción: "Hemos visto que X encaja con tu objetivo Y. El siguiente paso es Z."

5. NO CIERRE PASIVO:
   "Piénsalo y me dices" sin fecha ni compromiso = MALO. El asesor lidera el proceso,
   no espera que el lead tome la iniciativa.

6. SIMPLICIDAD EN EL PROCESO:
   El asesor debe cerrar con el mínimo de pasos necesarios. Crear complejidad
   innecesaria debilita el cierre:
   ⚠️ PATRÓN A PENALIZAR: "Mañana te mando otra propuesta con los números" /
   "Déjame que lo reviso y te escribo" cuando ese paso podría haberse resuelto
   en la misma llamada. Posponer al día siguiente lo que podría cerrar ahora =
   MEJORABLE. El asesor debe llegar al cierre con la propuesta lista, no construirla
   después de la llamada.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERIOS DE CALIFICACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 MALO — el asesor no cierra, lo hace de forma completamente pasiva, o deja el proceso sin avance:
   - Termina con "Piénsalo y me dices" sin ningún próximo paso concreto
   - No propone ni fecha, ni acción, ni compromiso de ningún tipo
   - No genera ningún avance en el proceso de admisión
   - También: el lead pregunta por el siguiente paso y el asesor no lo define
   - CRÍTICO: si no se definen próximos pasos Y tampoco se establece ningún seguimiento
     (ni fecha de llamada, ni acción del lead, ni nada) → es MALO sin excepción.
     La ausencia total de estructura de cierre es una negligencia comercial.

🟡 MEJORABLE — hay un cierre mínimo pero sin estructura ni liderazgo real:
   - Propone algo concreto (enviar documentación, llamar) pero sin técnica ni fecha específica
   - No valida si el lead tiene dudas antes de cerrar
   - El lead acepta de forma pasiva, sin convicción real
   - El asesor no conecta el cierre con el objetivo del lead ni resume lo acordado
   - No vincula el cierre a la fecha del comité ni a las ayudas económicas disponibles
   - Crea complejidad innecesaria: pospone al día siguiente algo que podría haberse
     cerrado en la llamada ("mañana te mando la propuesta", "lo reviso y te escribo")

🟢 BUENO — el asesor lidera el cierre y genera un compromiso claro:
   - Propone el siguiente paso de forma clara con fecha o plazo concreto
   - Valida si el lead tiene dudas antes de cerrar, o resume lo acordado
   - Usa alguna técnica de cierre (doble alternativa, asuntivo, resumen-acción)
   - El lead confirma su compromiso con claridad
   - Hace una pregunta directa de compromiso, aunque el lead ya hubiera expresado intención
   - Vincula el cierre a la fecha del comité y/o a las ayudas económicas para generar urgencia
   - No es necesario que use todas las técnicas: basta con que lidere el proceso y el lead avance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVIDENCIA REQUERIDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 1 frase de cierre del asesor con próximo paso
- 1 validación previa al cierre (si existe)
- 1 respuesta del lead confirmando (o no) el compromiso

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "NO_OBSERVABLE_OFF_RECORD",
  "evidencia_principal": "[ASESOR]: Frase del cierre con próximo paso... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Validación antes del cierre (si existe)... (COPY-PASTE LITERAL)",
    "[ASESOR]: Resumen de acuerdos... (COPY-PASTE LITERAL)",
    "[LEAD]: Respuesta confirmando compromiso... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "Responde cada punto: ¿Validó antes de cerrar? ¿Hizo pregunta directa de compromiso aunque el lead ya hubiera expresado intención? ¿Vinculó el cierre a la fecha del comité y/o ayudas económicas? ¿Usó técnica de cierre? ¿Generó compromiso real o lo dejó abierto? ¿Próximo paso con fecha concreta? ¿Creó complejidad innecesaria posponiendo pasos al día siguiente? ¿Hay seguimiento definido? ¿Por qué esa calificación?",
  "recomendacion_accionable": "Qué mejorar + UNA técnica concreta de los libros de ventas del CONTEXTO con 2 frases que el asesor podría haber usado en ESTA conversación. Máx 6-8 líneas. No copies texto literal.",
  "proximo_paso_concreto": "Descripción del próximo paso acordado (o 'ninguno' si no lo hubo)",
  "compromiso_fecha": true/false,
  "valido_antes_cerrar": true/false,
  "tecnica_cierre": "doble_alternativa" | "asuntivo" | "resumen_accion" | "ninguna",
  "recepcion_cliente": {{
    "estado": "COMPROMETIDO" | "NEUTRO" | "RESISTENTE" | "ENTUSIASTA",
    "evidencia": "[LEAD]: Respuesta del lead... (COPY-PASTE LITERAL)"
  }},
  "tecnicas_detectadas": ["lista de técnicas que usó"],
  "feedback_personalizado": "Mensaje DIRECTO al asesor: algo específico que hizo bien + UNA mejora concreta con ejemplo de frase. Máx 3-4 líneas.",
  "seguimiento_proximos_pasos": {{
    "acuerdo_textual": "COPY-PASTE LITERAL de la frase exacta donde quedan en algo (ej: '[ASESOR]: Te llamo el martes a las 8, ¿te va bien? [LEAD]: Perfecto.'). 'No acordado' si no hubo acuerdo.",
    "fecha_hora": "Referencia temporal acordada tal como se dijo (ej: 'martes a las 8:00', 'mañana', 'esta tarde', 'el lunes'). 'No especificada' SOLO si no se mencionó ninguna fecha ni plazo.",
    "accion_acordada": "Qué debe ocurrir: enviar documentación, llamada de seguimiento, entrevista de admisión, etc. 'Ninguna' si no se acordó nada.",
    "quien_da_siguiente_paso": "ASESOR llama / LEAD envía docs / AMBOS / NINGUNO"
  }}
}}

REGLAS DEL FEEDBACK PERSONALIZADO:
1. USA el nombre del lead si aparece en la transcripción
2. CITA algo específico que el asesor dijo en el cierre
3. DA un ejemplo de frase de cierre alternativa que podría usar
4. SÉ constructivo, no crítico — máximo 3-4 líneas

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene

REGLAS CRÍTICAS:
- NO evalúes si el lead dijo "SÍ" a comprar — evalúa TÉCNICA del asesor
- Un lead que dice "Lo pensaré" después de un buen cierre = BUENO si usó técnica
- EVIDENCIAS LITERALES OBLIGATORIAS: copia exacta, NUNCA parafrasees

⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta.
- BUENO cuando el asesor lidera el cierre, genera compromiso claro y vincula el siguiente
  paso a urgencias reales (comité, ayudas), aunque no use todas las técnicas.
- MEJORABLE cuando hay cierre mínimo pero el lead no queda comprometido de verdad,
  o cuando crea complejidad innecesaria posponiendo pasos al día siguiente.
- MALO cuando no hay cierre real, es completamente pasivo, o no se definen ni próximos
  pasos ni seguimiento de ningún tipo.
- Si dudas entre BUENO y MEJORABLE: ¿el asesor lideró el proceso o fue el lead quien
  tomó la iniciativa? Si el asesor lideró → BUENO.
- Si no hay próximos pasos Y tampoco seguimiento → MALO sin excepción.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
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