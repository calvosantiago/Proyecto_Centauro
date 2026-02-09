"""
RAG Dinámico v2.0 con Optimizaciones de Tokens + Análisis Exhaustivo

INSTRUCCIÓN: REEMPLAZA el contenido de:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\core\\rag_dynamic.py

CAMBIOS APLICADOS:
- Top-K reducido de 20 → 5 fragmentos
- Análisis exhaustivo con 6 muestras distribuidas para llamadas largas
- Máximo 8 items por categoría de temas
"""
from typing import List, Dict, Optional
import json
from ..llm_client import consultar_gpt
from ..rag import collection_manuales, collection_coaching
from ..config import centauro_config
from .config_agents import OptimizacionConfig

class DynamicRAGAgent:
    """Agente que adapta búsquedas RAG con optimización de tokens"""
    
    def __init__(self):
        self.cache_temas = {}
        self.cache_contextos = {}
        self.config = OptimizacionConfig()
        
        self.query_base_map = {
            "Apertura": "saludo inicial presentación rapport",
            "Detección de necesidades": "preguntas descubrimiento motivaciones escucha",
            "Presentación del programa": "explicar programa propuesta valor",
            "Manejo de objeciones": "objeciones rebatir validar técnicas",
            "Cierre y siguiente paso": "cierre compromiso siguiente paso",
            "Estilo y comunicación": "tono empatía comunicación efectiva",
            "Legal (Compliance)": "aviso legal grabación RGPD"
        }
    
    def extraer_temas_llamada(self, transcripcion: str, cache_key: str) -> Dict:
        """Analiza transcripción para identificar temas (CON CACHE)"""
        if cache_key in self.cache_temas:
            print("   💾 Usando temas en cache")
            return self.cache_temas[cache_key]
        
        print("   🔍 Extrayendo temas (análisis exhaustivo)...")
        
        # NUEVO: Muestreo inteligente para llamadas largas
        if len(transcripcion) > 12000:
            # Para entrevistas de 40+ min: 6 muestras distribuidas
            longitud = len(transcripcion)
            segmento = longitud // 6
            
            transcripcion_resumida = (
                transcripcion[:2500] +                      # Inicio (apertura)
                "\n\n[... MUESTRA 2 ...]\n\n" +
                transcripcion[segmento:segmento+2000] +     # ~15% de la llamada
                "\n\n[... MUESTRA 3 ...]\n\n" +
                transcripcion[segmento*2:segmento*2+2000] + # ~30% de la llamada
                "\n\n[... MUESTRA 4 ...]\n\n" +
                transcripcion[segmento*3:segmento*3+2000] + # ~50% de la llamada
                "\n\n[... MUESTRA 5 ...]\n\n" +
                transcripcion[segmento*4:segmento*4+2000] + # ~70% de la llamada
                "\n\n[... MUESTRA 6 ...]\n\n" +
                transcripcion[-2500:]                       # Final (cierre)
            )
            print(f"      📊 Llamada larga detectada: 6 muestras distribuidas")
        elif len(transcripcion) > 6000:
            # Para entrevistas de 20-40 min: 4 muestras
            cuarto = len(transcripcion) // 4
            transcripcion_resumida = (
                transcripcion[:2500] +
                "\n\n[... MUESTRA 2 ...]\n\n" +
                transcripcion[cuarto:cuarto+1500] +
                "\n\n[... MUESTRA 3 ...]\n\n" +
                transcripcion[cuarto*2:cuarto*2+1500] +
                "\n\n[... MUESTRA 4 ...]\n\n" +
                transcripcion[-2500:]
            )
            print(f"      📊 Llamada media: 4 muestras distribuidas")
        else:
            # Para entrevistas cortas (<20 min): enviar completa
            transcripcion_resumida = transcripcion
            print(f"      📊 Llamada corta: análisis completo")
        
        prompt_sistema = """
Extrae los temas MÁS RELEVANTES de esta llamada comercial.

PRIORIZA:
- Objeciones mencionadas por el lead
- Necesidades expresadas explícitamente
- Temas de conversación con más tiempo dedicado

FORMATO JSON:
{
  "temas_principales": ["tema1", "tema2", "tema3", "tema4", "tema5"],
  "objeciones_detectadas": ["objecion1", "objecion2", "objecion3"],
  "necesidades_lead": ["necesidad1", "necesidad2", "necesidad3"],
  "contexto_lead": "Descripción breve del perfil y situación del lead"
}

Máximo 8 items por categoría. Solo lo observable y relevante.
Si hay menos de 8, devuelve solo los que existan.
"""
        
        try:
            resp = consultar_gpt(prompt_sistema, transcripcion_resumida, "rag_temas")
            temas = json.loads(resp)
            self.cache_temas[cache_key] = temas
            print(f"      ✓ Temas detectados: {len(temas.get('temas_principales', []))}")
            return temas
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            temas_fallback = {
                "temas_principales": [],
                "objeciones_detectadas": [],
                "necesidades_lead": [],
                "contexto_lead": ""
            }
            self.cache_temas[cache_key] = temas_fallback
            return temas_fallback
    
    def buscar_contexto_para_bloque(self, nombre_bloque: str,
                                    transcripcion: str, cache_key: str) -> str:
        """Recupera contexto de MÚLTIPLES colecciones (manuales + coaching)"""
        cache_full_key = f"{cache_key}_{nombre_bloque}"

        if cache_full_key in self.cache_contextos:
            print(f"   💾 Cache hit: {nombre_bloque}")
            return self.cache_contextos[cache_full_key]

        print(f"   🔎 RAG: {nombre_bloque}")

        temas = self.extraer_temas_llamada(transcripcion, cache_key)
        query = self._construir_query_dinamica(nombre_bloque, temas)

        fragmentos_totales = []

        try:
            # 1. Buscar en colección de MANUALES GENERALES
            total_docs_manuales = collection_manuales.count()
            if total_docs_manuales > 0:
                n_results = min(centauro_config.RAG_TOP_K_GENERAL, total_docs_manuales)
                resultados_manuales = collection_manuales.query(
                    query_texts=[query],
                    n_results=n_results
                )

                if resultados_manuales['documents'] and resultados_manuales['documents'][0]:
                    docs = resultados_manuales['documents'][0]
                    metadatas = resultados_manuales.get('metadatas', [[]])[0]
                    fuentes_vistas = set()

                    for doc, meta in zip(docs, metadatas if metadatas else [{}]*len(docs)):
                        fuente = meta.get('fuente', 'desconocido') if isinstance(meta, dict) else 'desconocido'
                        fuentes_vistas.add(fuente)
                        fragmentos_totales.append(f"[MANUAL: {fuente}]\n{doc}")

                    print(f"      Manuales consultados: {', '.join(fuentes_vistas)}")

            # 2. Buscar en colección de COACHING / LIBROS DE VENTAS
            total_docs_coaching = collection_coaching.count()
            if total_docs_coaching > 0:
                n_coaching = min(centauro_config.RAG_TOP_K_COACHING, total_docs_coaching)
                resultados_coaching = collection_coaching.query(
                    query_texts=[query],
                    n_results=n_coaching
                )

                if resultados_coaching['documents'] and resultados_coaching['documents'][0]:
                    docs_c = resultados_coaching['documents'][0]
                    metadatas_c = resultados_coaching.get('metadatas', [[]])[0]

                    for doc, meta in zip(docs_c, metadatas_c if metadatas_c else [{}]*len(docs_c)):
                        fuente = meta.get('fuente', '') if isinstance(meta, dict) else ''
                        autor = meta.get('autor', '') if isinstance(meta, dict) else ''
                        etiqueta = f"COACHING: {fuente}" if fuente else "COACHING"
                        if autor:
                            etiqueta += f" ({autor})"
                        fragmentos_totales.append(f"[{etiqueta}]\n{doc}")

                    print(f"      Coaching: {len(docs_c)} fragmentos de libros")

            if not fragmentos_totales:
                print("   ⚠️ No se encontraron fragmentos en ninguna colección")
                return ""

            # Filtrar por relevancia (solo manuales, coaching siempre se incluye)
            fragmentos_manuales = [f for f in fragmentos_totales if f.startswith("[MANUAL:")]
            fragmentos_coaching = [f for f in fragmentos_totales if f.startswith("[COACHING:")]

            fragmentos_manuales_filtrados = self._filtrar_por_relevancia(fragmentos_manuales, query)
            if not fragmentos_manuales_filtrados:
                fragmentos_manuales_filtrados = fragmentos_manuales[:3]

            # Combinar: manuales filtrados + coaching (siempre incluido)
            fragmentos_finales = fragmentos_manuales_filtrados + fragmentos_coaching

            contexto = "\n\n--- FRAGMENTO ---\n".join(fragmentos_finales)
            self.cache_contextos[cache_full_key] = contexto

            print(f"      Total: {len(fragmentos_finales)} fragmentos ({len(fragmentos_manuales_filtrados)} manuales + {len(fragmentos_coaching)} coaching)")
            return contexto

        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            return ""
    
    def _construir_query_dinamica(self, nombre_bloque: str, temas: Dict) -> str:
        """Construye query adaptativa"""
        query_base = self.query_base_map.get(nombre_bloque, "venta consultiva")
        componentes = [query_base]
        
        if nombre_bloque == "Detección de necesidades":
            necesidades = temas.get("necesidades_lead", [])
            if necesidades:
                componentes.append(" ".join(necesidades[:2]))
        
        elif nombre_bloque == "Manejo de objeciones":
            objeciones = temas.get("objeciones_detectadas", [])
            if objeciones:
                componentes.append(" ".join(objeciones[:2]))
        
        elif nombre_bloque == "Presentación del programa":
            temas_principales = temas.get("temas_principales", [])
            if temas_principales:
                componentes.append(" ".join(temas_principales[:2]))
        
        query_final = " ".join(componentes)
        
        # OPTIMIZACIÓN: Limitar a 100 caracteres
        if len(query_final) > 100:
            query_final = query_final[:100]
        
        return query_final
    
    def _filtrar_por_relevancia(self, fragmentos: List[str], query: str) -> List[str]:
        """Filtra por relevancia semántica"""
        palabras_query = set(query.lower().split())
        
        fragmentos_con_score = []
        for frag in fragmentos:
            palabras_frag = set(frag.lower().split())
            overlap = len(palabras_query.intersection(palabras_frag))
            score = overlap / len(palabras_query) if palabras_query else 0
            
            if score >= 0.15:
                fragmentos_con_score.append((frag, score))
        
        fragmentos_con_score.sort(key=lambda x: x[1], reverse=True)
        
        # OPTIMIZACIÓN: Retornar máximo 3 fragmentos
        return [frag for frag, _ in fragmentos_con_score[:3]]
    
    def limpiar_cache(self):
        """Limpia caches"""
        self.cache_temas.clear()
        self.cache_contextos.clear()
        print("   🧹 Cache limpiado")


# ==================== FUNCIÓN AUXILIAR PARA BUENAS PRÁCTICAS ====================

def buscar_contexto_dinamico(
    query: str,
    collection_name: str = "default",
    k: int = 3,
    filtro_seccion: str = None
) -> List[Dict]:
    """
    Función auxiliar para buscar en colecciones específicas del RAG.

    ACTUALIZADO v4.2: Soporta filtrado por sección en buenas prácticas.

    Args:
        query: Texto de búsqueda
        collection_name: Nombre de la colección (usar centauro_config.COLLECTION_*)
        k: Número de resultados a devolver
        filtro_seccion: Nombre del bloque para filtrar buenas prácticas
                        (ej: "Investigación", "Cierre y próximos pasos")

    Returns:
        Lista de diccionarios con 'text' y 'metadata' de cada resultado

    Nota: Si la colección no existe o está vacía, devuelve lista vacía.
    """
    try:
        from ..rag import buscar_en_coleccion
        from ..config import centauro_config

        # Mapeo de nombres legacy a nombres oficiales
        if collection_name == "buenas_practicas":
            collection_name = centauro_config.COLLECTION_BUENAS_PRACTICAS
        elif collection_name == "coaching_ventas" or collection_name == "coaching":
            collection_name = centauro_config.COLLECTION_COACHING
        elif collection_name == "default":
            collection_name = centauro_config.COLLECTION_MANUALES

        # Construir filtro de metadata si se especifica sección
        filtro_metadata = None
        if filtro_seccion and collection_name == centauro_config.COLLECTION_BUENAS_PRACTICAS:
            filtro_metadata = {"seccion": filtro_seccion}

        # Usar función de búsqueda avanzada
        resultados = buscar_en_coleccion(
            query=query,
            collection_name=collection_name,
            k=k,
            filtro_metadata=filtro_metadata
        )

        return resultados

    except Exception as e:
        print(f"   Error buscando en coleccion '{collection_name}': {e}")
        return []