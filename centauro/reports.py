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
    def header(self):
        # Banda superior
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(0, 0, 210, 25, 'F')
        
        # Título
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 8)
        self.cell(0, 10, 'CENTAURO AUDIT | Sales Coaching Report', 0, 0, 'L')
        
        # Subtítulo
        self.set_font('Helvetica', '', 10)
        self.set_xy(10, 16)
        self.cell(0, 5, 'Evaluación de Calidad Venta Consultiva (V15.1)', 0, 0, 'L')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(*COLOR_TEXT_MUTED)
        self.cell(0, 10, f'Página {self.page_no()} | OBS Business School', 0, 0, 'C')

    def get_score_color(self, score):
        if score is None: return COLOR_NEUTRAL
        if score >= 4: return COLOR_GOOD
        if score >= 3: return COLOR_MID
        return COLOR_BAD

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
        nota = bloque.get('puntuacion_1_5')
        razon = bloque.get('razonamiento', '')
        evidencia = bloque.get('evidencia_principal', '')
        accion = bloque.get('recomendacion_accionable', '')
        
        # Color según nota
        score_color = self.get_score_color(nota)
        texto_nota = f"{nota}/5" if nota is not None else "N/A"
        
        # 1. Barra lateral de estado
        self.set_fill_color(*score_color)
        self.rect(10, start_y, 2, 35, 'F') # Altura mínima
        
        # 2. Título del Bloque y Nota
        self.set_xy(15, start_y)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(*COLOR_PRIMARY)
        self.cell(140, 8, to_latin1(nombre), 0, 0)
        
        # Badge de Nota a la derecha
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(*score_color)
        self.cell(0, 8, texto_nota, 0, 1, 'R')
        
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

        # 5. Recomendación (Acción) - Si la nota es baja
        if accion and (nota is None or nota < 5):
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
    
    # 1. Nota Global (Círculo/Cuadro Grande)
    nota_global = data.get('puntuacion_global_1_5', 0)
    color_global = pdf.get_score_color(nota_global)
    
    pdf.set_fill_color(*color_global)
    pdf.rect(10, 30, 40, 40, 'F')
    
    pdf.set_xy(10, 40)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 26)
    pdf.cell(40, 10, f"{nota_global}", 0, 1, 'C')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(10, 52)
    pdf.cell(40, 5, "/ 5.0", 0, 0, 'C')
    
    # 2. Datos Asesor y Contexto
    pdf.set_xy(55, 30)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.set_font('Helvetica', 'B', 14)
    asesor = data.get('asesor', 'Asesor OBS')
    pdf.cell(0, 8, to_latin1(f"Asesor: {asesor}"), 0, 1)
    
    pdf.set_xy(55, 40)
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
        
    # --- SECCIÓN: FEEDBACK RESUMIDO (Solo Áreas de Mejora) ---
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 10, "Plan de Accion & Coaching", 0, 1)
    pdf.ln(5)

    fb = data.get('feedback_resumido', {})

    # Áreas de Mejora (CRÍTICO: Texto completo sin cortar)
    pdf.set_fill_color(255, 230, 230) # Rojo claro fondo
    pdf.rect(10, pdf.get_y(), 190, 8, 'F')
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*COLOR_BAD)
    pdf.cell(0, 8, "  ÁREAS DE MEJORA (Action Plan)", 0, 1)
    pdf.ln(2)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*COLOR_TEXT_MAIN)
    for m in fb.get('areas_mejora', []):
        # Indent inicial
        pdf.set_x(15)
        # Usar multi_cell para texto largo sin cortar
        pdf.multi_cell(0, 5, to_latin1(f"• {m}"))
        pdf.ln(1)  # Espacio entre ítems
        
    # Guardar
    pdf_dir = settings.OUTPUTS_DIR / "Reportes_PDF"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / output_filename
    pdf.output(str(pdf_path))
    print(f"🎨 PDF Generado Exitosamente: {pdf_path}")