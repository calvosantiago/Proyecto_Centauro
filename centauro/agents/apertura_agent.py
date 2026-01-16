"""
Agente Evaluador de Apertura

Especializado en evaluar cómo inicia el asesor la conversación
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class AperturaAgent(BaseEvaluatorAgent):
    """
    Evalúa exclusivamente la apertura de la llamada
    
    Criterios:
    - Saludo profesional
    - Presentación clara
    - Generación de rapport inicial
    - Establecimiento del marco de la conversación
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Apertura")
        self.longitud_analisis = 800  # Caracteres del inicio a analizar
    
    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """
        Evalúa la apertura usando solo los primeros ~800 caracteres
        """
        # Extraer solo el inicio de la conversación
        inicio_conversacion = transcripcion[:self.longitud_analisis]
        
        # Detectar si el audio empieza tarde (off-record)
        if self._detectar_inicio_tardio(inicio_conversacion):
            return self._crear_resultado_off_record()
        
        # Evaluar con LLM
        try:
            resultado_raw = self._evaluar_con_llm(inicio_conversacion, contexto_manual)
            
            # Calcular confianza
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar evidencia
            evidencia_valida = self._validar_evidencia_literal(
                resultado_raw.get("evidencia_principal", ""),
                inicio_conversacion
            )
            
            if not evidencia_valida:
                print(f"   ⚠️ Evidencia NO verificada en transcripción")
                # Ajustar confianza pero no forzar error
                confianza *= 0.7
            
            # Crear resultado
            return EvaluationResult(
                bloque=self.nombre_bloque,
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", "")
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Apertura: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, inicio: str, manual: str) -> dict:
        """
        Llama al LLM con prompt especializado en apertura
        """
        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de APERTURAS de llamadas comerciales.

TU ÚNICA TAREA: Evaluar cómo inició la conversación el [ASESOR].

CONTEXTO DEL MANUAL:
{manual}

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = DEFICIENTE / NEGLIGENTE
   - Sin saludo o saludo grosero
   - Inicio brusco o confuso
   - No se identifica

2 = INSUFICIENTE
   - Saludo mínimo sin presentación ("Hola, dime")
   - Frío o desinteresado
   - No establece propósito

3 = CORRECTO / ESTÁNDAR (Robot)
   - Saludo educado estándar ("Buenos días, soy X de OBS")
   - Presentación correcta pero mecánica
   - Funcional pero sin calidez

4 = BUENO / PROFESIONAL
   - Saludo cálido y profesional
   - Presentación completa (nombre + empresa + propósito)
   - Tono amable que invita al diálogo
   - Verifica que es buen momento

5 = EXCELENTE / MAESTRÍA
   - Todo lo anterior PLUS:
   - Genera conexión inmediata (menciona algo del lead, personaliza)
   - Establece marco de confianza ("Esta llamada es para X, te parece bien?")
   - Tono cercano pero profesional
   - Transición natural a exploración de necesidades

REGLA OFF-RECORD CRÍTICA:
Si la transcripción empieza claramente a mitad de conversación:
- Ejemplo: "...como te decía antes..."
- Ejemplo: "[ASESOR]: Entonces, cuéntame más sobre tu experiencia"
→ Marca observabilidad: "NO_OBSERVABLE_OFF_RECORD" y NO asignes nota (null)

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "NO_OBSERVABLE_OFF_RECORD",
  "evidencia_principal": "[ASESOR]: Cita textual exacta del saludo...",
  "evidencias_extra": ["[ASESOR]: Presentación...", "[ASESOR]: Propósito..."],
  "razonamiento": "Análisis técnico de POR QUÉ esta nota (100-200 palabras)",
  "recomendacion_accionable": "Acción específica para mejorar (si nota < 5)"
}}

REGLAS CRÍTICAS:
- La evidencia_principal DEBE ser copy-paste LITERAL de la transcripción
- Incluye SIEMPRE la etiqueta [ASESOR] o [LEAD] en la cita
- El razonamiento debe explicar qué faltó para el siguiente nivel
- NO uses lenguaje motivacional ("lo hizo bien", "buen trabajo"). Sé técnico.
"""
        
        prompt_usuario = f"""
Analiza SOLO la apertura de esta conversación:

{inicio}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_apertura")
        return self._extract_json_safe(resp)
    
    def _detectar_inicio_tardio(self, inicio: str) -> bool:
        """
        Detecta si la grabación empezó después del saludo
        
        Indicadores:
        - "...como te decía"
        - "entonces"
        - Empieza con pregunta profunda sin presentación previa
        """
        inicio_lower = inicio.lower()
        
        indicadores = [
            "como te decía",
            "como te comentaba",
            "entonces, cuéntame",
            "...perfectamente",
            "como te mencioné",
            # Patrón: empieza directo en exploración profunda
            r"^\[asesor\]:\s*(cuéntame|explícame|háblame)",
        ]
        
        import re
        for indicador in indicadores:
            if isinstance(indicador, str):
                if indicador in inicio_lower:
                    return True
            else:
                if re.search(indicador, inicio_lower, re.IGNORECASE):
                    return True
        
        return False
    
    def _crear_resultado_off_record(self) -> EvaluationResult:
        """
        Resultado para casos donde el saludo ocurrió antes de la grabación
        """
        return EvaluationResult(
            bloque=self.nombre_bloque,
            puntuacion_1_5=None,  # No evaluable
            observabilidad="NO_OBSERVABLE_OFF_RECORD",
            confianza=1.0,  # Estamos seguros de que no es observable
            evidencia_principal="Grabación inició después del saludo (inicio tardío detectado)",
            evidencias_extra=[],
            razonamiento=(
                "La transcripción comienza a mitad de conversación, indicando que el saludo "
                "ocurrió antes de iniciar la grabación. No se puede evaluar este bloque. "
                "Esto es común y NO es un error del asesor."
            ),
            recomendacion_accionable="Verificar que la grabación inicie desde el primer saludo"
        )