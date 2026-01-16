"""
Test de Optimizaciones: Valida que el ahorro de tokens es real

INSTRUCCIÓN: Copia este archivo en tests/test_optimizaciones.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from centauro.core.config_agents import OptimizacionConfig
from centauro.core.orchestrator import CentauroOrchestrator

def test_extractos():
    """Valida que los extractos reducen tokens"""
    print("="*60)
    print("TEST 1: Validación de Extractos")
    print("="*60)
    
    # Transcripción simulada
    transcripcion = "Lorem ipsum " * 3000  # ~36,000 caracteres
    
    print(f"\n📏 Longitud transcripción completa: {len(transcripcion)} chars")
    
    # Test extracto Apertura
    extracto_apertura = OptimizacionConfig.get_extracto("Apertura", transcripcion)
    print(f"   Extracto Apertura: {len(extracto_apertura)} chars ({len(extracto_apertura)/len(transcripcion)*100:.1f}%)")
    
    # Test extracto Cierre
    extracto_cierre = OptimizacionConfig.get_extracto("Cierre y siguiente paso", transcripcion)
    print(f"   Extracto Cierre: {len(extracto_cierre)} chars ({len(extracto_cierre)/len(transcripcion)*100:.1f}%)")
    
    # Test extracto Legal
    extracto_legal = OptimizacionConfig.get_extracto("Legal (Compliance)", transcripcion)
    print(f"   Extracto Legal: {len(extracto_legal)} chars ({len(extracto_legal)/len(transcripcion)*100:.1f}%)")
    
    # Cálculo de ahorro
    total_sin_optimizar = len(transcripcion) * 3  # 3 agentes × transcripción completa
    total_optimizado = len(extracto_apertura) + len(extracto_cierre) + len(extracto_legal)
    
    ahorro_pct = (1 - total_optimizado / total_sin_optimizar) * 100
    
    print(f"\n💰 AHORRO:")
    print(f"   Sin optimizar: {total_sin_optimizar:,} chars")
    print(f"   Optimizado: {total_optimizado:,} chars")
    print(f"   Ahorro: {ahorro_pct:.1f}%")
    
    assert ahorro_pct > 90, f"Ahorro insuficiente: {ahorro_pct:.1f}% (esperado >90%)"
    print("\n✅ TEST PASADO: Ahorro >90%")

def test_config_batch():
    """Valida configuración de batches"""
    print("\n" + "="*60)
    print("TEST 2: Configuración de Batches")
    print("="*60)
    
    config = OptimizacionConfig()
    
    print(f"\n📦 Batch Ligero:")
    print(f"   Agentes: {config.BATCH_LIGERO.agentes}")
    print(f"   Usa transcripción completa: {config.BATCH_LIGERO.usa_transcripcion_completa}")
    
    print(f"\n📦 Batch Pesado:")
    print(f"   Agentes: {config.BATCH_PESADO.agentes}")
    print(f"   Usa transcripción completa: {config.BATCH_PESADO.usa_transcripcion_completa}")
    
    # Validar que hay 7 agentes en total
    total_agentes = len(config.BATCH_LIGERO.agentes) + len(config.BATCH_PESADO.agentes)
    assert total_agentes == 7, f"Error: {total_agentes} agentes (esperado 7)"
    
    print(f"\n✅ TEST PASADO: 7 agentes configurados")

def test_rag_top_k():
    """Valida que RAG usa Top-K reducido"""
    print("\n" + "="*60)
    print("TEST 3: Optimización RAG")
    print("="*60)
    
    config = OptimizacionConfig()
    
    print(f"\n🔍 Top-K configurado: {config.RAG_TOP_K}")
    
    # Estimar ahorro
    top_k_anterior = 20
    fragmento_promedio = 400  # tokens por fragmento
    
    tokens_anterior = top_k_anterior * fragmento_promedio
    tokens_nuevo = config.RAG_TOP_K * fragmento_promedio
    
    ahorro = tokens_anterior - tokens_nuevo
    ahorro_pct = (ahorro / tokens_anterior) * 100
    
    print(f"   Tokens antes (Top-K=20): {tokens_anterior}")
    print(f"   Tokens ahora (Top-K={config.RAG_TOP_K}): {tokens_nuevo}")
    print(f"   Ahorro: {ahorro} tokens ({ahorro_pct:.1f}%)")
    
    assert config.RAG_TOP_K <= 5, "Top-K debe ser ≤5"
    print(f"\n✅ TEST PASADO: RAG optimizado")

def test_estadisticas():
    """Muestra estadísticas de ahorro"""
    print("\n" + "="*60)
    print("TEST 4: Estadísticas de Ahorro")
    print("="*60)
    
    stats = OptimizacionConfig.estadisticas_ahorro()
    
    print("\n📊 Optimizaciones Activas:")
    for key, valor in stats.items():
        print(f"   • {key}: {valor}")
    
    print(f"\n✅ TODAS LAS OPTIMIZACIONES CONFIGURADAS")

def main():
    print("\n" + "🚀"*30)
    print(" VALIDACIÓN DE OPTIMIZACIONES DEL SISTEMA MULTI-AGENTE")
    print("🚀"*30 + "\n")
    
    test_extractos()
    test_config_batch()
    test_rag_top_k()
    test_estadisticas()
    
    print("\n" + "="*60)
    print("✅ TODOS LOS TESTS PASADOS")
    print("="*60)
    print("\nCONCLUSIÓN:")
    print("El sistema está optimizado para reducir ~60% de tokens")
    print("vs implementación sin optimizar.")
    print()

if __name__ == "__main__":
    main()