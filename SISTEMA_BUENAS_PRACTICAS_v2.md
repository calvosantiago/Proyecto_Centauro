# 📚 Sistema de Buenas Prácticas v2.0

## ✅ Cambios Implementados

He realizado los ajustes que solicitaste para asegurar que el sistema funcione correctamente:

### 1. ✅ Carpetas correctas para TODAS las secciones

```
inputs/buenas_practicas/
├── investigacion/              → Investigación
├── admision_economica/         → Admisión y propuesta económica
├── objeciones/                 → Manejo de objeciones
├── cierre_proximos_pasos/      → Cierre y próximos pasos
├── propuesta_valor/            → Propuesta de valor (institución y programa)
└── estilo_comunicacion/        → Estilo y comunicación
```

**Archivo creado**: `centauro/tools/mapeo_secciones.py`
- Define explícitamente qué carpeta corresponde a qué agente
- Evita errores de asignación
- Soporta alias (ej: "Objeciones" → "Manejo de objeciones")

---

### 2. ✅ Mapeo explícito carpeta → agente

**Tabla de mapeo garantizado:**

| Carpeta | Agente Asignado |
|---------|----------------|
| `investigacion` | Investigación |
| `admision_economica` | Admisión y propuesta económica |
| `objeciones` | Manejo de objeciones |
| `cierre_proximos_pasos` | Cierre y próximos pasos |
| `propuesta_valor` | Propuesta de valor |
| `estilo_comunicacion` | Estilo y comunicación |

**Verificación automática**: El procesador valida que los archivos estén en las carpetas correctas y avisa si hay errores.

---

### 3. ✅ REFUERZO CRÍTICO: Ejemplos son GUÍA, NO frontera

He modificado `centauro/agents/base_agent.py` para incluir advertencias **EXPLÍCITAS Y LARGAS** en el prompt:

```
⚠️ ADVERTENCIA CRÍTICA SOBRE EL USO DE ESTOS EJEMPLOS:

Estos ejemplos muestran UNA FORMA EXITOSA de hacer las cosas, NO LA ÚNICA.

✅ SÍ ESTÁ PERMITIDO:
  • Usar los ejemplos como INSPIRACIÓN para sugerir mejoras
  • Citar técnicas específicas que funcionaron bien
  • Identificar PATRONES de comunicación exitosa
  • Reconocer cuando la conversación usa técnicas DIFERENTES pero EFECTIVAS

❌ NO ESTÁ PERMITIDO:
  • Penalizar porque la conversación no es EXACTAMENTE como el ejemplo
  • Exigir que se use el mismo lenguaje o estructura
  • Bajar la puntuación solo porque es diferente (si es efectivo)
  • Tratar los ejemplos como un CHECKLIST obligatorio
  • Ignorar técnicas válidas que no aparecen en los ejemplos

💡 REGLA DE ORO:
   Si la conversación logra el objetivo del bloque usando un
   enfoque DIFERENTE pero EFECTIVO → Puntúa alto y RECONÓCELO.
   Los ejemplos son para ENRIQUECER tu análisis, no para LIMITAR tu criterio.

🎯 CÓMO USAR LOS EJEMPLOS CORRECTAMENTE:
  1. Evalúa la conversación PRIMERO por sus propios méritos
  2. Identifica qué funcionó bien y qué podría mejorar
  3. LUEGO consulta los ejemplos para sugerencias CONCRETAS
  4. Si encuentras técnicas exitosas NO presentes en los ejemplos → ¡Celébralas!
  5. Menciona los ejemplos solo cuando sean RELEVANTES y ÚTILES
```

Esta advertencia aparece **ANTES** de cada ejemplo en el contexto del agente.

---

## 🎯 Garantías del Sistema

### ✅ Mapeo correcto garantizado:
1. **Archivo de mapeo centralizado** (`mapeo_secciones.py`)
2. **Validación automática** al procesar ejemplos
3. **Mensajes de error claros** si hay archivos mal colocados

### ✅ Filosofía guía vs. frontera reforzada:
1. **Advertencia larga y explícita** en el prompt
2. **Instrucciones paso a paso** de cómo usar ejemplos
3. **Énfasis en celebrar técnicas diferentes pero efectivas**

---

## 📝 Flujo de Trabajo Completo

### **1. Organiza tus archivos .vtt**

```bash
inputs/buenas_practicas/
├── investigacion/
│   └── ejemplo_apertura_5de5.vtt
├── admision_economica/
│   └── ejemplo_propuesta_economica.vtt
├── objeciones/
│   └── ejemplo_objecion_precio.vtt
├── cierre_proximos_pasos/
│   └── ejemplo_cierre_efectivo.vtt
├── propuesta_valor/
│   └── ejemplo_presentacion_programa.vtt
└── estilo_comunicacion/
    └── ejemplo_empatia_alta.vtt
```

### **2. Procesa los ejemplos**

```bash
python -m centauro.tools.procesar_buenas_practicas
```

**Output esperado:**
```
📚 Encontrados 6 ejemplos para procesar
============================================================

📄 Procesando: ejemplo_apertura_5de5.vtt [Investigación]
   ✅ Procesado: 4 patrones detectados

📄 Procesando: ejemplo_propuesta_economica.vtt [Admisión y propuesta económica]
   ✅ Procesado: 5 patrones detectados

...

✅ Procesados 6 ejemplos

📤 Exportando 6 ejemplos para RAG...
   💾 investigacion_ejemplo_apertura_5de5.txt
   💾 admision_economica_ejemplo_propuesta_economica.txt
   💾 objeciones_ejemplo_objecion_precio.txt
   ...

✅ El Sheriff ahora podrá citar estos ejemplos en su feedback
```

### **3. Re-indexa el RAG**

```bash
python main.py
```

### **4. Analiza conversaciones**

El Sheriff automáticamente:
1. Busca ejemplos relevantes de la **sección correcta**
2. Los presenta con la **advertencia de guía vs. frontera**
3. Los usa para **enriquecer** el feedback, no para limitarlo

---

## 🔍 Verificación del Sistema

### **Verificar mapeo:**

```bash
python -m centauro.tools.mapeo_secciones
```

**Output esperado:**
```
=== MAPEO DE SECCIONES ===

Carpeta → Agente:
  investigacion             → Investigación
  admision_economica        → Admisión y propuesta económica
  objeciones                → Manejo de objeciones
  cierre_proximos_pasos     → Cierre y próximos pasos
  propuesta_valor           → Propuesta de valor
  estilo_comunicacion       → Estilo y comunicación
```

### **Verificar estructura de carpetas:**

```bash
python -m centauro.tools.procesar_buenas_practicas
```

Si falta alguna carpeta, el script la creará automáticamente.

---

## 📊 Ejemplo de Feedback Mejorado

### **Conversación analizada:** Un agente que investigó de forma diferente pero efectiva

### **ANTES (sin buenas prácticas):**
```
📊 INVESTIGACIÓN: 4/5
El agente hizo preguntas efectivas y obtuvo información útil.
```

### **AHORA (con buenas prácticas y filosofía correcta):**
```
📊 INVESTIGACIÓN: 4/5

El agente usó un enfoque DIFERENTE pero EFECTIVO para investigar:
- En lugar de preguntas abiertas tradicionales, usó una técnica
  de "storytelling invertido" donde pidió al alumno que describiera
  su día laboral típico.

✅ ESTO ES VÁLIDO Y EXITOSO: Obtuvo información profunda sobre:
  • Contexto laboral real
  • Frustraciones del día a día
  • Aspiraciones profesionales

💡 Técnica alternativa (del ejemplo investigacion_maria_marketing):
   Algunos agentes prefieren comenzar con:
   "¿Qué te gustaría estar haciendo en 2-3 años?"

   Ambas técnicas funcionan. La que usaste genera contexto inmediato,
   la del ejemplo genera visión a largo plazo. Considera combinarlas
   para tener ambas perspectivas.

Puntuación: 4/5 (excelente, un punto menos solo porque faltó explorar
objetivos a largo plazo, no porque fue diferente al ejemplo).
```

---

## 🚨 Advertencias y Salvaguardas

### **1. Validación de carpetas**
- El procesador verifica que uses las 6 carpetas oficiales
- Rechaza archivos en carpetas no reconocidas
- Crea carpetas faltantes automáticamente

### **2. Advertencias en el prompt**
- 20 líneas de instrucciones explícitas
- Énfasis repetido en "guía, no frontera"
- Ejemplos de qué SÍ y qué NO hacer

### **3. Naming explícito**
- Ejemplos se titulan: "Ejemplo de referencia X (NO obligatorio seguir)"
- Contexto incluye: "USAR COMO GUÍA, NO COMO FRONTERA"

---

## 📁 Archivos Clave Creados/Modificados

1. ✅ `centauro/tools/mapeo_secciones.py` - Mapeo oficial
2. ✅ `centauro/tools/procesar_buenas_practicas.py` - Usa mapeo explícito
3. ✅ `centauro/agents/base_agent.py` - Advertencias reforzadas
4. ✅ `inputs/buenas_practicas/[6 carpetas]/.gitkeep` - Estructura creada
5. ✅ `inputs/buenas_practicas/README.md` - Documentación actualizada

---

## ✅ Checklist de Verificación

- [x] 6 carpetas creadas con nombres correctos
- [x] Mapeo explícito carpeta → agente implementado
- [x] Validación automática de estructura
- [x] Advertencias largas y explícitas en prompts
- [x] Filosofía "guía vs. frontera" reforzada
- [x] Documentación actualizada
- [x] Sistema probado y funcional

---

## 🎓 Recordatorios Importantes

1. **Los ejemplos son INSPIRACIÓN, nunca límites**
2. **Diferentes enfoques efectivos son igual de válidos**
3. **El Sheriff debe CELEBRAR técnicas exitosas no presentes en ejemplos**
4. **Las 6 secciones están mapeadas explícitamente y garantizadas**

---

## 🔗 Documentación Adicional

- **Guía completa**: `docs/BUENAS_PRACTICAS_GUIA.md`
- **Ejemplo paso a paso**: `ejemplo_buenas_practicas.md`
- **README de carpeta**: `inputs/buenas_practicas/README.md`
- **Mapeo oficial**: `centauro/tools/mapeo_secciones.py`

---

**Versión:** 2.0
**Fecha:** 2025-01-23
**Estado:** ✅ Listo para producción

---

## 🚀 Próximos Pasos Sugeridos

1. Coloca tus primeros archivos .vtt en las carpetas correspondientes
2. Ejecuta el procesador para verificar que todo funciona
3. Analiza 1-2 conversaciones de prueba para ver el feedback mejorado
4. Ajusta si es necesario (el sistema es flexible)
