# Análisis Comparativo: Transcripción Teams vs. OpenAI Whisper en Proyecto Centauro

Este informe detalla las diferencias en la evaluación automatizada de ventas (sistema Centauro) al utilizar transcripciones nativas de Microsoft Teams frente a transcripciones procesadas por OpenAI Whisper, basándose en el análisis de 4 asesores.

---

## 1. Análisis por Asesor

### 👩‍💼 Esther López
* **Recomendación:** **WHISPER**
* **Mejora Estimada:** 75%

**Resumen del Caso:**
La transcripción de Teams para esta llamada fue tan deficiente (probablemente por audio degradado, acento o ruido de fondo) que el sistema Centauro no pudo extraer evidencias válidas en 4 de los 6 bloques, resultando en una evaluación injusta de "6 MALO". Whisper recuperó el 100% de las evidencias clave, permitiendo una evaluación calibrada (1 BUENO + 5 MEJORABLE) y un coaching accionable.

**Errores Críticos Exclusivos de Teams:**
* **Alucinaciones fonéticas:** Teams generó fragmentos ininteligibles, sílabas aleatorias y pseudo-inglés (ej: *"Baliya"*, *"Mira, I don't like me"*).
* **Impacto en Calificación:** Estas "alucinaciones" provocaron que Centauro calificara bloques como MALO injustamente, asumiendo lenguaje informal o falta de preguntas, cuando en realidad el asesor lo hizo bien (Whisper detectó 3 preguntas y un estilo adecuado).
* **Pérdida de Información:** Teams no capturó la mención del precio (7.700 €), la financiación, ni el próximo paso real acordado en el cierre, limitando el perfilado del lead.

**Bloques con Alto Impacto de Mejora (Teams vs. Whisper):**
* **Investigación:** MALO ➡️ BUENO (Diferencia de 2 niveles. Teams: 0 preguntas; Whisper: 3 preguntas y FDC claro).
* **Propuesta de Valor:** MALO ➡️ MEJORABLE
* **Admisión Económica:** MALO ➡️ MEJORABLE
* **Estilo:** MALO ➡️ MEJORABLE

---

### 👨‍💼 Iván Canale
* **Recomendación:** **INDIFERENTE**
* **Mejora Estimada:** 8%

**Resumen del Caso:**
La transcripción de Teams fue suficientemente legible para capturar los 5 bloques más importantes correctamente. La calificación global fue BUENO en ambos casos. Whisper ofrece un perfil del lead más rico y barreras mejor identificadas.

**Diferencias Clave:**
* **Cierre (Impacto Medio):** Teams perdió la evidencia de una reunión concreta programada, evaluando como MEJORABLE. Whisper la detectó (reunión mañana 10:00), elevando la nota a BUENO.
* **Investigación:** Teams no detectó preguntas explícitas (aunque evaluó BUENO por contexto). Whisper reportó 2 preguntas claras.
* **Contexto:** Whisper identificó barreras reales (precio, fraccionar pago), mientras que Teams no detectó ninguna.

---

### 👨‍💼 Nicolás Uriburu
* **Recomendación:** **TEAMS**
* **Mejora Estimada:** 0%

**Resumen del Caso:**
Teams funcionó de manera excelente. Las calificaciones son **idénticas en los 6 bloques** (2 BUENO + 4 MEJORABLE). Las evidencias extraídas por ambas herramientas son frases completas y coherentes.

**Diferencias Clave:**
* **Estilo (Impacto Bajo):** Whisper captura un error de comunicación más específico y accionable (el asesor confundió sus turnos con los del lead), mientras que Teams detectó una informalidad más genérica.

---

### 👨‍💼 Vicente Spina
* **Recomendación:** **TEAMS**
* **Mejora Estimada:** 0%

**Resumen del Caso:**
Las evidencias citadas son casi idénticas palabra por palabra entre Teams y Whisper, sugiriendo un audio de muy alta calidad. Las calificaciones son **idénticas en los 6 bloques** (1 BUENO + 5 MEJORABLE).

**Diferencias Clave:**
* **Objeciones (Impacto Bajo):** Whisper reconoció correctamente que el asesor usó la técnica de "anticipación" (aunque de forma superficial). Teams no detectó ninguna técnica.

---

## 2. Conclusión Global y Veredicto Final

### 📊 Patrones Observados

* **El Problema de Teams:** Cuando el audio de la llamada es degradado (ruido, VoIP de baja calidad, acentos no estándar, solapamiento), el motor ASR de Teams produce transcripciones con mezcla de idiomas y frases ininteligibles. Centauro, al no encontrar evidencias, colapsa las calificaciones a MALO (falsos negativos).
* **La Ventaja de Whisper:** Produce transcripciones coherentes incluso en condiciones adversas. Las evidencias son siempre legibles, el perfil del lead es detallado y las barreras son precisas.

### 📉 Impacto en Evaluaciones de Ventas
El impacto de usar la transcripción correcta es **ALTO**. Se han documentado 7 cambios de calificación de bloque en solo 4 asesores, incluyendo un salto crítico de MALO a BUENO en el caso de Esther López.

### 💰 Análisis de Costos (Whisper API)
* **Costo total de transcripción:** $1.026 USD
* **Costo incremental por asesor:** $0.257 USD
* *(Nota: El costo de análisis de Centauro es el mismo independientemente del origen de la transcripción).*

### 🏆 Veredicto: WHISPER (Mejora media estimada: 21%)

El ROI de Whisper justifica la inversión, especialmente para evitar evaluaciones injustas debidas a fallos tecnológicos. Un coste de ~$0.30 por llamada transforma una evaluación inservible en coaching accionable.

#### ✅ Condiciones donde Whisper es IMPRESCINDIBLE:
1. Llamadas con audio degradado (ruido, mala conexión, cortes).
2. Asesores/Leads con acentos marcados o jergas regionales.
3. Llamadas con habla rápida, solapamientos o múltiples interlocutores.
4. **Cuando la evaluación impacta directamente en coaching o bonificaciones** (el coste de una evaluación injusta supera con creces los $0.25).
5. En implementaciones a escala sin revisión humana obligatoria de las evidencias.

#### ❌ Condiciones donde Teams es SUFICIENTE:
1. Llamadas con audio limpio, entorno controlado y dicción clara.
2. Si existe un sistema de alerta que detecte transcripciones "ilegibles" (baja observabilidad) antes de la evaluación.
3. Operaciones de altísimo volumen (>500 llamadas/mes) donde el coste acumulado de Whisper sea prohibitivo y se asuma un margen de error por calidad de audio.