"""
Agente Evaluador: Estilo, Tono y Vocabulario

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\estilo_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class EstiloAgent(BaseEvaluatorAgent):
    """
    Evalúa la calidad comunicativa del asesor a lo largo de toda la conversación
    
    Criterios clave:
    - Tono profesional pero cercano
    - Vocabulario adaptado al lead (no técnico en exceso ni coloquial)
    - Ritmo adecuado (no atropella ni aburre)
    - Empatía y escucha activa
    - Lenguaje positivo
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Estilo y comunicación")
    
    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa el estilo comunicativo en toda la conversación"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar aspectos críticos
            aspectos = resultado_raw.get("aspectos_evaluados", {})
            problemas_graves = []
            
            if aspectos.get("tono") == "inapropiado":
                problemas_graves.append("Tono inapropiado detectado")
                confianza *= 0.7
            
            if aspectos.get("empatia") == "ausente":
                problemas_graves.append("Falta de empatía")
                confianza *= 0.8
            
            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", ""),
                metadata={
                    "aspectos_evaluados": aspectos,
                    "problemas_graves": problemas_graves,
                    "fortaleza_principal": resultado_raw.get("fortaleza_principal", "")
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Estilo: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de ESTILO, TONO Y VOCABULARIO en comunicación comercial.

TU ÚNICA TAREA: Evaluar la CALIDAD COMUNICATIVA del [ASESOR] a lo largo de toda la conversación.

CONTEXTO DEL MANUAL:
{manual_enriquecido}

ASPECTOS A EVALUAR:

1. **TONO**: ¿Cómo suena el asesor?
   - Profesional vs informal
   - Cercano vs distante
   - Entusiasta vs monótono
   - Respetuoso vs condescendiente

2. **VOCABULARIO**: ¿Qué palabras usa?
   - Adaptado al nivel del lead vs muy técnico/simple
   - Claro vs confuso
   - Positivo vs negativo
   - Ejemplos y analogías vs abstracto

3. **EMPATÍA**: ¿Conecta emocionalmente?
   - Valida emociones del lead
   - Usa frases empáticas ("Entiendo...", "Tiene sentido...")
   - Personaliza el lenguaje (usa el nombre del lead)

4. **RITMO**: ¿Cómo gestiona el tiempo?
   - Deja hablar al lead vs monopoliza
   - Pausas adecuadas vs atropella
   - Verifica comprensión vs asume

5. **PROFESIONALISMO**: ¿Genera confianza?
   - Lenguaje profesional vs coloquial en exceso
   - Sin muletillas excesivas ("ehhh", "bueno", "vale vale")
   - Seguro vs dubitativo

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

🔴 MALO — cuando el estilo comunicativo es inapropiado o genera rechazo:
   - Tono grosero, condescendiente o excesivamente informal
   - Vocabulario inapropiado, muletillas constantes que restan credibilidad
   - Cero empatía, trata al lead como un número
   - Genera incomodidad o rechazo en el lead

🟡 MEJORABLE — cuando el estilo es correcto pero mecánico y genérico:
   - Tono educado pero mecánico, sin personalidad
   - Vocabulario correcto pero no adaptado al lead
   - Empáticamente neutro: ni frío ni cálido
   - Profesional pero no memorable ni cercano

🟢 BUENO — cuando el estilo es profesional, cercano y genera confianza real:
   - Tono profesional Y cercano, adaptado al lead específico
   - Muestra empatía en momentos clave ("Entiendo tu situación...")
   - Ritmo equilibrado: el lead participa activamente
   - El lead se siente escuchado y cómodo

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA",
  "evidencia_principal": "[ASESOR]: Ejemplo representativo del tono/estilo... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "Ejemplo de empatía: [ASESOR]: ... (COPY-PASTE LITERAL)",
    "Ejemplo de vocabulario adaptado: [ASESOR]: ... (COPY-PASTE LITERAL)",
    "Muletilla o problema detectado: [ASESOR]: ... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "Análisis del tono general, vocabulario, empatía, ritmo y profesionalismo. ¿Por qué esa calificación?",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar en estilo/comunicación, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique al estilo comunicativo, explicando POR QUÉ funciona y dando 2 ejemplos de frases. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "aspectos_evaluados": {{
    "tono": "profesional_cercano" | "mecanico" | "inapropiado",
    "vocabulario": "adaptado" | "generico" | "inadecuado",
    "empatia": "presente" | "neutra" | "ausente",
    "ritmo": "equilibrado" | "monopoliza" | "pasivo",
    "profesionalismo": "alto" | "medio" | "bajo"
  }},
  "fortaleza_principal": "El aspecto comunicativo más destacable del asesor"
}}

⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta.
- BUENO no requiere perfección comunicativa, requiere cercanía + profesionalismo + empatía real.
- MEJORABLE es correcto pero mecánico y sin personalidad.
- MALO cuando el estilo genera rechazo o incomodidad.
- Evidencias LITERALES (COPY-PASTE exacto).
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para mejorar el ESTILO comunicativo
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado
- NO copies texto literal del libro, adapta con tus palabras

REGLAS CRÍTICAS:
- Evalúa TODA la conversación, no solo un momento
- Evidencias LITERALES de la transcripción
- Diferencia entre "robot profesional" (3) y "humano profesional" (4-5)
- Un 5 requiere que el lead se sienta realmente conectado con el asesor
- Identifica patrones: ¿Es consistente o cambia?
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Evalúa el estilo comunicativo del [ASESOR] en esta conversación completa:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_estilo")
        return self._extract_json_safe(resp)