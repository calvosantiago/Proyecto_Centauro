"""
Agente Evaluador: Proceso de Admisión y Propuesta Económica

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\admision_economica_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt


class AdmisionEconomicaAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo se explica el proceso de admisión y la propuesta económica

    Criterios clave:
    - Claridad en explicación del proceso de admisión
    - Presentación transparente de inversión y financiación
    - Manejo profesional de la conversación sobre precio
    - Genera confianza sin presión comercial
    - Facilita decisión informada
    """

    def __init__(self):
        super().__init__(nombre_bloque="Proceso de Admisión y Propuesta Económica")

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa admisión y propuesta económica"""
        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)

            # Validar que se haya mencionado precio/inversión
            menciona_precio = resultado_raw.get("menciona_precio", False)
            if not menciona_precio:
                print(f"   ⚠️ No se detectó mención de inversión/precio")
                confianza *= 0.7

            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "MEDIA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_base,
                metadata={
                    "menciona_precio": menciona_precio,
                    "explica_financiacion": resultado_raw.get("explica_financiacion", False),
                    "menciona_comite": resultado_raw.get("menciona_comite", False),
                    "comite_con_emocion": resultado_raw.get("comite_con_emocion", False),
                    "valor_antes_precio": resultado_raw.get("valor_antes_precio", False),
                    "usa_storytelling": resultado_raw.get("usa_storytelling", False),
                    "secuencia_correcta": resultado_raw.get("secuencia_correcta", False),
                    "claridad_admision": resultado_raw.get("claridad_admision", "MEDIA"),
                    "enfoque_valor_vs_precio": resultado_raw.get("enfoque_valor_vs_precio", "precio"),
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Admisión/Económica: {e}")
            return self._create_fallback_result(str(e))

    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de PROCESO DE ADMISIÓN Y PROPUESTA ECONÓMICA en venta consultiva de formación.

TU TAREA: Evaluar cómo el [ASESOR] presenta el comité de admisión, construye valor y maneja la propuesta económica.

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO es una checklist de frases que el asesor debe decir palabra por palabra.
Es la CARRETERA: define los límites de lo que se puede y no se puede hacer.
Un asesor que construye valor con sus propias palabras pero logra el objetivo → BUENO.
Lo que evalúas es si se sale de los límites (dar precio sin contexto, omitir comité, etc.)
o si conduce bien dentro de ellos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALCANCE: EVALÚA TODA LA CONVERSACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Los bloques de la entrevista son una guía organizativa, no límites de evaluación.
Busca activamente en TODA la transcripción:

  ✓ Señales del perfil financiero del lead (quién paga, capacidad económica, expectativas)
    → Pueden surgir durante la investigación, no solo cuando se presenta el precio
  ✓ Momentos de construcción de valor (beneficios, diferenciadores, ROI)
    → El asesor puede haber construido valor desde el inicio de la llamada
  ✓ Reacciones del lead al precio en cualquier momento de la conversación
  ✓ Storytelling o casos de alumni mencionados en cualquier sección

Si encuentras alguno de estos elementos en cualquier parte de la conversación,
tenlos en cuenta para la evaluación. El análisis financiero puede haberse hecho
en la investigación y el valor puede haberse construido antes del bloque económico.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLAVES DE ESTA FASE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ANÁLISIS FINANCIERO DEL LEAD:
   El asesor debe explorar la situación económica del lead ANTES de hablar de precio
   y ANTES de ofrecer alternativas de pago (cuotas, menor inscripción, financiación).
   No se trata de interrogar, sino de entender su capacidad y expectativas.
   Perfiles válidos de pago: inversión propia, empresa, familia/padres. No penalices
   porque sean los padres quienes paguen — es un perfil legítimo que el asesor debe
   conocer para adaptar su discurso.
   ⚠️ PATRÓN A DETECTAR: si el asesor ofrece cuotas adicionales o reduce la inscripción
   SIN haber preguntado antes la situación financiera del lead, está quemando herramientas
   de negociación. Menciónalo en el razonamiento como oportunidad perdida.

2. COMITÉ DE ADMISIÓN:
   El comité de admisión genera importancia, exclusividad y emoción en el lead.
   Aunque sea un proceso interno, el lead no lo sabe, y debe sentir que está siendo
   evaluado/seleccionado, no solo comprando. El asesor debe:
   - Mencionar el comité con convicción y darle peso real
   - Generar ilusión y sentido de oportunidad ("No todos los candidatos son admitidos")
   - No mencionar el comité de forma mecánica o de pasada

3. VALOR ANTES QUE PRECIO:
   El precio NUNCA se da al inicio. Primero se construye todo el valor del programa
   (qué incluye, beneficios, diferenciadores, ROI) y SOLO DESPUÉS se menciona la
   inversión completa. El orden correcto es:
   → Valor completo (lo que incluye, lo que te aporta) → Precio sin descuento → Descuento
   Un asesor que da el precio antes de construir el valor = MALO en este bloque.

4. DESCUENTO COMO REMATE, NO COMO PUNTO DE PARTIDA:
   El descuento se presenta DESPUÉS de haber explicado el valor completo y mencionado
   el precio de lista. Ejemplo correcto:
   "El programa completo tiene un valor de 7.700€ [pausa — el lead asimila el valor].
   En este momento contamos con una bonificación especial que lo deja en X€."
   Un asesor que abre con el precio rebajado o lo da sin contexto = MEJORABLE o MALO.

5. VALIDACIÓN TRAS LA PROPUESTA:
   Después de presentar el precio, el asesor debe verificar que el lead lo ha procesado
   y saber cuál es su reacción antes de avanzar. No da por supuesto que el lead aceptó.
   Preguntas de comprobación: "¿Cómo lo ves?" / "¿Qué te parece?" / "¿Esto encaja con
   lo que tenías en mente?"
   Ausencia de esta validación = oportunidad perdida de detectar objeciones a tiempo.

5b. SEGURIDAD EN EL PRECIO:
   Cuando el lead pide más descuento, el asesor debe mantener una posición firme pero
   consultiva: presentar la propuesta completa (lo que sí puede ofrecer), preguntar si
   le va bien, y ENTONCES comprometerse a pedir aprobación para esa tarifa concreta.
   ⚠️ PATRÓN A PENALIZAR: respuestas evasivas como "voy a revisar si hay alguna ayuda
   adicional que te pueda aprobar" generan inseguridad en el lead e impiden cerrar
   cualquier compromiso económico en la entrevista. El asesor debe presentar UNA
   propuesta concreta y cerrar sobre ella, no dejar todo abierto.

6. STORYTELLING:
   Se valora que el asesor use historias, ejemplos de otros alumnos o situaciones
   reales para hacer tangible el valor del programa. Un caso real bien contado
   vale más que una lista de características.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERIOS DE CALIFICACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 MALO — presentación económica o de admisión negligente o que daña la conversación:
   - Da el precio sin construir ningún valor previo (precio antes que valor)
   - Omite completamente el comité de admisión
   - Es evasivo o defensivo ante preguntas del lead sobre precio
   - Genera confusión, desconfianza o presión innecesaria
   - También: el lead pregunta directamente por el precio o el proceso y el asesor lo esquiva o lo gestiona mal
   - CRÍTICO: si el lead muestra resistencia a la fecha de inicio o a decidir ahora, y el asesor
     NO usa las ayudas económicas disponibles, NO expone las consecuencias de no formarse ahora,
     y NO argumenta las ventajas de hacerlo → es MALO. Dejar ir al lead sin activar ningún
     argumento económico de urgencia es una negligencia comercial.

🟡 MEJORABLE — funcional pero mecánico, sin impacto emocional real:
   - Menciona el comité de forma mecánica, sin darle peso ni emoción
   - Explica el precio de forma ordenada pero sin haber construido valor suficiente primero
   - La secuencia valor→precio existe pero es superficial
   - No valida ni explora la situación financiera del lead
   - No usa storytelling ni ejemplos que hagan tangible el valor del programa
   - No valida la reacción del lead tras presentar el precio ("¿Cómo lo ves?")
   - Ofrece alternativas de pago sin haber preguntado la situación financiera antes

🟢 BUENO — presentación estructurada que construye valor y genera confianza antes del precio:
   - Construye valor del programa antes de mencionar el precio
   - Presenta el comité de admisión con convicción, no como trámite
   - Introduce el precio después del valor, con contexto claro
   - Valida la reacción del lead tras presentar el precio ("¿Cómo lo ves?")
   - Si el lead muestra resistencia a la fecha, activa argumentos de urgencia económica
     (ayudas, consecuencias de no formarse ahora, ventajas de decidir hoy)
   - Usa storytelling o ejemplos reales que hagan tangible el valor del programa
   - Ante petición de descuento, presenta una propuesta concreta y cierra sobre ella
   - No es necesario que use todas las técnicas: basta con que la propuesta sea firme y el lead sienta que la inversión tiene sentido

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVIDENCIA REQUERIDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Debes identificar MÍNIMO:
- 1 ejemplo de cómo se presentó el comité de admisión (si se menciona)
- 1 ejemplo de construcción de valor antes del precio
- 1 ejemplo de mención de precio/inversión
- 1 ejemplo de financiación o descuento (si existe)
- 1 reacción del lead sobre el tema económico

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Momento clave de la propuesta económica o comité... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Presentación del comité de admisión... (COPY-PASTE LITERAL)",
    "[ASESOR]: Construcción de valor antes del precio... (COPY-PASTE LITERAL)",
    "[ASESOR]: Mención de precio/descuento... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción o pregunta sobre precio/admisión... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "Responde cada punto: ¿Hizo análisis financiero antes de hablar de precio? ¿Ofreció alternativas sin haber preguntado la situación financiera (patrón negativo)? ¿Presentó comité con emoción o fue mecánico? ¿Valor antes que precio? ¿Validó la reacción del lead tras el precio? ¿Usó storytelling o ejemplo real? ¿Ante resistencia del lead, activó argumentos de urgencia económica? ¿Fue firme con el precio o dejó todo abierto? ¿Por qué esa calificación?",
  "recomendacion_accionable": "Qué mejorar + UNA técnica concreta de los libros de ventas del CONTEXTO con 2 frases que el asesor podría haber usado en ESTA conversación. Máx 6-8 líneas. No copies texto literal.",
  "menciona_precio": true/false,
  "explica_financiacion": true/false,
  "menciona_comite": true/false,
  "comite_con_emocion": true/false,
  "valor_antes_precio": true/false,
  "usa_storytelling": true/false,
  "secuencia_correcta": true/false,
  "claridad_admision": "ALTA" | "MEDIA" | "BAJA" | "NO_MENCIONADO",
  "enfoque_valor_vs_precio": "valor" | "precio" | "equilibrado"
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
- Todas las evidencias DEBEN ser copy-paste LITERAL (COPY-PASTE exacto)
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Observabilidad puede ser BAJA si no se mencionó el tema en la llamada
- NO penalices si el tema no surgió naturalmente (puede ser llamada inicial)
- SÍ penaliza con MALO si evitó el tema cuando el lead preguntó directamente

⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta.
- BUENO cuando el asesor construye valor antes del precio, valida la reacción del lead y
  maneja la conversación económica con firmeza y criterio consultivo.
- MEJORABLE cuando hay estructura mínima pero el impacto es plano: el lead no entiende
  por qué vale lo que vale, o el asesor no valida ni gestiona bien las resistencias.
- MALO cuando el precio aparece sin contexto, el comité se omite, el asesor es evasivo
  con el precio, o deja ir al lead sin activar ningún argumento económico de urgencia.
- Si dudas entre BUENO y MEJORABLE: ¿el lead entendió que está haciendo una inversión
  con sentido y el asesor cerró sobre una propuesta concreta? Si sí → BUENO.
- Si el lead mostró resistencia a la fecha y el asesor no usó ayudas ni consecuencias → MALO.

REGLA DE ACUMULACIÓN — MALO POR SUMA DE FALLOS:
Si en tu razonamiento has detectado 3 o más de los siguientes fallos, la calificación
DEBE ser MALO, independientemente de que haya habido algún elemento positivo aislado:
  ✗ Sin análisis financiero previo al precio
  ✗ Comité de admisión mencionado de forma mecánica o sin emoción
  ✗ Valor construido insuficientemente antes del precio
  ✗ Sin validación de la reacción del lead tras el precio
  ✗ Sin argumentos de urgencia cuando el lead mostró resistencia (sin ayudas, sin
    consecuencias de no formarse ahora, sin ventajas de decidir hoy)
Un asesor que deja al lead ir sin activar NINGUNO de estos argumentos ante resistencia
ha fallado en lo esencial de esta fase. El feedback debe enumerar los fallos detectados.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza cómo manejó el proceso de admisión y la propuesta económica:

{transcripcion}

Genera la evaluación en JSON.
IMPORTANTE: Si el tema no se mencionó en la llamada, marca observabilidad como BAJA.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_admision_economica")
        return self._extract_json_safe(resp)
