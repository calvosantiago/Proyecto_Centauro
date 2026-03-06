"""
Base Agent v4.0: Template para todos los agentes evaluadores
Define la interfaz común y utilidades compartidas

ACTUALIZADO v4.0: Usa configuración centralizada
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from dataclasses import dataclass, field
import json
from pathlib import Path
from centauro.config import centauro_config

@dataclass
class EvaluationResult:
    """Resultado estandarizado de evaluación

    v5.0: Calificación ordinal MALO | MEJORABLE | BUENO (reemplaza escala 1-5)
    """
    bloque: str
    calificacion: Optional[str]  # MALO | MEJORABLE | BUENO | None (no observable)
    observabilidad: str  # ALTA | MEDIA | BAJA | NO_OBSERVABLE_OFF_RECORD
    confianza: float  # 0.0 - 1.0
    evidencia_principal: str
    evidencias_extra: List[str] = field(default_factory=list)
    razonamiento: str = ""
    recomendacion_accionable: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convierte a diccionario para compatibilidad con schema.py"""
        return {
            "bloque": self.bloque,
            "calificacion": self.calificacion,
            "observabilidad": self.observabilidad,
            "confianza": self.confianza,
            "evidencia_principal": self.evidencia_principal,
            "evidencias_extra": self.evidencias_extra,
            "razonamiento": self.razonamiento,
            "recomendacion_accionable": self.recomendacion_accionable,
            **self.metadata
        }

class BaseEvaluatorAgent(ABC):
    """
    Clase base abstracta para todos los agentes evaluadores.

    Incluye soporte para consultar ejemplos de buenas prácticas.
    """

    def __init__(self, nombre_bloque: str):
        self.nombre_bloque = nombre_bloque
        self.version = "4.0"
        self.temperatura = centauro_config.LLM_TEMPERATURE_EVALUACION
        self._ejemplos_cache = None  # Cache para ejemplos de buenas prácticas
    
    @abstractmethod
    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """
        Método principal de evaluación que cada agente debe implementar

        Args:
            transcripcion: Transcripción diarizada de la llamada
            contexto_manual: Contexto del manual de ventas (RAG)
            contexto_usuario: (Opcional) Contexto adicional del usuario (info del lead, instrucciones, etc.)
        """
        pass

    def _construir_bloque_contexto_usuario(self, contexto_usuario: str = None) -> str:
        """
        Construye el bloque de texto para incluir contexto del usuario en los prompts.

        Args:
            contexto_usuario: Texto libre del usuario con contexto adicional

        Returns:
            Bloque de texto formateado para incluir en el prompt, o cadena vacía si no hay contexto
        """
        if not contexto_usuario or not contexto_usuario.strip():
            return ""

        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO ESPECÍFICO DE ESTA EVALUACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{contexto_usuario.strip()}

⚠️ INSTRUCCIÓN OBLIGATORIA: Este contexto tiene PRIORIDAD sobre las asunciones
generales del prompt. Úsalo para calibrar tu evaluación de forma específica.
Ejemplos de cómo aplicarlo:
- Edad del lead (ej: "22 años", "recién graduado") → ajusta la exigencia de estilo,
  los argumentos esperados y el lenguaje apropiado. Un lead joven necesita un pitch
  diferente (aspiracional, empleabilidad) que uno de 45+ años (ROI, ascenso directivo).
- Quién financia (ej: "los padres pagan", "empresa lo cubre") → no penalices por
  referencias a financiación familiar ni por ausencia de análisis financiero propio.
- Perfil profesional (ej: "directivo con 20 años de experiencia", "estudiante sin experiencia")
  → ajusta qué estilo comunicativo, argumentos y técnicas son apropiados para ese perfil.
- Circunstancias especiales (ej: "llamada corta", "lead ya comparó opciones") → úsalas
  como atenuantes o contexto relevante en la evaluación.
Refleja explícitamente el uso de este contexto en el campo "razonamiento".
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    def _extract_json_safe(self, raw_response: str) -> Dict:
        """Extrae JSON de forma robusta"""
        if not raw_response:
            raise ValueError("Respuesta vacía del LLM")
        
        clean = raw_response.replace("```json", "").replace("```", "").strip()
        
        import re
        match = re.search(r'\{.*\}', clean, flags=re.DOTALL)
        
        if not match:
            raise ValueError("No se encontró JSON en la respuesta")
        
        json_str = match.group(0)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON malformado en {self.nombre_bloque}: {e}")
            print(f"   Fragmento: {json_str[:200]}...")
            raise
    
    def _calcular_confianza(self, resultado_raw: Dict) -> float:
        """Calcula nivel de confianza basado en la calidad de la respuesta"""
        score = 1.0

        evidencia = resultado_raw.get("evidencia_principal", "")
        if not evidencia or len(evidencia) < centauro_config.MIN_EVIDENCE_LENGTH:
            score -= centauro_config.CONFIDENCE_PENALTY_SHORT_EVIDENCE
        if "no se pudo evaluar" in evidencia.lower():
            score -= centauro_config.CONFIDENCE_PENALTY_VAGUE_EVIDENCE

        razonamiento = resultado_raw.get("razonamiento", "")
        if len(razonamiento) < centauro_config.MIN_REASONING_LENGTH:
            score -= centauro_config.CONFIDENCE_PENALTY_SHORT_REASONING

        obs = resultado_raw.get("observabilidad", "MEDIA")
        if obs in ["BAJA", "NO_OBSERVABLE_OFF_RECORD"]:
            score -= centauro_config.CONFIDENCE_PENALTY_LOW_OBSERVABILITY

        return max(0.0, min(1.0, score))
    
    def _create_fallback_result(self, error_msg: str) -> EvaluationResult:
        """Genera resultado de fallback cuando la evaluación falla"""
        return EvaluationResult(
            bloque=self.nombre_bloque,
            calificacion=None,
            observabilidad="ERROR_EVALUACION",
            confianza=0.0,
            evidencia_principal=f"Error: {error_msg}",
            evidencias_extra=[],
            razonamiento="La evaluación automática falló. Requiere revisión manual.",
            recomendacion_accionable="Revisar transcripción manualmente",
            metadata={"error": error_msg}
        )
    
    def _validar_evidencia_literal(self, evidencia: str, transcripcion: str) -> bool:
        """Valida que la evidencia citada exista realmente en la transcripción"""
        try:
            from rapidfuzz import fuzz
            evidencia_clean = evidencia.lower().strip()
            transcripcion_clean = transcripcion.lower()
            ratio = fuzz.partial_ratio(evidencia_clean, transcripcion_clean)
            return ratio >= centauro_config.SHERIFF_FUZZY_THRESHOLD
        except ImportError:
            return evidencia.lower() in transcripcion.lower()

    def _buscar_ejemplos_relevantes(self, transcripcion: str, max_ejemplos: int = None) -> List[str]:
        """
        Busca ejemplos de buenas prácticas relevantes para esta evaluación.

        ACTUALIZADO v4.3: Filtra por sección con fallback sin filtro.

        Usa RAG para encontrar fragmentos similares de conversaciones exitosas.
        Los ejemplos se usan como INSPIRACIÓN, no como reglas rígidas.

        Args:
            transcripcion: Conversación a evaluar
            max_ejemplos: Máximo número de ejemplos a devolver

        Returns:
            Lista de textos de ejemplos relevantes
        """
        if max_ejemplos is None:
            max_ejemplos = centauro_config.RAG_TOP_K_BUENAS_PRACTICAS

        try:
            # Importar RAG dinámico
            from centauro.core.rag_dynamic import buscar_contexto_dinamico

            # Construir query específica para este bloque
            query = f"Ejemplo de buena práctica: {transcripcion[:500]}"

            # Buscar en la colección de buenas prácticas FILTRADO por sección
            resultados = buscar_contexto_dinamico(
                query=query,
                collection_name="buenas_practicas",
                k=max_ejemplos,
                filtro_seccion=self.nombre_bloque  # Filtra por la sección del agente
            )

            # FALLBACK: Si no encuentra con filtro, buscar sin filtro de sección
            if not resultados:
                print(f"   Info: No hay ejemplos para seccion '{self.nombre_bloque}', buscando sin filtro...")
                resultados = buscar_contexto_dinamico(
                    query=query,
                    collection_name="buenas_practicas",
                    k=max_ejemplos,
                    filtro_seccion=None
                )

            if not resultados:
                return []

            # Extraer textos de ejemplos
            ejemplos = []
            fuentes_vistas = set()
            for resultado in resultados[:max_ejemplos]:
                # Formato esperado del RAG: dict con 'text' y 'metadata'
                if isinstance(resultado, dict):
                    texto = resultado.get('text', '')
                    fuente = resultado.get('metadata', {}).get('fuente', '')
                    seccion = resultado.get('metadata', {}).get('seccion', '')
                    if texto:
                        ejemplos.append(texto)
                        if fuente and fuente not in fuentes_vistas:
                            fuentes_vistas.add(fuente)
                            print(f"      Ejemplo encontrado: {fuente} (seccion: {seccion})")
                else:
                    ejemplos.append(str(resultado))

            return [e for e in ejemplos if e]  # Filtrar vacíos

        except Exception as e:
            # Si falla (ej: no hay ejemplos indexados), continuar sin ejemplos
            print(f"   Info: No se pudieron cargar ejemplos de buenas practicas: {e}")
            return []

    def _enriquecer_contexto_con_ejemplos(self, contexto_base: str, transcripcion: str) -> str:
        """
        Añade ejemplos de buenas prácticas como ANCLAS DE CALIBRACIÓN.

        v4.3: Reestructurado para que los ejemplos sean referencia de puntuación,
        no solo inspiración ignorable.

        Args:
            contexto_base: Contexto original del manual
            transcripcion: Conversación a evaluar

        Returns:
            Contexto enriquecido con ejemplos de calibración
        """
        ejemplos = self._buscar_ejemplos_relevantes(transcripcion)

        if not ejemplos:
            return contexto_base

        # Posicionar ejemplos ANTES del contexto del manual para mayor visibilidad
        contexto_enriquecido = ""
        contexto_enriquecido += "="*80 + "\n"
        contexto_enriquecido += "ANCLAS DE CALIBRACION - EJEMPLOS REALES PUNTUADOS\n"
        contexto_enriquecido += "="*80 + "\n\n"

        contexto_enriquecido += "Los siguientes son extractos de entrevistas REALES que fueron\n"
        contexto_enriquecido += "evaluadas manualmente. USALOS PARA CALIBRAR tu evaluacion:\n\n"

        contexto_enriquecido += "INSTRUCCIONES DE CALIBRACION:\n"
        contexto_enriquecido += "1. Lee los ejemplos para entender el NIVEL DE CALIDAD que corresponde a cada calificacion\n"
        contexto_enriquecido += "2. Los ejemplos muestran UNA forma exitosa, NO la unica. Hay muchas formas\n"
        contexto_enriquecido += "   de ser BUENO sin parecerse al ejemplo\n"
        contexto_enriquecido += "3. Evalua la conversacion por SUS PROPIOS MERITOS primero:\n"
        contexto_enriquecido += "   - Si logra el objetivo del bloque con calidad → BUENO\n"
        contexto_enriquecido += "   - Si usa tecnicas diferentes pero efectivas → BUENO\n"
        contexto_enriquecido += "   - NO exijas que se parezca al ejemplo para calificar como BUENO\n"
        contexto_enriquecido += "4. Si la conversacion es la MISMA entrevista que un ejemplo,\n"
        contexto_enriquecido += "   la calificacion debe ser COHERENTE con la del ejemplo\n"
        contexto_enriquecido += "5. Usa los ejemplos para ENRIQUECER tus recomendaciones de mejora,\n"
        contexto_enriquecido += "   sugiriendo tecnicas concretas que podrian complementar lo que ya hace bien\n\n"

        for i, ejemplo in enumerate(ejemplos, 1):
            max_len = centauro_config.MAX_EJEMPLO_LENGTH_IN_PROMPT
            ejemplo_truncado = ejemplo[:max_len] + "..." if len(ejemplo) > max_len else ejemplo
            contexto_enriquecido += f"--- EJEMPLO DE REFERENCIA {i} ---\n"
            contexto_enriquecido += ejemplo_truncado + "\n\n"

        contexto_enriquecido += "="*80 + "\n\n"

        # Luego el contexto del manual
        contexto_enriquecido += contexto_base

        return contexto_enriquecido

    def __repr__(self):
        return f"<{self.__class__.__name__} bloque='{self.nombre_bloque}' v{self.version}>"