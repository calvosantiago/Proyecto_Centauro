# 🦄 Centauro v3.0 - Interfaz Chainlit

## 🚀 Inicio Rápido

### Opción 1: Windows (Doble clic)
```
Doble clic en: start_chainlit.bat
```

### Opción 2: Terminal
```bash
# 1. Instalar dependencias (solo primera vez)
pip install -r requirements.txt

# 2. Iniciar servidor
chainlit run app.py -w
```

El navegador se abrirá automáticamente en: **http://localhost:8000**

---

## 📁 Estructura de Archivos

```
Proyecto_Centauro/
├── app.py                 # 🆕 Interfaz Chainlit principal
├── chainlit.md            # Página de bienvenida
├── .chainlit/
│   └── config.toml        # Configuración UI (colores, tema)
├── start_chainlit.bat     # Script de inicio rápido (Windows)
├── main.py                # CLI original (mantener para scripts batch)
└── centauro/              # Tu código existente
```

---

## 🎯 Cómo Usar

### 1️⃣ **Subir Transcripción**
Arrastra o sube un archivo:
- `.txt` - Texto plano
- `.vtt` - Formato WebVTT (Teams, Zoom)
- `.docx` - Documento Word (Teams)

### 2️⃣ **Esperar Análisis**
El sistema ejecutará 4 fases en ~1-2 minutos:
- 🛡️ FASE 0: Protección de datos (RGPD)
- 🎙️ FASE 1: Diarización (ASESOR/LEAD)
- 🧠 FASE 2: RAG Dinámico (contexto)
- 🤖 FASE 3: Multi-Agente (6 bloques)
- 🛡️ FASE 3.5: Sheriff (anti-alucinaciones)
- 🎨 FASE 4: Síntesis + PDF

### 3️⃣ **Descargar Reporte**
- **Vista en pantalla:** Nota global + desglose
- **PDF descargable:** Reporte completo profesional
- **JSON técnico:** `outputs/Reportes_JSON/`

---

## ⚙️ Configuración

### Cambiar colores (Branding OBS)
Edita `.chainlit/config.toml`:

```toml
[UI.theme]
primary_color = "#FFDD00"  # Amarillo OBS
background_color = "#FFFFFF"
```

### Habilitar modo oscuro
Por defecto Chainlit detecta el modo del sistema. Puedes forzarlo en `config.toml`.

### Cambiar puerto
```bash
chainlit run app.py -w --port 8080
```

---

## 🔧 Solución de Problemas

### "Module 'chainlit' not found"
```bash
pip install chainlit
```

### "Port 8000 already in use"
```bash
# Cerrar proceso en puerto 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# O usar otro puerto
chainlit run app.py -w --port 8080
```

### Error de encoding en archivos
Chainlit espera UTF-8. Si tienes problemas:
1. Abre el `.txt` en Notepad++
2. Codificación → Convertir a UTF-8
3. Guardar

---

## 📊 Comparativa: CLI vs Chainlit

| Característica | `main.py` (CLI) | `app.py` (Chainlit) |
|----------------|-----------------|---------------------|
| **UX** | Terminal | Interfaz web visual |
| **Progreso** | Texto plano | Steps visuales |
| **Descarga PDF** | Carpeta local | Botón descarga |
| **Múltiples usuarios** | ❌ Batch secuencial | ✅ Sesiones paralelas |
| **Uso recomendado** | Scripts automáticos | Evaluación interactiva |

---

## 🎨 Personalización Avanzada

### Añadir logo
1. Crear carpeta `public/`
2. Añadir `logo.png`
3. En `chainlit.md` añadir:
   ```markdown
   ![Logo](public/logo.png)
   ```

### Autenticación (Futuro)
Chainlit soporta autenticación. Ver docs:
https://docs.chainlit.io/authentication/overview

---

## 🚀 Próximas Mejoras

- [ ] Historial de evaluaciones por asesor
- [ ] Comparativa asesor vs promedio del equipo
- [ ] Dashboard con gráficos (evolución temporal)
- [ ] Exportación batch (múltiples archivos)
- [ ] Integración con CRM (API REST)

---

## 📞 Soporte

**Equipo BI & Analytics OBS**

- **Versión:** 3.0
- **Última actualización:** Enero 2025
- **Tech Stack:** Python 3.10+ | Chainlit | OpenAI GPT-4o-mini
