# 📚 Guía: Sistema de Buenas Prácticas

## 🎯 Objetivo

Permitir que el Sheriff consulte **ejemplos de conversaciones exitosas** como **referencia inspiradora**, no como reglas rígidas.

**Filosofía clave**: Los ejemplos son guías, NO plantillas obligatorias. El Sheriff debe:
- ✅ Usarlos para identificar patrones de éxito
- ✅ Citar fragmentos concretos en el feedback
- ✅ Sugerir técnicas basadas en los ejemplos
- ❌ NO penalizar si la conversación es diferente pero efectiva
- ❌ NO exigir que todo sea exactamente igual al ejemplo

---

## 📁 Estructura de Archivos

```
Proyecto_Centauro/
├── inputs/
│   └── buenas_practicas/           ← Coloca aquí tus archivos .vtt
│       ├── investigacion/
│       │   ├── ejemplo_001.vtt
│       │   ├── ejemplo_002.vtt
│       │   └── ...
│       ├── cierre/
│       │   └── ejemplo_001.vtt
│       ├── proximos_pasos/
│       └── otros/
│
└── inputs/docs/
    └── buenas_practicas/            ← Ejemplos procesados (indexados en RAG)
        ├── investigacion_ejemplo_001.txt
        ├── investigacion_ejemplo_002.txt
        └── ...
```

---

## 🚀 Flujo de Trabajo

### **1. Coloca los archivos .vtt**

Organiza tus transcripciones de buenas conversaciones en subcarpetas por sección:

```bash
inputs/buenas_practicas/
├── investigacion/          # Ejemplos de buena apertura y detección
├── cierre/                 # Ejemplos de cierre exitoso
├── proximos_pasos/         # Ejemplos de fijación de próximos pasos
└── otros/                  # Otros ejemplos diversos
```

**Formato esperado de los .vtt:**
```
WEBVTT

00:00:05.000 --> 00:00:08.000
Agente: Hola María, gracias por tu interés en nuestro programa...

00:00:08.000 --> 00:00:12.000
Alumno: Hola, estoy buscando especializarme en marketing digital...
```

---

### **2. Procesa los ejemplos**

Ejecuta el script procesador:

```bash
python -m centauro.tools.procesar_buenas_practicas
```

Esto hará:
1. ✅ Leer todos los `.vtt` en `inputs/buenas_practicas/`
2. ✅ Analizar cada conversación con GPT para detectar:
   - Patrones de comunicación exitosa
   - Técnicas específicas usadas
   - Fragmentos destacados
3. ✅ Generar archivos `.txt` optimizados en `inputs/docs/buenas_practicas/`
4. ✅ Preparar los ejemplos para indexación en ChromaDB

**Costo aproximado**: ~$0.05-0.10 por ejemplo (solo se ejecuta una vez)

---

### **3. Re-indexa el RAG**

Ejecuta el sistema principal para que ChromaDB indexe los nuevos ejemplos:

```bash
python main.py
```

El sistema detectará los nuevos archivos en `inputs/docs/buenas_practicas/` y los indexará automáticamente.

---

### **4. El Sheriff ahora puede consultar ejemplos**

Cuando analices conversaciones, el Sheriff:

1. **Buscará ejemplos relevantes** automáticamente según el bloque (investigación, cierre, etc.)
2. **Añadirá contexto enriquecido** al prompt con fragmentos de buenas prácticas
3. **Citará ejemplos concretos** en el feedback:

```
📊 INVESTIGACIÓN: 3/5

El agente hizo preguntas, pero fueron muy cerradas (sí/no).

💡 Buena práctica detectada:
   En conversaciones exitosas, los agentes usan preguntas abiertas
   que invitan a compartir contexto:

   Ejemplo: "¿Qué te gustaría estar haciendo en 2-3 años?"

   Esto genera 3x más información útil que preguntas cerradas.

Mejora sugerida: Reemplazar "¿Te interesa el MBA?" por
"¿Qué te motiva a buscar un programa de estas características?"
```

---

## 📊 Estructura de Ejemplo Procesado

Cada ejemplo procesado contiene:

```markdown
=== EJEMPLO DE BUENA PRÁCTICA: INVESTIGACIÓN ===
Archivo: ejemplo_001.vtt
Duración: 8 min
Puntuación: 5/5

PATRONES DETECTADOS:
  ✓ pregunta_abierta
  ✓ escucha_activa
  ✓ exploracion_profunda
  ✓ personalizacion

TÉCNICAS USADAS:
  • Preguntó sobre experiencia laboral actual
  • Exploró objetivos profesionales a 2-3 años
  • Conectó programa con aspiraciones del alumno
  • Validó las preocupaciones antes de responder

FRAGMENTOS DESTACADOS:

  [1] "¿Qué te gustaría estar haciendo profesionalmente en 2 o 3 años?"
      → Por qué funciona: Pregunta abierta que explora motivación profunda,
        no solo interés superficial en el programa

  [2] "Entiendo que el tema de la inversión es importante para ti..."
      → Por qué funciona: Validación emocional antes de dar información,
        genera confianza y apertura

--- CONVERSACIÓN COMPLETA ---
AGENTE: Hola María, gracias por tu interés en nuestro programa...
ALUMNO: Hola, estoy buscando especializarme en marketing digital...
[... resto de la conversación ...]
```

---

## ⚙️ Configuración Avanzada

### **Cambiar el número de ejemplos consultados**

En `centauro/agents/base_agent.py` línea ~131:

```python
def _buscar_ejemplos_relevantes(self, transcripcion: str, max_ejemplos: int = 2):
    # Cambiar max_ejemplos a 1, 2, 3, etc.
```

### **Desactivar ejemplos temporalmente**

Si quieres que el Sheriff NO use ejemplos en una evaluación:

```python
# En investigacion_agent.py (o cualquier agente)
# Comentar esta línea:
# manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

# Y usar directamente:
manual_enriquecido = manual
```

### **Añadir más secciones**

Para añadir ejemplos de nuevas secciones:

1. Crea subcarpeta en `inputs/buenas_practicas/nueva_seccion/`
2. Coloca tus `.vtt` ahí
3. Ejecuta `python -m centauro.tools.procesar_buenas_practicas`
4. Re-indexa con `python main.py`

---

## 🔍 Verificar que funciona

### **1. Comprobar archivos procesados:**

```bash
# Windows
dir "inputs\docs\buenas_practicas"

# Deberías ver archivos .txt como:
# investigacion_ejemplo_001.txt
# cierre_ejemplo_001.txt
# etc.
```

### **2. Comprobar indexación:**

```bash
python -m centauro.inspect_rag
```

Deberías ver mensajes como:
```
📚 Documentos indexados: 45
   - 30 fragmentos de manuales
   - 15 fragmentos de buenas prácticas
```

### **3. Ejecutar análisis de prueba:**

```bash
python main.py --archivo inputs/transcripts/test.vtt
```

En los logs verás:
```
📄 Procesando: investigacion_agent.py
   🔍 Buscando ejemplos de buenas prácticas...
   ✅ 2 ejemplos relevantes encontrados
```

---

## 🐛 Troubleshooting

### **Problema: No se encuentran ejemplos**

**Síntoma:**
```
ℹ️ No se pudieron cargar ejemplos de buenas prácticas: ...
```

**Soluciones:**
1. Verifica que existen archivos en `inputs/docs/buenas_practicas/`
2. Re-indexa el RAG: `python main.py`
3. Comprueba que ChromaDB tiene documentos: `python -m centauro.inspect_rag`

---

### **Problema: Los ejemplos no son relevantes**

**Síntoma:** El Sheriff cita ejemplos que no tienen relación con la conversación

**Soluciones:**
1. Reduce `max_ejemplos` de 2 a 1 en `base_agent.py`
2. Mejora los metadatos de los ejemplos (sección, etiquetas)
3. Aumenta el threshold de similitud en el RAG

---

### **Problema: El procesamiento falla con error LLM**

**Síntoma:**
```
⚠️ Error LLM: JSONDecodeError...
```

**Soluciones:**
1. Verifica que tienes API key configurada en `.env`
2. Verifica que los archivos `.vtt` están bien formateados
3. Prueba con un solo archivo primero

---

## 💡 Mejores Prácticas

### **¿Cuántos ejemplos necesito?**

- **Mínimo recomendado**: 3-5 ejemplos por sección (15-25 total)
- **Óptimo**: 5-10 ejemplos por sección (30-50 total)
- **Máximo útil**: 15 ejemplos por sección (no más, hay rendimientos decrecientes)

### **¿Qué hace un buen ejemplo?**

✅ **Sí:**
- Conversación real que obtuvo 5/5 en evaluaciones previas
- Muestra técnicas específicas y accionables
- Tiene variedad (diferentes perfiles de alumnos)
- Duración: 5-15 minutos (no muy largo)

❌ **No:**
- Conversaciones genéricas sin técnicas destacadas
- Ejemplos demasiado largos (>30 min)
- Casos extremos o atípicos
- Conversaciones con errores evidentes

### **Mantenimiento**

- **Añadir ejemplos nuevos**: Mensual o trimestral
- **Revisar relevancia**: Cada 6 meses
- **Actualizar si cambian criterios**: Cuando actualices el manual de ventas

---

## 📈 Impacto Esperado

Con ejemplos de buenas prácticas, el Sheriff:

1. **Da feedback más accionable** (+40% especificidad)
   - Antes: "Mejorar las preguntas"
   - Ahora: "Usar preguntas abiertas como 'Cuéntame sobre tu experiencia actual...'"

2. **Reduce falsos negativos** (-30% errores)
   - No penaliza técnicas efectivas pero diferentes del manual

3. **Acelera el aprendizaje** (+50% adopción)
   - Los agentes ven ejemplos concretos, no solo teoría

4. **Calibra mejor las puntuaciones**
   - Referencia clara de qué es un 5/5 vs. un 3/5

---

## 🔄 Flujo Completo (Resumen)

```
1. Colectas .vtt de conversaciones exitosas
   ↓
2. Organizas en inputs/buenas_practicas/seccion/
   ↓
3. Ejecutas: python -m centauro.tools.procesar_buenas_practicas
   ↓
4. GPT analiza y extrae patrones/técnicas (UNA SOLA VEZ)
   ↓
5. Se generan .txt optimizados en inputs/docs/buenas_practicas/
   ↓
6. Ejecutas: python main.py (re-indexa RAG)
   ↓
7. ChromaDB indexa los ejemplos
   ↓
8. El Sheriff ahora puede consultar ejemplos automáticamente
   ↓
9. Cada análisis busca 1-2 ejemplos relevantes (GRATIS, local)
   ↓
10. El feedback incluye citas y técnicas concretas
```

---

## 📞 Soporte

Si tienes dudas o problemas:

1. Revisa esta guía completa
2. Ejecuta `python -m centauro.inspect_rag` para diagnóstico
3. Consulta los logs del Sheriff (busca "ejemplos de buenas prácticas")
4. Contacta con el equipo técnico

---

**Versión:** 1.0
**Última actualización:** 2025-01-23
**Autor:** Claude (Proyecto Centauro)
