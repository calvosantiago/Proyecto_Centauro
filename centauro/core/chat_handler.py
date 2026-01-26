"""
Chat Handler v4.0 - Interfaz de consulta interactiva al RAG

Permite a los usuarios hacer preguntas sobre:
- Manuales de venta (cómo hacer algo correctamente)
- Ejemplos de buenas prácticas (mostrarme ejemplos)
- Evaluaciones históricas (cómo lo han hecho otros asesores)
- Perfiles de asesores (mi rendimiento, estadísticas)
"""
from typing import List, Dict, Optional
from ..config import centauro_config
from ..rag import buscar_en_coleccion
from ..llm_client import consultar_gpt
from .memoria import memory_manager


class ChatHandler:
    """
    Maneja consultas de texto libre del usuario al sistema de conocimiento.

    Identifica la intención y busca en la colección apropiada.
    """

    def __init__(self):
        self.historial_conversacion: List[Dict] = []

    def procesar_consulta(self, pregunta_usuario: str, nombre_asesor: Optional[str] = None) -> str:
        """
        Procesa una pregunta del usuario y devuelve respuesta contextualizada.

        Args:
            pregunta_usuario: Pregunta en lenguaje natural
            nombre_asesor: Nombre del asesor (si se quiere consultar su perfil)

        Returns:
            Respuesta generada por el LLM con contexto del RAG
        """
        # Identificar intención
        intencion = self._clasificar_intencion(pregunta_usuario)

        # Buscar contexto relevante
        contexto = self._buscar_contexto_relevante(pregunta_usuario, intencion, nombre_asesor)

        # Generar respuesta
        respuesta = self._generar_respuesta(pregunta_usuario, contexto, intencion)

        # Guardar en historial
        self.historial_conversacion.append({
            "pregunta": pregunta_usuario,
            "respuesta": respuesta,
            "intencion": intencion
        })

        return respuesta

    def _clasificar_intencion(self, pregunta: str) -> str:
        """
        Clasifica la intención de la pregunta del usuario.

        Returns:
            "manual" | "ejemplo" | "perfil" | "estadisticas" | "general"
        """
        pregunta_lower = pregunta.lower()

        # Patrón: Perfil personal
        if any(kw in pregunta_lower for kw in ["mi rendimiento", "mi perfil", "mis evaluaciones", "cómo he mejorado", "mi progreso"]):
            return "perfil"

        # Patrón: Ejemplos
        if any(kw in pregunta_lower for kw in ["ejemplo", "muestra", "cómo hacer", "cómo debería", "demostración", "referencia"]):
            return "ejemplo"

        # Patrón: Estadísticas globales
        if any(kw in pregunta_lower for kw in ["estadísticas", "cuántos asesores", "promedio general", "tendencias"]):
            return "estadisticas"

        # Patrón: Manual (cómo hacer algo)
        if any(kw in pregunta_lower for kw in ["cómo", "cuál es el proceso", "qué debo", "procedimiento", "protocolo", "reglas"]):
            return "manual"

        # Default: General
        return "general"

    def _buscar_contexto_relevante(self, pregunta: str, intencion: str, nombre_asesor: Optional[str]) -> str:
        """Busca contexto en las colecciones apropiadas según la intención"""

        if intencion == "perfil" and nombre_asesor:
            # Buscar perfil del asesor
            return self._obtener_perfil_asesor(nombre_asesor)

        elif intencion == "estadisticas":
            # Obtener estadísticas globales
            return self._obtener_estadisticas_globales()

        elif intencion == "ejemplo":
            # Buscar en buenas prácticas
            resultados = buscar_en_coleccion(
                query=pregunta,
                collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
                k=centauro_config.CHAT_RAG_TOP_K
            )
            if resultados:
                fragmentos = [r['text'] for r in resultados]
                return "\n\n---\n\n".join(fragmentos)
            return "No se encontraron ejemplos relevantes."

        elif intencion == "manual":
            # Buscar en manuales generales
            resultados = buscar_en_coleccion(
                query=pregunta,
                collection_name=centauro_config.COLLECTION_MANUALES,
                k=centauro_config.CHAT_RAG_TOP_K
            )
            if resultados:
                fragmentos = [r['text'] for r in resultados]
                return "\n\n---\n\n".join(fragmentos)
            return "No se encontró información en los manuales."

        else:
            # Búsqueda general en todas las colecciones
            return self._busqueda_multicoleccion(pregunta)

    def _obtener_perfil_asesor(self, nombre_asesor: str) -> str:
        """Obtiene y formatea el perfil de un asesor"""
        try:
            perfil = memory_manager.cargar_perfil(nombre_asesor)

            if perfil.total_evaluaciones == 0:
                return f"No hay evaluaciones registradas para {nombre_asesor}."

            texto_perfil = f"""
PERFIL DE {perfil.nombre.upper()}
{'='*50}

📊 RESUMEN:
- Total evaluaciones: {perfil.total_evaluaciones}
- Promedio general: {perfil.puntuacion_promedio:.1f}/5
- Primera evaluación: {perfil.fecha_primera_evaluacion}
- Última evaluación: {perfil.fecha_ultima_evaluacion}

📈 TENDENCIA:
- Estado: {perfil.tendencia_global}
- Cambio reciente: {perfil.cambio_reciente:+.1f} puntos

✅ FORTALEZAS CONSISTENTES:
{', '.join(perfil.fortalezas_consistentes) if perfil.fortalezas_consistentes else 'No identificadas aún'}

🎯 ÁREAS DE MEJORA CONSISTENTES:
{', '.join(perfil.areas_mejora_consistentes) if perfil.areas_mejora_consistentes else 'Ninguna crítica'}
"""
            return texto_perfil

        except Exception as e:
            return f"Error obteniendo perfil: {e}"

    def _obtener_estadisticas_globales(self) -> str:
        """Obtiene estadísticas del sistema completo"""
        try:
            stats = memory_manager.obtener_estadisticas_globales()

            texto_stats = f"""
ESTADÍSTICAS GLOBALES DEL SISTEMA
{'='*50}

👥 ASESORES:
- Total asesores: {stats.get('total_asesores', 0)}
- Asesores mejorando: {stats.get('asesores_mejorando', 0)}
- Asesores empeorando: {stats.get('asesores_empeorando', 0)}

📊 EVALUACIONES:
- Total evaluaciones: {stats.get('total_evaluaciones', 0)}
- Promedio global: {stats.get('promedio_global', 0):.1f}/5

📚 BASE DE CONOCIMIENTO:
- Conversaciones excelentes en RAG: {stats.get('conversaciones_en_rag', 0)}
"""
            return texto_stats

        except Exception as e:
            return f"Error obteniendo estadísticas: {e}"

    def _busqueda_multicoleccion(self, pregunta: str) -> str:
        """Busca en múltiples colecciones y combina resultados"""
        resultados_todos = []

        # Manuales
        res_manuales = buscar_en_coleccion(
            query=pregunta,
            collection_name=centauro_config.COLLECTION_MANUALES,
            k=2
        )
        if res_manuales:
            resultados_todos.append("## DESDE MANUALES:\n" + res_manuales[0]['text'])

        # Buenas prácticas
        res_ejemplos = buscar_en_coleccion(
            query=pregunta,
            collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
            k=2
        )
        if res_ejemplos:
            resultados_todos.append("## DESDE EJEMPLOS:\n" + res_ejemplos[0]['text'])

        if resultados_todos:
            return "\n\n---\n\n".join(resultados_todos)

        return "No se encontró información relevante."

    def _generar_respuesta(self, pregunta: str, contexto: str, intencion: str) -> str:
        """Genera respuesta usando LLM con el contexto obtenido"""

        # Prompt según intención
        if intencion == "perfil":
            prompt_sistema = """
Eres un asistente especializado en análisis de rendimiento de asesores comerciales.

El usuario pregunta por su perfil y tienes acceso a sus estadísticas históricas.

IMPORTANTE:
- Sé directo y constructivo
- Resalta fortalezas antes de mencionar áreas de mejora
- Usa datos concretos del perfil
- Sugiere acciones específicas si hay áreas de mejora
"""

        elif intencion == "ejemplo":
            prompt_sistema = """
Eres un experto en ventas consultivas que proporciona ejemplos prácticos.

IMPORTANTE:
- Los ejemplos son REFERENCIAS, no reglas absolutas
- Explica el "por qué" detrás de cada técnica
- Sugiere adaptaciones según el contexto
- Mantén un tono inspirador, no prescriptivo
"""

        elif intencion == "manual":
            prompt_sistema = """
Eres un instructor de ventas consultivas que explica procedimientos y mejores prácticas.

IMPORTANTE:
- Explica de forma clara y estructurada
- Usa el contexto del manual pero explícalo con tus palabras
- Proporciona razones detrás de cada recomendación
- Sé conciso pero completo
"""

        elif intencion == "estadisticas":
            prompt_sistema = """
Eres un analista de datos que presenta estadísticas del sistema de forma comprensible.

IMPORTANTE:
- Presenta datos de forma clara
- Identifica tendencias y patrones
- Sugiere interpretaciones útiles
- Mantén un tono objetivo
"""

        else:
            prompt_sistema = """
Eres un asistente experto en ventas consultivas y evaluación de llamadas comerciales.

Responde preguntas usando el contexto proporcionado de nuestra base de conocimiento.

IMPORTANTE:
- Sé conciso y directo
- Cita ejemplos concretos del contexto
- Si no hay información suficiente, dilo claramente
"""

        # Construir prompt de usuario
        prompt_usuario = f"""
PREGUNTA DEL USUARIO:
{pregunta}

CONTEXTO RELEVANTE:
{contexto}

Responde la pregunta del usuario basándote en el contexto proporcionado.
Si el contexto no es suficiente para responder, indícalo claramente.
"""

        try:
            respuesta = consultar_gpt(
                prompt_sistema,
                prompt_usuario,
                "chat_interactivo",
                force_json=False  # Chat NO necesita JSON, solo texto
            )
            return respuesta

        except Exception as e:
            return f"Error generando respuesta: {e}"

    def obtener_historial(self, ultimas_n: int = 5) -> List[Dict]:
        """Devuelve las últimas N interacciones del historial"""
        return self.historial_conversacion[-ultimas_n:]

    def limpiar_historial(self):
        """Limpia el historial de conversación"""
        self.historial_conversacion.clear()
