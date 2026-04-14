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

            # Tope universal: 3+ fallos críticos = MALO
            contador_fallos = resultado_raw.get("contador_fallos_criticos", 0)
            cal_tmp, raz_tmp = self._aplicar_tope_fallos_criticos(
                resultado_raw.get("calificacion"), contador_fallos, resultado_raw.get("razonamiento", "")
            )
            if cal_tmp != resultado_raw.get("calificacion"):
                resultado_raw["calificacion"] = cal_tmp
                resultado_raw["razonamiento"] = raz_tmp

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

TONO DE REDACCIÓN: Escribe SIEMPRE en TERCERA PERSONA al referirte al asesor ("el asesor hizo...", "el asesor podría..."). NUNCA uses segunda persona ("hiciste...", "podrías...", "tu objetivo...").

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
  ✓ SEÑAL CRÍTICA — Declaraciones de no-intención de compra en la convocatoria actual:
    Frases como "mi plan no era ingresar en ningún programa académico", "no lo tenía
    pensado para esta convocatoria", "no tengo intención de matricularme ahora" son
    la señal más importante que debes detectar en toda la transcripción. Cuando la
    encuentres, busca activamente si el asesor activó en algún momento posterior
    argumentos de urgencia: ayudas económicas disponibles, consecuencias de no
    formarse ahora, ventajas de decidir en esta convocatoria. Si no los activó → MALO,
    independientemente de si el lead "parecía poco interesado". Que el lead no tenga
    intención de comprar ahora es exactamente el momento en que el asesor debe usar
    estas herramientas, no una excusa para omitirlas.

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
   - CRÍTICO — LEAD SIN INTENCIÓN DE COMPRA EN LA CONVOCATORIA ACTUAL:
     Si el lead declara explícitamente que no tenía intención de inscribirse ahora
     ("mi plan no era ingresar en ningún programa académico", "no lo tenía pensado para
     esta convocatoria", "no es algo que me plantee para ahora") Y el asesor NO usa las
     ayudas económicas disponibles, NO expone las consecuencias de no formarse ahora, y
     NO argumenta las ventajas de decidir en esta convocatoria → es MALO sin excepción.
     Esta declaración del lead es la señal más importante para activar urgencia. No usarla
     es la negligencia comercial más grave. El hecho de que el lead "no tuviera intención"
     NO es una excusa para que el asesor omita los argumentos de urgencia: es exactamente
     la situación para la que existen esas herramientas.
   - CRÍTICO — RESISTENCIA A LA FECHA O A DECIDIR AHORA: si el lead muestra resistencia
     a la fecha de inicio o a comprometerse en esta llamada, y el asesor NO usa las ayudas
     económicas disponibles, NO expone las consecuencias de no formarse ahora, y NO argumenta
     las ventajas de hacerlo → es MALO. Dejar ir al lead sin activar ningún argumento
     económico de urgencia es una negligencia comercial.

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
  "contador_fallos_criticos": 0,
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Momento clave de la propuesta económica o comité... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Presentación del comité de admisión... (COPY-PASTE LITERAL)",
    "[ASESOR]: Construcción de valor antes del precio... (COPY-PASTE LITERAL)",
    "[ASESOR]: Mención de precio/descuento... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción o pregunta sobre precio/admisión... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica qué hizo bien el asesor y en qué aspectos falló en la admisión y propuesta económica. Por qué merece esa calificación. Conecta con lo que ocurrió realmente en la conversación. OBLIGATORIO si la calificación es MALO o MEJORABLE: incluye en el texto al menos una cita literal entre comillas de la conversación que muestre el fallo principal.",
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
⚠️ VERIFICA ANTES DE RECOMENDAR: Comprueba si el asesor ya demostró en la conversación
el comportamiento que vas a recomendar. Si ya lo hizo, NO lo recomiendes — elige otro
aspecto donde haya margen real de mejora. Recomendar algo que el asesor ya hizo invalida
el coaching.

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL (COPY-PASTE exacto)
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Observabilidad puede ser BAJA si no se mencionó el tema en la llamada
- NO penalices si el tema no surgió naturalmente (puede ser llamada inicial)
- SÍ penaliza con MALO si evitó el tema cuando el lead preguntó directamente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ANTES DE CALIFICAR — VERIFICACIÓN OBLIGATORIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CALIBRA con los ejemplos del CONTEXTO:
Los ejemplos de buenas prácticas que aparecen arriba son el estándar de referencia
del programa — no son inspiración para el coaching, son la definición concreta de BUENO.
Si lo que hizo este asesor se parece en espíritu a esos ejemplos (aunque use otras
palabras o no cubra cada punto al pie de la letra), está en zona BUENO.
⚠️ Matiz: un momento aislado que se parece a un ejemplo NO hace BUENO el bloque
completo. Evalúa el CONJUNTO de la fase, no el mejor instante. Los ejemplos marcan
el estándar para el nivel general, no para un fragmento aislado.
Tenlo presente al interpretar los fallos del checklist.

DETENTE. Antes de elegir la calificación, DEBES responder SÍ o NO a cada uno
de estos 5 puntos. Cuenta cuántos tienen respuesta NEGATIVA (= fallo):

  1. ¿Hizo análisis financiero ANTES de hablar de precio?              → SÍ / NO
  2. ¿Presentó el comité de admisión con emoción y convicción (no mecánico)? → SÍ / NO
  3. ¿Construyó valor SUFICIENTE antes de presentar el precio?          → SÍ / NO
  4. ¿Validó la reacción del lead DESPUÉS de presentar el precio?       → SÍ / NO
  5. ¿Activó argumentos de urgencia cuando el lead mostró resistencia O declaró no-intención
     de inscribirse en la convocatoria actual?                            → SÍ / NO
     (Si el lead no mostró resistencia ni declaró no-intención → marca SÍ por defecto)

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: Si hay 3 o más NOs → la calificación es MALO. Sin excepciones.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 5 criterios son todos relevantes para el
   resultado de esta dimensión. Fallos en análisis financiero, comité sin emoción,
   precio sin valor previo, no validar la reacción del lead y no activar urgencia son
   aspectos críticos que comprometen directamente el avance. Si la mayoría fallaron,
   la calificación debe reflejar esa realidad: MALO. No porque exista un umbral mecánico,
   sino porque es lo que corresponde al impacto real en la conversación. No puedes detectar
   múltiples fallos graves y concluir MEJORABLE: sería incoherente con tu propio análisis.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: múltiples fallos críticos acumulados que comprometieron el avance del lead, O precio
  sin contexto, O comité omitido, O evasivo con precio, O deja ir al lead sin activar ningún
  argumento ante resistencia.
- MEJORABLE: hay estructura mínima pero el impacto es plano: el asesor cumple los pasos pero sin construir valor real ni generar reacción en el lead. Correcta pero no persuasiva.
- BUENO: construye valor real, valida la reacción del lead y maneja la parte económica con firmeza consultiva. No es necesario cubrir todos los puntos: si el lead avanzó con claridad económica y sin resistencia no resuelta → es BUENO.
- Si dudas entre BUENO y MEJORABLE: ¿el lead entendió que está haciendo una inversión
  con sentido y el asesor cerró sobre una propuesta concreta? Si sí → BUENO.
- Si el lead mostró resistencia a la fecha y el asesor no usó ayudas ni consecuencias → MALO.
- Si el lead declaró explícitamente no-intención de compra en esta convocatoria ("mi plan
  no era ingresar en ningún programa académico" o equivalente) Y el asesor no activó ningún
  argumento de urgencia en ningún momento posterior de la conversación → MALO sin excepción,
  independientemente de cuántas cosas hiciera bien en otros aspectos.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
ANTES DE EVALUAR: Lee la transcripción completa de principio a fin. El análisis financiero,
la presentación del comité, el precio y los argumentos de urgencia pueden aparecer en
cualquier momento de la llamada. Identifica TODOS los momentos relevantes — incluyendo
ayudas económicas mencionadas, reacciones del lead al precio, y cualquier momento donde
el asesor usó urgencia — antes de decidir la calificación.

Analiza cómo manejó el proceso de admisión y la propuesta económica:

{transcripcion}

Genera la evaluación en JSON.
IMPORTANTE: Si el tema no se mencionó en la llamada, marca observabilidad como BAJA.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_admision_economica")
        return self._extract_json_safe(resp)
