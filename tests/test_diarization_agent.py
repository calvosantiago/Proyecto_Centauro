"""
Test del Agente de Diarización

INSTRUCCIÓN: Copia TODO este archivo en tests/test_diarization_agent.py
"""
import sys
from pathlib import Path

# Añadir directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from centauro.agents import DiarizationAgent

# --- TEXTO DE PRUEBA ---
TEXTO_TEST = """
Hola buenos días, soy María de OBS Business School. 
Hablo con Pedro Martínez?
Sí, soy yo. 
Perfecto Pedro. Te llamo porque solicitaste información sobre nuestro Máster en Data Science. 
¿Es buen momento para hablar unos minutos?
Sí, dime.
Genial. Cuéntame, ¿qué te motivó a interesarte por este programa?
Bueno, trabajo en una empresa de consultoría y veo que cada vez se demanda más conocimiento en análisis de datos.
Entiendo. ¿Y actualmente qué rol desempeñas en tu empresa?
Soy consultor junior, pero quiero especializarme más.
Perfecto. ¿Has tenido alguna formación previa en programación o estadística?
Sí, hice un curso de Python hace un año.
Muy bien. El programa es 100% online con clases en vivo. ¿Cómo lo ves compatible con tu horario laboral?
Trabajo hasta las 6pm, así que si las clases son por la tarde me vendría bien.
Las clases son martes y jueves de 7pm a 9pm, hora española. Te da tiempo?
Sí, perfecto.
"""

def test_diarization():
    print("="*60)
    print("TEST: Agente de Diarización v2.0")
    print("="*60)
    
    # Crear agente
    agente = DiarizationAgent(nombre_asesor="María")
    
    # Ejecutar diarización
    resultado = agente.diarizar(TEXTO_TEST, log_id="test_001")
    
    print("\n" + "="*60)
    print("RESULTADO:")
    print("="*60)
    print(resultado)
    
    # Validaciones básicas
    assert "[ASESOR]" in resultado, "Falta etiqueta ASESOR"
    assert "[LEAD]" in resultado, "Falta etiqueta LEAD"
    
    # Contar turnos
    turnos_asesor = resultado.count("[ASESOR]")
    turnos_lead = resultado.count("[LEAD]")
    
    print("\n" + "="*60)
    print("ESTADÍSTICAS:")
    print("="*60)
    print(f"Turnos ASESOR: {turnos_asesor}")
    print(f"Turnos LEAD: {turnos_lead}")
    print(f"Proporción: {turnos_asesor / (turnos_asesor + turnos_lead) * 100:.1f}% ASESOR")
    
    # Validación lógica
    assert turnos_asesor > 3, "Muy pocos turnos de ASESOR"
    assert turnos_lead > 3, "Muy pocos turnos de LEAD"
    
    print("\n✅ TEST PASADO")

if __name__ == "__main__":
    test_diarization()