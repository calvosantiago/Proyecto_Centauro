# 📝 Instrucciones para Procesar Ejemplos

## ⚠️ Problemas detectados en tu procesamiento:

### 1. **Archivos duplicados**
Tienes el mismo archivo .vtt en múltiples carpetas:
- `Maria Jose Godoy - Dirección de Comunicación Corporativa- NEREA OCON.vtt`
  - Aparece en: admision_economica/, cierre_proximos_pasos/, investigacion/, objeciones/, propuesta_valor/

**Solución:** Decide en QUÉ carpeta va cada archivo. Un ejemplo solo puede estar en UNA sección.

### 2. **Nombres de archivo muy largos**
Algunos archivos superan el límite de Windows (260 caracteres):
- `OBS Business School- Entrevista a Juan Jose Adames Máster de Formación Permanente en Dirección de Recursos Humanos y Gestión del Talento.vtt` (209 chars)

**Solución:** Renombra a nombres más cortos ANTES de procesar:
```
OBS_Juan_Jose_Adames_RRHH.vtt
```

---

## ✅ Pasos para procesar correctamente:

### **Paso 1: Limpiar archivos duplicados**

Revisa cada carpeta y **elimina duplicados**. Cada .vtt debe estar SOLO en la carpeta que mejor represente su contenido:

```
¿"Maria Jose Godoy" es principalmente sobre...?
- Investigación → investigacion/
- Admisión → admision_economica/
- Cierre → cierre_proximos_pasos/
- Objeciones → objeciones/
- Propuesta de valor → propuesta_valor/
```

### **Paso 2: Renombrar archivos largos**

Renombra archivos con más de 100 caracteres a nombres cortos y descriptivos:

**ANTES:**
```
OBS Business School- Entrevista a Juan Jose Adames Máster de Formación Permanente en Dirección de Recursos Humanos y Gestión del Talento.vtt
```

**DESPUÉS:**
```
Juan_Adames_RRHH.vtt
```

El contenido del archivo sigue siendo el mismo, solo cambia el nombre.

---

### **Paso 3: Ejecutar el procesador**

#### **Opción A: Usar el script .bat (Recomendado)**
```bash
procesar_ejemplos.bat
```

#### **Opción B: Manualmente**
```bash
# 1. Activar entorno virtual
.venv\Scripts\activate

# 2. Verificar mapeo
python -m centauro.tools.mapeo_secciones

# 3. Procesar ejemplos
python -m centauro.tools.procesar_buenas_practicas
```

---

### **Paso 4: Verificar resultados**

Deberías ver algo como:

```
📚 Encontrados 35 ejemplos para procesar
============================================================

📄 Procesando: Juan_Adames_RRHH.vtt [Admisión y propuesta económica]
   ✅ Procesado: 5 patrones detectados

...

============================================================
✅ Procesados 35 ejemplos

📤 Exportando 35 ejemplos para RAG...
   💾 admision_economica_ejemplo_001.txt
   💾 admision_economica_ejemplo_002.txt
   💾 cierre_proximos_pasos_ejemplo_001.txt
   ...

✅ Exportación completada en: inputs\docs\buenas_practicas
```

**✅ Nombres de archivo CORTOS y sin problemas**

---

### **Paso 5: Re-indexar el RAG**

```bash
python main.py
```

---

## 🔍 Verificaciones finales:

### **Verificar que no hay duplicados:**
```bash
# Buscar archivos con el mismo nombre en diferentes carpetas
cd inputs/buenas_practicas
for /r %f in (*.vtt) do @echo %~nxf | sort
```

Si ves nombres repetidos → elimina los duplicados

### **Verificar longitud de nombres:**
```bash
# Ver archivos con nombres muy largos
for /r %f in (*.vtt) do @if %~zf GTR 100 echo %f
```

Si alguno es > 100 chars → renómbralo

---

## 💡 Consejos para nombres de archivo:

### ✅ Buenos nombres:
- `Juan_Perez_MBA.vtt` (corto, descriptivo)
- `Maria_Marketing_Digital.vtt`
- `Carlos_Cierre_Efectivo.vtt`

### ❌ Malos nombres:
- `OBS Business School - Máster Executive MBA - Entrevista a Geraldine Manríquez Plaza.vtt` (muy largo)
- `Meeting Recording - 2024-01-15.vtt` (no descriptivo)
- `archivo (1).vtt` (sin contexto)

---

## 🚨 Si algo falla:

1. **Error de path demasiado largo:**
   - Renombra el archivo .vtt a un nombre más corto
   - Mueve las carpetas a un path más corto (ej: C:\Centauro\)

2. **Error de duplicados:**
   - Decide en qué carpeta va cada archivo
   - Elimina el archivo de las otras carpetas

3. **Error de encoding:**
   - Asegúrate que los .vtt estén en UTF-8
   - Abre con Notepad++ y cambia encoding si es necesario

---

## 📊 Resumen de tu situación actual:

- ✅ 35 ejemplos procesados exitosamente
- ⚠️ 2 archivos fallaron (path demasiado largo)
- ⚠️ ~5-6 archivos duplicados entre carpetas

**Acción recomendada:**
1. Revisa los duplicados y decide dónde va cada uno
2. Renombra los 2 archivos que fallaron
3. Vuelve a ejecutar el procesador
4. Re-indexa el RAG

---

**Última actualización:** 2025-01-23
