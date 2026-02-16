from fpdf import FPDF
from .config import settings

# --- PALETA DE COLORES (Estilo Corporativo Moderno) ---
COLOR_PRIMARY = (0, 0, 0)          # Negro
COLOR_ACCENT = (255, 221, 0)       # Amarillo OBS #FFDD00
COLOR_BG_LIGHT = (245, 245, 245)   # Gris muy claro
COLOR_TEXT_MAIN = (0, 0, 0)
COLOR_TEXT_MUTED = (120, 120, 120)

# Semáforo de Notas (1-5)
COLOR_BAD = (220, 53, 69)     # Rojo (Nota 1-2)
COLOR_MID = (255, 193, 7)     # Amarillo (Nota 3)
COLOR_GOOD = (40, 167, 69)    # Verde (Nota 4-5)
COLOR_NEUTRAL = (108, 117, 125)# Gris (Off Record)

def to_latin1(text):
    if text is None: return ""
    text = str(text)
    text = text.replace("€", "EUR").replace("“", '"').replace("”", '"').replace("’", "'")
    return text.encode("latin-1", "replace").decode("latin-1")

class ModernReport(FPDF):
    def fit_text_cell(self, width, height, text, font_family='Helvetica', style='', max_size=12, min_size=8, align='L'):
        """
        Ajusta automáticamente el tamaño de fuente para que una línea de texto quepa en el ancho dado.
        """
        text = to_latin1(text)
        font_size = max_size
        self.set_font(font_family, style, font_size)
        while font_size > min_size and self.get_string_width(text) > width:
            font_size -= 0.5
            self.set_font(font_family, style, font_size)
        self.cell(width, height, text, 0, 0, align)

    def header(self):
        # Banda superior
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(0, 0, 210, 25, 'F')
        
        # Título
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 8)
        self.fit_text_cell(190, 8, 'CENTAURO AUDIT | Sales Coaching Report', font_family='Helvetica', style='B', max_size=16, min_size=10, align='L')
        
        # Subtítulo
        self.set_xy(10, 16)
        self.fit_text_cell(190, 5, 'Evaluación de Calidad Venta Consultiva (V15.1)', font_family='Helvetica', style='', max_size=10, min_size=8, align='L')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(*COLOR_TEXT_MUTED)
        self.cell(0, 10, f'Página {self.page_no()} | OBS Business School', 0, 0, 'C')

    def get_score_color(self, calificacion):
        if calificacion == "BUENO":    return COLOR_GOOD
        if calificacion == "MEJORABLE": return COLOR_MID
        if calificacion == "MALO":     return COLOR_BAD
        return COLOR_NEUTRAL

    def draw_badge(self, texto, color_rgb):
        """Dibuja una etiqueta de color."""
        self.set_fill_color(*color_rgb)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 8)
        width = self.get_string_width(texto) + 6
        self.rect(self.get_x(), self.get_y(), width, 6, 'F')
        self.cell(width, 6, texto, 0, 0, 'C')
        self.ln(8)

    def draw_block_card(self, bloque):
        """Dibuja la tarjeta de evaluación de un bloque específico."""
        start_y = self.get_y()
        
        # Salto de página inteligente
        if start_y > 240:
            self.add_page()
            start_y = self.get_y()

        # Datos del bloque
        nombre = bloque.get('bloque', 'Bloque Desconocido')
        calificacion = bloque.get('calificacion')
        razon = bloque.get('razonamiento', '')
        evidencia = bloque.get('evidencia_principal', '')
        accion = bloque.get('recomendacion_accionable', '')
        hallazgos = bloque.get('hallazgos_del_lead', {}) or bloque.get('metadata', {}).get('hallazgos_del_lead', {})

        # Color según calificación ordinal
        score_color = self.get_score_color(calificacion)
        texto_cal = calificacion if calificacion is not None else "N/A"

        # 1. Barra lateral de estado
        self.set_fill_color(*score_color)
        self.rect(10, start_y, 2, 35, 'F') # Altura mínima

        # 2. Título del Bloque y Calificación
        self.set_xy(15, start_y)
        self.set_text_color(*COLOR_PRIMARY)
        self.fit_text_cell(140, 8, nombre, font_family='Helvetica', style='B', max_size=12, min_size=8, align='L')

        # Badge de Calificación a la derecha
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(*score_color)
        self.cell(0, 8, texto_cal, 0, 1, 'R')
        
        # 3. Razonamiento (Feedback)
        self.set_x(15)
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*COLOR_TEXT_MAIN)
        self.multi_cell(0, 5, to_latin1(razon))
        self.ln(2)

        # 4. Evidencia (Cita) - Fondo gris
        if evidencia and "NO_OBSERVABLE" not in evidencia:
            self.set_x(15)
            self.set_fill_color(240, 240, 240)
            self.set_font('Helvetica', 'I', 9)
            self.set_text_color(80, 80, 80)
            self.multi_cell(0, 5, to_latin1(f'"{evidencia}"'), border=0, fill=True)
            self.ln(2)

        # 5. Hallazgos clave en Investigación
        if str(nombre).strip().lower() == "investigación" or str(nombre).strip().lower() == "investigacion":
            factor_compra = hallazgos.get("factor_de_compra", "")
            inversion_esperada = hallazgos.get("inversion_esperada", "")
            competidores = hallazgos.get("competidores", "")
            motivacion_principal = hallazgos.get("motivacion_principal", "")

            if factor_compra or inversion_esperada or competidores or motivacion_principal:
                self.set_x(15)
                self.set_fill_color(248, 248, 248)
                self.set_draw_color(225, 225, 225)
                self.set_x(18)
                self.set_font('Helvetica', 'B', 9)
                self.set_text_color(*COLOR_PRIMARY)
                self.cell(0, 5, to_latin1("Hallazgos clave (Investigación)"), 0, 1, fill=True)

                self.set_x(18)
                self.set_font('Helvetica', 'B', 9)
                self.cell(38, 5, to_latin1("Factor de compra:"), 0, 0, fill=True)
                self.set_font('Helvetica', '', 9)
                self.multi_cell(139, 5, to_latin1(factor_compra or "No detectado"), fill=True)

                self.set_x(18)
                self.set_font('Helvetica', 'B', 9)
                self.cell(38, 5, to_latin1("Inversión esperada:"), 0, 0, fill=True)
                self.set_font('Helvetica', '', 9)
                self.multi_cell(139, 5, to_latin1(inversion_esperada or "No explorada"), fill=True)

                self.set_x(18)
                self.set_font('Helvetica', 'B', 9)
                self.cell(38, 5, to_latin1("Competidores:"), 0, 0, fill=True)
                self.set_font('Helvetica', '', 9)
                self.multi_cell(139, 5, to_latin1(competidores or "No explorados"), fill=True)

                self.set_x(18)
                self.set_font('Helvetica', 'B', 9)
                self.cell(38, 5, to_latin1("Motivación principal:"), 0, 0, fill=True)
                self.set_font('Helvetica', '', 9)
                self.multi_cell(139, 5, to_latin1(motivacion_principal or "No detectada"), fill=True)
                self.ln(2)

        # 6. Recomendación (Acción) - Si calificación es MALO, MEJORABLE o N/A
        if accion and calificacion in ("MALO", "MEJORABLE", None):
            self.set_x(15)
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(*COLOR_ACCENT) # Amarillo OBS para resaltar acción
            # Ponemos fondo negro al texto amarillo para legibilidad o usamos color oscuro
            self.set_text_color(100, 80, 0) # Ocre oscuro para leerse bien sobre blanco
            self.multi_cell(0, 5, to_latin1(f"💡 COACHING: {accion}"))

        self.ln(5)
        # Línea separadora
        self.set_draw_color(220, 220, 220)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

def generar_pdf(reporte_json, output_filename):
    # Convertir a dict si es un objeto Pydantic
    if hasattr(reporte_json, 'model_dump'):
        data = reporte_json.model_dump()
    else:
        data = reporte_json

    pdf = ModernReport()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # --- DASHBOARD SUPERIOR ---
    pdf.set_y(30)
    
    # 1. Calificación Global (Cuadro Grande con etiqueta)
    cal_global = data.get('calificacion_global')
    color_global = pdf.get_score_color(cal_global)
    texto_global = cal_global if cal_global else "N/A"

    pdf.set_fill_color(*color_global)
    pdf.rect(10, 30, 50, 40, 'F')

    pdf.set_xy(10, 43)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(50, 10, texto_global, 0, 1, 'C')
    
    # 2. Datos Asesor y Contexto
    pdf.set_xy(65, 30)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.set_font('Helvetica', 'B', 12)
    asesor = data.get('asesor', 'Asesor OBS')
    pdf.multi_cell(135, 6, to_latin1(f"Asesor: {asesor}"))
    
    y_contexto = max(pdf.get_y() + 1, 42)
    pdf.set_xy(65, y_contexto)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*COLOR_TEXT_MAIN)
    
    ctx = data.get('resumen_contextual', {})
    resumen_texto = (
        f"Perfil Lead: {ctx.get('perfil_lead', 'N/A')}\n"
        f"Objetivo: {ctx.get('objetivo_del_lead', 'N/A')}\n"
        f"Resultado: {ctx.get('resultado_general', 'N/A')}"
    )
    pdf.multi_cell(0, 5, to_latin1(resumen_texto))
    
    pdf.ln(15)

    # --- SECCIÓN: EVALUACIÓN DETALLADA ---
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 10, "Desglose por Bloques (Técnica de Venta)", 0, 1)
    pdf.ln(2)
    
    bloques = data.get('evaluacion_por_bloques', [])
    for bloque in bloques:
        pdf.draw_block_card(bloque)
        
    # Guardar
    pdf_dir = settings.OUTPUTS_DIR / "Reportes_PDF"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / output_filename
    pdf.output(str(pdf_path))
    print(f"🎨 PDF Generado Exitosamente: {pdf_path}")
