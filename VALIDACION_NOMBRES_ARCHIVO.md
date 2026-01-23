# 🔍 Sistema de Validación de Nombres de Archivo

## 🎯 Objetivo

Detectar y reportar nombres de archivo demasiado largos **ANTES** de que causen errores, con mensajes claros tanto en terminal como en Chainlit.

---

## ✅ ¿Qué se implementó?

### **1. Módulo de validaciones** (`centauro/utils/validaciones.py`)

Funciones centralizadas para validar archivos:

- `validar_nombre_archivo()` - Verifica longitud de nombre y path
- `validar_archivo_para_procesamiento()` - Validación completa (existe, extensión, tamaño, longitud)
- `generar_mensaje_error_usuario()` - Genera mensajes amigables

### **2. Validación en procesador de buenas prácticas**

`centauro/tools/procesar_buenas_practicas.py` ahora valida ANTES de procesar:

```
❌ ERROR: Nombre de archivo demasiado largo
   Archivo: OBS Business School- Entrevista a Juan Jose Adames Máster de Formación...
   Longitud: 120 caracteres
   Máximo recomendado: 100 caracteres
   Acción: Renombra el archivo a algo más corto
   Ejemplo: OBS_Juan_Adames_ejemplo.vtt
```

### **3. Validación en main.py**

Valida archivos cuando se analizan desde línea de comandos.

### **4. Validación en Chainlit** (`app.py`)

**CRÍTICO**: Muestra mensajes claros al usuario en la interfaz web.

---

## 📊 Límites establecidos:

| Tipo | Límite | Razón |
|------|--------|-------|
| **Nombre de archivo** | 100 caracteres | Windows tiene problemas con nombres >150 |
| **Path completo** | 240 caracteres | Límite de Windows es 260 |

---

## 🔍 ¿Cuándo se valida?

### **1. Al procesar ejemplos de buenas prácticas:**

```bash
python -m centauro.tools.procesar_buenas_practicas
```

**Output:**
```
📚 Encontrados 37 ejemplos para procesar
============================================================

❌ ERROR: Nombre de archivo demasiado largo
   Archivo: OBS Business School- Entrevista a Juan Jose Adames Máster de Formación...
   Longitud: 120 caracteres
   Máximo recomendado: 100 caracteres
   Acción: Renombra el archivo a algo más corto
   Ejemplo: Juan_Adames_RRHH.vtt

📄 Procesando: ejemplo_corto.vtt [Investigación]
   ✅ Procesado: 5 patrones detectados
```

### **2. Al analizar conversaciones (main.py):**

```bash
python main.py --archivo inputs/transcripts/archivo_muy_largo.vtt
```

**Output:**
```
============================================================
⚠️ **Error en análisis de conversación**

❌ ERROR: Nombre de archivo demasiado largo
   Archivo: OBS_Business_School_Entrevista_a_Geraldine_Manriquez...
   Longitud: 115 caracteres
   Máximo permitido: 100 caracteres

💡 Sugerencia: Renombra el archivo a algo más corto
   Ejemplo: Geraldine_Manriquez_MBA.vtt

---
**¿Necesitas ayuda?**
Contacta al equipo técnico si el problema persiste.
============================================================
```

### **3. Al subir archivo en Chainlit:**

Usuario sube archivo con nombre largo → Ve este mensaje en la interfaz:

```
⚠️ **Error en análisis de conversación**

❌ ERROR: Nombre de archivo demasiado largo
   Archivo: OBS Business School- Entrevista a Juan Jose Adames Máster...
   Longitud: 120 caracteres
   Máximo permitido: 100 caracteres

💡 Sugerencia: Renombra el archivo a algo más corto
   Ejemplo: Juan_Adames_RRHH.vtt

---
**¿Necesitas ayuda?**
Contacta al equipo técnico si el problema persiste.
```

---

## 🛠️ Uso en código:

### **Validación básica:**

```python
from centauro.utils import validar_nombre_archivo
from pathlib import Path

archivo = Path("archivo_muy_largo.vtt")
validacion = validar_nombre_archivo(archivo)

if not validacion:
    print(validacion.mensaje)
    print(validacion.sugerencia)
```

### **Validación completa:**

```python
from centauro.utils import validar_archivo_para_procesamiento

archivo = Path("conversacion.vtt")
validacion = validar_archivo_para_procesamiento(archivo)

if validacion:
    # Archivo válido, procesar
    procesar(archivo)
else:
    # Archivo inválido, mostrar error
    print(validacion.mensaje)
    print(validacion.sugerencia)
```

### **Generar mensaje para usuario:**

```python
from centauro.utils import generar_mensaje_error_usuario

if not validacion:
    mensaje = generar_mensaje_error_usuario(validacion, "procesamiento de ejemplos")
    print(mensaje)
    # O en Chainlit:
    await cl.Message(content=mensaje).send()
```

---

## ✅ Beneficios:

### **Antes (sin validación):**
```
❌ Archivo procesa → Error al guardar → Crash del script
❌ Usuario confundido: "¿Por qué falló?"
❌ Difícil de debuggear
```

### **Ahora (con validación):**
```
✅ Validación ANTES de procesar → Mensaje claro → Usuario sabe qué hacer
✅ No hay crashes inesperados
✅ Mensajes específicos con sugerencias
```

---

## 📝 Ejemplos de mensajes:

### **1. Nombre muy largo:**
```
❌ ERROR: Nombre de archivo demasiado largo
   Archivo: OBS Business School Máster Executive MBA...
   Longitud: 115 caracteres
   Máximo permitido: 100 caracteres

💡 Sugerencia: Renombra el archivo a algo más corto
   Ejemplo: MBA_Executive_Geraldine.vtt
```

### **2. Path muy largo:**
```
❌ ERROR: Path completo demasiado largo
   Archivo: ejemplo.vtt
   Path: C:\Users\...\muy\largo\...
   Longitud: 265 caracteres
   Límite Windows: 260 caracteres

💡 Sugerencia: Renombra el archivo O mueve la carpeta del proyecto
   - Opción 1: Renombrar archivo más corto
   - Opción 2: Mover proyecto a C:\Centauro\ (path más corto)
```

### **3. Archivo vacío:**
```
❌ ERROR: El archivo está vacío
   Archivo: conversacion.vtt

💡 Verifica que el archivo tenga contenido
```

### **4. Extensión inválida:**
```
❌ ERROR: Extensión no soportada: .mp3
   Archivo: grabacion.mp3

💡 Extensiones válidas: .vtt, .txt, .docx
```

---

## 🚀 Testing:

### **Test 1: Archivo con nombre corto (válido)**
```bash
python -c "from centauro.utils import validar_nombre_archivo; from pathlib import Path; print('✅ Válido' if validar_nombre_archivo(Path('ejemplo.vtt')) else '❌ Inválido')"
```

**Output esperado:** `✅ Válido`

### **Test 2: Archivo con nombre largo (inválido)**
```bash
python -c "from centauro.utils import validar_nombre_archivo; from pathlib import Path; v = validar_nombre_archivo(Path('OBS Business School - Máster Executive MBA - Entrevista a Geraldine Manríquez Plaza sobre programa de formación y desarrollo profesional.vtt')); print(v.mensaje if not v else 'OK')"
```

**Output esperado:** Mensaje de error con sugerencia

---

## 📁 Archivos modificados/creados:

1. ✅ **Nuevo:** `centauro/utils/validaciones.py` - Módulo de validaciones
2. ✅ **Nuevo:** `centauro/utils/__init__.py` - Exports del módulo
3. ✅ **Modificado:** `centauro/tools/procesar_buenas_practicas.py` - Validación al procesar
4. ✅ **Modificado:** `main.py` - Validación al analizar
5. ✅ **Modificado:** `app.py` - Validación en Chainlit

---

## 🔄 Flujo de validación:

```
Usuario sube archivo "nombre_muy_largo.vtt"
              ↓
    validar_archivo_para_procesamiento()
              ↓
    ¿Nombre > 100 chars?  → SÍ
              ↓
    generar_mensaje_error_usuario()
              ↓
    Mostrar mensaje en Chainlit / Terminal
              ↓
    Usuario ve: "ERROR: Nombre demasiado largo"
                "Sugerencia: Renombrar a ejemplo.vtt"
              ↓
    Usuario renombra archivo
              ↓
    Vuelve a subir → ✅ Procesamiento exitoso
```

---

## 💡 Buenas prácticas para nombres:

### ✅ Buenos nombres (< 50 chars):
- `Juan_Perez_MBA.vtt`
- `Maria_Marketing_Digital.vtt`
- `Carlos_Cierre_202501.vtt`

### ⚠️ Nombres aceptables (50-100 chars):
- `Entrevista_Geraldine_Manriquez_MBA_Executive_OBS.vtt`

### ❌ Nombres problemáticos (> 100 chars):
- `OBS Business School - Máster Executive MBA - Entrevista a Geraldine Manríquez Plaza sobre programa de formación.vtt`

---

## 🐛 Troubleshooting:

### **Error: "ModuleNotFoundError: No module named 'centauro.utils'"**

**Solución:** El módulo aún no está en tu instalación. Ejecuta:
```bash
python -c "import centauro.utils; print('OK')"
```

Si falla, verifica que `centauro/utils/__init__.py` exista.

### **Error persiste después de renombrar:**

1. Verifica que el archivo realmente se renombró (no solo en una copia)
2. Cierra y vuelve a abrir Chainlit
3. Verifica que el path completo sea < 240 caracteres

---

**Versión:** 1.0
**Fecha:** 2025-01-23
**Estado:** ✅ Implementado y probado
