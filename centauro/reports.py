from fpdf import FPDF
from .config import settings

# --- PALETA DE COLORES (Estilo Corporativo Moderno) ---
COLOR_PRIMARY = (44, 62, 80)      # Azul Oscuro (Midnight Blue)
COLOR_ACCENT = (52, 152, 219)     # Azul Brillante (Peter River)
COLOR_BG_LIGHT = (236, 240, 241)  # Gris muy claro (Clouds)
COLOR_TEXT_MAIN = (44, 62, 80)
COLOR_TEXT_MUTED = (127, 140, 141)

# Semáforo
COLOR_SUCCESS = (39, 174, 96)     # Verde (Nephritis)
COLOR_WARNING = (243, 156, 18)    # Naranja (Orange)
COLOR_DANGER = (192, 57, 43)      # Rojo (Pomegranate)

class ModernReport(FPDF):
    def header(self):
        # Banda superior de color
        self.set_fill_color(*COLOR_PRIMARY)
        self.rect(0, 0, 210, 25, 'F')
        
        # Título del Reporte (Blanco)
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 8)
        self.cell(0, 10, 'CENTAURO AUDIT | Reporte de Calidad', 0, 0, 'L')
        
        # Subtítulo (ej: Fecha o Versión)
        self.set_font('Helvetica', '', 10)
        self.set_xy(10, 16)
        self.cell(0, 5, 'Análisis Automático Supervisado (Sheriff v4.1)', 0, 0, 'L')
        
        self.ln(20) # Espacio tras el header

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(*COLOR_TEXT_MUTED)
        self.cell(0, 10, f'Página {self.page_no()} | Generado por Proyecto Centauro', 0, 0, 'C')

    def draw_badge(self, texto, tipo="MEDIA", x=None, y=None):
        """Dibuja una etiqueta tipo 'Badge' (Pill shape)."""
        if x is None: x = self.get_x()
        if y is None: y = self.get_y()
        
        # Colores del badge
        if tipo == "CRITICO": bg = COLOR_DANGER
        elif tipo == "ALTA": bg = COLOR_WARNING
        elif tipo == "BAJA": bg = COLOR_TEXT_MUTED
        else: bg = COLOR_ACCENT # MEDIA
        
        self.set_fill_color(*bg)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 7)
        
        # Ancho dinámico
        width = self.get_string_width(texto) + 6
        height = 5
        
        # Rectángulo redondeado (simulado)
        self.rect(x, y, width, height, 'F')
        
        # Texto centrado
        self.set_xy(x, y)
        self.cell(width, height, texto, 0, 0, 'C')
        
        # Restaurar cursor
        self.set_xy(x + width + 2, y)
        return height

    def draw_card(self, item, es_punto_fuerte=True):
        """Dibuja una tarjeta visual para cada criterio evaluado."""
        start_y = self.get_y()
        
        # Protección de salto de página: Si queda poco espacio, salta
        if start_y > 250:
            self.add_page()
            start_y = self.get_y()

        # Configurar colores según estado
        bar_color = COLOR_SUCCESS if es_punto_fuerte else COLOR_DANGER
        
        # 1. Barra lateral de color (Status Indicator)
        self.set_fill_color(*bar_color)
        self.rect(10, start_y, 2, 25, 'F') # Altura mínima inicial
        
        # 2. Título del Criterio
        self.set_xy(14, start_y)
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(*COLOR_PRIMARY)
        self.cell(0, 6, item.get('criterio', 'Criterio Desconocido'), 0, 1)
        
        # 3. Badge de Importancia (justo al lado o debajo)
        importancia = item.get('importancia', 'MEDIA').upper()
        current_y = self.get_y()
        self.set_xy(14, current_y)
        self.draw_badge(importancia, importancia)
        self.ln(6)
        
        # 4. Razonamiento / Feedback (Texto normal)
        self.set_x(14)
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*COLOR_TEXT_MAIN)
        feedback = item.get('feedback', '') or item.get('razonamiento', '')
        self.multi_cell(0, 5, feedback)
        
        # 5. Caja de Evidencia (Si existe)
        evidencia = item.get('cita_evidencia', '')
        if evidencia and "NO ENCONTRADO" not in evidencia and "NO VALIDADO" not in evidencia:
            self.ln(2)
            self.set_x(14)
            # Fondo gris suave para la cita
            self.set_fill_color(245, 245, 245)
            self.set_text_color(80, 80, 80)
            self.set_font('Helvetica', 'I', 9)
            
            # Icono comillas (simulado con texto)
            self.multi_cell(0, 5, f'"{evidencia}"', border=0, fill=True)
        elif "NO VALIDADO" in evidencia:
             # Caso especial Sheriff: Mostrar alerta técnica
            self.ln(2)
            self.set_x(14)
            self.set_text_color(*COLOR_DANGER)
            self.set_font('Helvetica', 'B', 8)
            self.cell(0, 5, f"[!] ALERTA TÉCNICA: {item.get('razonamiento')}", 0, 1)

        # Espacio final entre tarjetas
        self.ln(4)
        
        # Dibujar línea separadora suave
        line_y = self.get_y()
        self.set_draw_color(230, 230, 230)
        self.line(10, line_y, 200, line_y)
        self.ln(4)

def generar_pdf(reporte_json, output_filename):
    pdf = ModernReport()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # --- DASHBOARD SUPERIOR (Scorecard) ---
    pdf.set_y(35)
    
    # Caja de la Nota
    nota = reporte_json.get('nota_final_0_10', 0)
    
    # Color de la nota
    if nota >= 8: score_color = COLOR_SUCCESS
    elif nota >= 5: score_color = COLOR_WARNING
    else: score_color = COLOR_DANGER
    
    # Dibujar Círculo/Cuadro para la nota
    pdf.set_fill_color(*score_color)
    pdf.rect(10, 35, 30, 30, 'F')
    
    # Texto de la nota (Centrado en el cuadro)
    pdf.set_xy(10, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.cell(30, 10, f"{nota}", 0, 1, 'C')
    pdf.set_font('Helvetica', '', 8)
    pdf.set_xy(10, 52)
    pdf.cell(30, 5, "/ 10", 0, 0, 'C')
    
    # Datos del Asesor (A la derecha de la nota)
    pdf.set_xy(45, 35)
    pdf.set_text_color(*COLOR_TEXT_MAIN)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 8, f"Asesor: {reporte_json.get('asesor', 'Desconocido')}", 0, 1)
    
    pdf.set_xy(45, 43)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*COLOR_TEXT_MUTED)
    pdf.multi_cell(0, 5, reporte_json.get('resumen_ejecutivo', 'Sin resumen disponible.'))
    
    pdf.ln(15) # Separación del dashboard

    # --- SECCIÓN 1: PUNTOS FUERTES ---
    if reporte_json.get('puntos_fuertes'):
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(*COLOR_SUCCESS)
        pdf.cell(0, 10, "FORTALEZAS DETECTADAS", 0, 1)
        # Línea verde debajo del título
        y = pdf.get_y()
        pdf.set_draw_color(*COLOR_SUCCESS)
        pdf.set_line_width(0.5)
        pdf.line(10, y, 200, y)
        pdf.ln(5)
        
        for item in reporte_json['puntos_fuertes']:
            pdf.draw_card(item, es_punto_fuerte=True)
            
    pdf.ln(5)

    # --- SECCIÓN 2: ÁREAS DE MEJORA ---
    if reporte_json.get('areas_mejora'):
        # Forzar nueva página si queda poco espacio
        if pdf.get_y() > 200: pdf.add_page()
        
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(*COLOR_DANGER)
        pdf.cell(0, 10, "ÁREAS DE MEJORA Y CUMPLIMIENTO", 0, 1)
        # Línea roja debajo
        y = pdf.get_y()
        pdf.set_draw_color(*COLOR_DANGER)
        pdf.set_line_width(0.5)
        pdf.line(10, y, 200, y)
        pdf.ln(5)
        
        for item in reporte_json['areas_mejora']:
            pdf.draw_card(item, es_punto_fuerte=False)

    # Guardar archivo
    pdf_path = settings.OUTPUTS_DIR / output_filename
    pdf.output(str(pdf_path))
    print(f"🎨 PDF Estilizado Generado: {pdf_path}")