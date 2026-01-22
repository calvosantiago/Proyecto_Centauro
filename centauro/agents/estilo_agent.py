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
    
    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """Evalúa el estilo comunicativo en toda la conversación"""
        
        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual)
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
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
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
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado"""
        
        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de ESTILO, TONO Y VOCABULARIO en comunicación comercial.

TU ÚNICA TAREA: Evaluar la CALIDAD COMUNICATIVA del [ASESOR] a lo largo de toda la conversación.

CONTEXTO DEL MANUAL:
{manual}

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

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = INAPROPIADO / CONTRAPRODUCENTE
   - Tono grosero, condescendiente o excesivamente informal
   - Vocabulario inapropiado (coloquialismos, errores graves)
   - Cero empatía, trata al lead como número
   - Genera rechazo o incomodidad

2 = DEFICIENTE / POCO PROFESIONAL
   - Tono inconsistente (a veces formal, a veces demasiado casual)
   - Muletillas constantes que restan profesionalismo
   - Poca adaptación al lead
   - No genera confianza

3 = CORRECTO / ESTÁNDAR (Robot)
   - Tono educado pero mecánico
   - Vocabulario correcto pero genérico
   - Empáticamente neutro (no frío, pero tampoco cálido)
   - Profesional pero sin personalidad
   - Funcional pero no memorable

4 = BUENO / COMUNICACIÓN EFECTIVA
   - Tono profesional Y cercano
   - Adapta vocabulario al lead
   - Muestra empatía en momentos clave
   - Ritmo equilibrado (lead participa activamente)
   - Genera confianza

5 = MAESTRÍA / COMUNICACIÓN EXCEPCIONAL
   - Tono perfecto para el contexto y el lead
   - Vocabulario que conecta (usa metáforas, ejemplos del mundo del lead)
   - Empatía genuina que genera conexión real
   - Ritmo magistral (sabe cuándo hablar y cuándo callar)
   - El lead se siente escuchado, comprendido y valorado

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA",
  "evidencia_principal": "[ASESOR]: Ejemplo representativo del tono/estilo... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "Ejemplo de empatía: [ASESOR]: ... (COPY-PASTE LITERAL)",
    "Ejemplo de vocabulario adaptado: [ASESOR]: ... (COPY-PASTE LITERAL)",
    "Muletilla o problema detectado: [ASESOR]: ... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "Análisis del tono general, vocabulario, empatía, ritmo y profesionalismo. ¿Qué faltó para la nota siguiente?",
  "recomendacion_accionable": "Acción específica para mejorar el estilo (sin repetir lo ya logrado)",
  "gap_para_5": "Si nota es 3 o 4, explica ESPECÍFICAMENTE qué faltó para alcanzar el 5. Si nota es 5, pon 'N/A - Ya alcanzado'",
  "aspectos_evaluados": {{
    "tono": "profesional_cercano" | "mecanico" | "inapropiado",
    "vocabulario": "adaptado" | "generico" | "inadecuado",
    "empatia": "presente" | "neutra" | "ausente",
    "ritmo": "equilibrado" | "monopoliza" | "pasivo",
    "profesionalismo": "alto" | "medio" | "bajo"
  }},
  "fortaleza_principal": "El aspecto comunicativo más destacable del asesor"
}}

⚠️ REGLAS CRÍTICAS:
- El 5/5 ES ALCANZABLE si la comunicación es excepcional
- Si la ejecución es excelente, NO te limites a dar 4
- Evidencias LITERALES (COPY-PASTE exacto)
- En "gap_para_5" sé específico (ej: "Faltó usar metáforas del mundo del lead")
- En "recomendacion_accionable" NO repitas lo que ya hizo bien

REGLAS CRÍTICAS:
- Evalúa TODA la conversación, no solo un momento
- Evidencias LITERALES de la transcripción
- Diferencia entre "robot profesional" (3) y "humano profesional" (4-5)
- Un 5 requiere que el lead se sienta realmente conectado con el asesor
- Identifica patrones: ¿Es consistente o cambia?
"""
        
        prompt_usuario = f"""
Evalúa el estilo comunicativo del [ASESOR] en esta conversación completa:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_estilo")
        return self._extract_json_safe(resp)