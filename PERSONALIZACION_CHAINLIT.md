# 🎨 GUÍA DE PERSONALIZACIÓN DE CHAINLIT

**Versión**: 4.0 | **Fecha**: 26 Enero 2025

---

## 📁 **ESTRUCTURA DE ARCHIVOS**

```
Proyecto_Centauro/
├── .chainlit/
│   └── config.toml       # ← Configuración principal
├── public/               # ← Crear esta carpeta para assets
│   ├── logo_light.png    # Logo para tema claro
│   ├── logo_dark.png     # Logo para tema oscuro
│   ├── favicon.ico       # Ícono del navegador
│   └── avatar.png        # Avatar del chatbot (opcional)
├── app.py
└── chainlit.md           # Página de bienvenida (opcional)
```

---

## 🎨 **1. CAMBIAR COLORES**

### **Archivo**: `.chainlit/config.toml`

```toml
[UI.theme]
primary_color = "#1976D2"  # Color principal (botones, enlaces)

[UI.theme.light]
background = "#F5F7FA"     # Fondo general
paper = "#FFFFFF"          # Fondo de tarjetas/mensajes
primary = "#1976D2"        # Azul corporativo
accent = "#FFDD00"         # Amarillo OBS (destacados)
text_primary = "#212121"   # Texto principal
text_secondary = "#757575" # Texto secundario

[UI.theme.dark]
background = "#1A1A2E"     # Fondo oscuro
paper = "#16213E"          # Tarjetas oscuras
primary = "#42A5F5"        # Azul claro
accent = "#FFE66D"         # Amarillo claro
text_primary = "#FFFFFF"
text_secondary = "#B0BEC5"
```

### **Colores recomendados OBS**:

| Elemento | Color HEX | Uso |
|----------|-----------|-----|
| Azul OBS | `#1976D2` | Primario (botones) |
| Amarillo OBS | `#FFDD00` | Acentos/destacados |
| Gris claro | `#F5F7FA` | Fondo |
| Negro texto | `#212121` | Texto principal |

---

## 🖼️ **2. AÑADIR LOGO PERSONALIZADO**

### **Paso 1: Crear carpeta `public/`**

```bash
mkdir public
```

### **Paso 2: Añadir imágenes**

Coloca tus imágenes en `public/`:

```
public/
├── logo_light.png    # Logo para tema claro (recomendado: 200x50px)
├── logo_dark.png     # Logo para tema oscuro (opcional)
└── favicon.ico       # Ícono de pestaña navegador (16x16px o 32x32px)
```

### **Paso 3: Configurar en `config.toml`**

```toml
[UI]
# Logo que aparece en el sidebar
logo_light = "public/logo_light.png"
logo_dark = "public/logo_dark.png"  # Opcional

# Favicon (ícono de pestaña)
favicon = "public/favicon.ico"

# Avatar del chatbot
[chatbot]
avatar = "public/avatar.png"  # O usar emoji: "🦄"
name = "Centauro"
```

### **Especificaciones de imágenes**:

| Tipo | Tamaño recomendado | Formato |
|------|-------------------|---------|
| Logo sidebar | 200x50px o 300x75px | PNG con fondo transparente |
| Favicon | 16x16px, 32x32px, 64x64px | ICO o PNG |
| Avatar chatbot | 100x100px | PNG circular |

---

## 🎭 **3. CREAR LOGO SIMPLE (SI NO TIENES DISEÑADOR)**

### **Opción A: Usar emoji gigante**

```toml
[chatbot]
avatar = "🦄"  # Unicornio = Centauro
name = "Centauro"
```

### **Opción B: Texto como logo**

Crear imagen PNG con texto "CENTAURO" usando:
- https://www.canva.com (gratis)
- PowerPoint/Google Slides
- Photoshop/GIMP

**Plantilla**:
```
Tamaño: 300x75px
Fondo: Transparente
Texto: "CENTAURO"
Fuente: Arial Black o similar
Color: #1976D2 (azul OBS)
```

### **Opción C: Usar logo de OBS**

Si tienes permiso para usar logo institucional:
1. Exportar logo OBS a PNG transparente
2. Redimensionar a 200x50px
3. Colocar en `public/logo_light.png`

---

## 🎨 **4. PERSONALIZACIÓN AVANZADA**

### **Cambiar fuente**:

Chainlit usa las fuentes del sistema. Para cambiar, necesitas CSS custom:

**Crear**: `public/custom.css`

```css
/* Fuente personalizada */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

body {
    font-family: 'Inter', sans-serif !important;
}

/* Cambiar color de botón primario */
.MuiButton-containedPrimary {
    background-color: #1976D2 !important;
}

/* Personalizar mensajes del chatbot */
.step-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
}
```

**Configurar en `config.toml`**:

```toml
[UI]
custom_css = "public/custom.css"
```

---

## 🔄 **5. APLICAR CAMBIOS**

### **Reiniciar Chainlit**:

```bash
# Detener servidor (Ctrl+C)
# Volver a ejecutar
chainlit run app.py -w
```

**Los cambios en `config.toml` requieren reinicio.**

---

## 📝 **6. EJEMPLOS DE TEMAS**

### **Tema OBS Profesional** (actual):

```toml
[UI.theme.light]
background = "#F5F7FA"
paper = "#FFFFFF"
primary = "#1976D2"  # Azul OBS
accent = "#FFDD00"   # Amarillo OBS
```

### **Tema Oscuro Moderno**:

```toml
[UI.theme.dark]
background = "#0D1117"  # GitHub dark
paper = "#161B22"
primary = "#58A6FF"
accent = "#F78166"
```

### **Tema Minimalista**:

```toml
[UI.theme.light]
background = "#FFFFFF"
paper = "#F9F9F9"
primary = "#000000"
accent = "#666666"
text_primary = "#000000"
text_secondary = "#666666"
```

---

## 🎯 **7. RECOMENDACIONES**

### **Para marca corporativa**:

✅ Usar colores oficiales de OBS
✅ Logo institucional (si hay permiso)
✅ Tema claro profesional
✅ Fuente corporativa

### **Para desarrollo/pruebas**:

✅ Tema oscuro (menos fatiga visual)
✅ Emoji como avatar (rápido)
✅ Colores contrastantes

### **Para producción**:

✅ Logo profesional PNG
✅ Favicon personalizado
✅ Colores accesibles (contraste WCAG)
✅ Tema coherente con branding

---

## 🐛 **TROUBLESHOOTING**

### **Logo no aparece**:

1. Verificar que carpeta `public/` existe
2. Verificar nombre exacto del archivo
3. Verificar permisos de lectura
4. Reiniciar Chainlit

### **Colores no cambian**:

1. Verificar sintaxis TOML (comillas, =)
2. Usar códigos HEX válidos (#RRGGBB)
3. Reiniciar servidor Chainlit
4. Limpiar cache del navegador (Ctrl+F5)

### **CSS custom no se aplica**:

1. Verificar ruta en `config.toml`
2. Verificar sintaxis CSS
3. Usar `!important` si es necesario
4. Inspeccionar con DevTools del navegador (F12)

---

## 📚 **RECURSOS**

### **Generadores de paletas**:

- https://coolors.co - Generar paletas de colores
- https://color.adobe.com - Adobe Color Wheel
- https://mycolor.space - Gradientes y combinaciones

### **Creadores de logo**:

- https://www.canva.com - Diseño gráfico gratis
- https://looka.com - Generador de logos IA
- https://www.freelogodesign.org - Logos gratis

### **Iconos y emojis**:

- https://emojipedia.org - Buscar emojis
- https://www.flaticon.com - Iconos PNG/SVG
- https://favicon.io - Generador de favicons

---

## ✅ **CHECKLIST DE PERSONALIZACIÓN**

- [ ] Cambiar `name` a "Centauro v4.0" en config.toml
- [ ] Ajustar `primary_color` al color corporativo
- [ ] Crear carpeta `public/`
- [ ] Añadir logo (`logo_light.png`)
- [ ] Añadir favicon (`favicon.ico`)
- [ ] Configurar avatar del chatbot
- [ ] Probar tema claro y oscuro
- [ ] Verificar en navegadores (Chrome, Firefox)
- [ ] Documentar colores usados

---

**Última actualización**: 26 Enero 2025
**Versión Chainlit**: 1.0+
