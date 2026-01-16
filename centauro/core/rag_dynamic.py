"""
RAG Dinámico v2.0 con Optimizaciones de Tokens

INSTRUCCIÓN: Copia este archivo en centauro/core/rag_dynamic.py
CAMBIO CLAVE: Top-K reducido de 20 → 5 fragmentos
"""
from typing import List, Dict, Optional
import json
from ..llm_client import consultar_gpt
from ..rag import collection
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
        
        print("   🔍 Extrayendo temas...")
        
        # OPTIMIZACIÓN: Truncar agresivamente (inicio + final)
        if len(transcripcion) > 8000:
            # Para llamadas largas: inicio + 2 muestras del medio + final
            cuarto = len(transcripcion) // 4
            transcripcion_resumida = (
            transcripcion[:2500] +           # Inicio
            "\n\n[...]\n\n" + 
            transcripcion[cuarto:cuarto+1500] +  # Muestra del medio 1
            "\n\n[...]\n\n" + 
            transcripcion[cuarto*2:cuarto*2+1500] +  # Muestra del medio 2
            "\n\n[...]\n\n" + 
            transcripcion[-2500:]            # Final
        )   
        else:
            transcripcion_resumida = transcripcion
        
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
            print(f"      ✓ Temas: {len(temas.get('temas_principales', []))}")
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
        """Recupera contexto con Top-K REDUCIDO (5 en lugar de 20)"""
        cache_full_key = f"{cache_key}_{nombre_bloque}"
        
        if cache_full_key in self.cache_contextos:
            print(f"   💾 Cache hit: {nombre_bloque}")
            return self.cache_contextos[cache_full_key]
        
        print(f"   🔎 RAG: {nombre_bloque}")
        
        temas = self.extraer_temas_llamada(transcripcion, cache_key)
        query = self._construir_query_dinamica(nombre_bloque, temas)
        
        try:
            total_docs = collection.count()
            if total_docs == 0:
                print("   ⚠️ Base vacía")
                return ""
            
            # OPTIMIZACIÓN CRÍTICA: Top-K = 5 (antes 20)
            n_results = min(self.config.RAG_TOP_K, total_docs)
            
            resultados = collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            if not resultados['documents'] or not resultados['documents'][0]:
                return ""
            
            fragmentos = resultados['documents'][0]
            fragmentos_relevantes = self._filtrar_por_relevancia(fragmentos, query)
            
            if not fragmentos_relevantes:
                fragmentos_relevantes = fragmentos[:2]
            
            contexto = "\n\n--- FRAGMENTO ---\n".join(fragmentos_relevantes)
            self.cache_contextos[cache_full_key] = contexto
            
            print(f"      ✓ {len(fragmentos_relevantes)} fragmentos")
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
            
            if score >= 0.3:
                fragmentos_con_score.append((frag, score))
        
        fragmentos_con_score.sort(key=lambda x: x[1], reverse=True)
        
        # OPTIMIZACIÓN: Retornar máximo 3 fragmentos
        return [frag for frag, _ in fragmentos_con_score[:3]]
    
    def limpiar_cache(self):
        """Limpia caches"""
        self.cache_temas.clear()
        self.cache_contextos.clear()
        print("   🧹 Cache limpiado")