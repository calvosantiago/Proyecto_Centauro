# 📁 Carpeta PUBLIC - Assets de Chainlit

Esta carpeta contiene los assets visuales para personalizar Chainlit.

## 🖼️ CÓMO AÑADIR TU LOGO

### Paso 1: Preparar el logo

Coloca tu logo PNG (con fondo transparente) en esta carpeta con el nombre:
```
logo.png
```

**Especificaciones recomendadas:**
- Formato: PNG con fondo transparente
- Tamaño: 200x50px o 300x75px
- Colores: Compatible con tema oscuro (gris #2B2D2F)

### Paso 2: Activar en config.toml

Edita `.chainlit/config.toml` y descomenta estas líneas (líneas ~42-44):

```toml
# Logo personalizado (descomenta cuando tengas el archivo)
logo_dark = "public/logo.png"   # ← DESCOMENTAR (quitar el #)
logo_light = "public/logo.png"  # ← DESCOMENTAR (quitar el #)
favicon = "public/favicon.ico"  # ← DESCOMENTAR si tienes favicon
```

### Paso 3: Reiniciar Chainlit

```bash
# Detener con Ctrl+C
# Volver a ejecutar
chainlit run app.py -w
```

El logo aparecerá en la esquina superior izquierda del sidebar.

---

## 🎨 COLORES ACTUALES

**Tema Oscuro (por defecto):**
- Fondo principal: Gris plomo oscuro (#2B2D2F)
- Tarjetas/mensajes: Gris un poco más claro (#3A3C3E)
- Color primario: Amarillo OBS (#FFDD00) - botones, enlaces
- Texto: Blanco (#FFFFFF)
- Texto secundario: Gris claro (#B0B0B0)

**Cambiar a tema claro:**
En `.chainlit/config.toml` línea ~40, cambiar:
```toml
default_theme = "light"  # en lugar de "dark"
```

---

## 📝 ARCHIVOS OPCIONALES

Puedes añadir también:

### Favicon (ícono de pestaña del navegador)
```
public/favicon.ico
```
- Formato: ICO o PNG
- Tamaño: 16x16px, 32x32px o 64x64px

### Avatar del chatbot
Si prefieres imagen en lugar de emoji 🦄:
```
public/avatar.png
```
- Formato: PNG circular o cuadrado
- Tamaño: 100x100px

Luego en `app.py`, buscar donde está el welcome message y cambiar el avatar.

---

**Última actualización**: 26 Enero 2025
