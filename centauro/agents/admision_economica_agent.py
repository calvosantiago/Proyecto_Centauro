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
CLAVES DE ESTA FASE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ANÁLISIS FINANCIERO DEL LEAD:
   El asesor debe explorar la situación económica del lead ANTES de hablar de precio.
   No se trata de interrogar, sino de entender su capacidad y expectativas para adaptar
   la presentación. ¿Preguntó si tiene financiación en mente? ¿Validó el rango que maneja?

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

5. VALIDACIÓN, NO SUPUESTOS:
   El asesor debe verificar que el lead entiende y procesa cada elemento antes de avanzar.
   No da por supuesto que el lead entendió el valor, el proceso o la financiación.
   Usa preguntas de comprobación: "¿Esto tiene sentido para ti?" / "¿Cómo lo ves?"

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

🟡 MEJORABLE — funcional pero mecánico, sin impacto emocional real:
   - Menciona el comité de forma mecánica, sin darle peso ni emoción
   - Explica el precio de forma ordenada pero sin haber construido valor suficiente primero
   - La secuencia valor→precio existe pero es superficial
   - No valida ni explora la situación financiera del lead
   - No usa storytelling ni ejemplos que hagan tangible el valor del programa

🟢 BUENO — presentación estructurada que construye valor y genera confianza antes del precio:
   - Construye valor del programa antes de mencionar el precio
   - Presenta el comité de admisión con convicción, no como trámite
   - Introduce el precio después del valor, con contexto claro
   - Valida la comprensión del lead en al menos un punto clave
   - No es necesario que use todas las técnicas: basta con que el lead sienta que la inversión tiene sentido

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
  "razonamiento": "¿Hizo análisis financiero? ¿Presentó comité con emoción? ¿Valor antes que precio? ¿Secuencia correcta? ¿Storytelling? ¿Por qué esa calificación?",
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
- BUENO cuando el asesor construye valor antes del precio y el lead procesa la inversión con calma, aunque no use todas las técnicas.
- MEJORABLE cuando hay estructura mínima pero el impacto es plano: el lead no entiende por qué vale lo que vale.
- MALO cuando el precio aparece sin contexto, el comité se omite, o el asesor genera confusión o desconfianza.
- Si dudas entre BUENO y MEJORABLE: ¿el lead entendió que está haciendo una inversión con sentido? Si sí → BUENO.
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
