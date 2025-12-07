import streamlit as st
import os
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io

st.set_page_config(page_title="Modo Regla 📏", layout="centered")

# --- RUTAS ---
CARPETA_PENDIENTES = "PENDIENTES"
CARPETA_FIRMADOS = "FIRMADOS"
os.makedirs(CARPETA_PENDIENTES, exist_ok=True)
os.makedirs(CARPETA_FIRMADOS, exist_ok=True)

if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'archivo_actual' not in st.session_state: st.session_state['archivo_actual'] = None

# --- FUNCIÓN DE REGLA (SOLO DIBUJA LINEAS) ---
def dibujar_regla(pdf_path, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    
    # LINEAS AZULES (EJE X - HORIZONTAL)
    c.setStrokeColorRGB(0, 0, 1, 0.5) 
    c.setFont("Helvetica", 10)
    for x in range(0, 600, 50): # Cada 50 puntos
        c.line(x, 0, x, 800)
        c.drawString(x+2, 50, f"{x}")
        c.drawString(x+2, 400, f"{x}") # Repetir en el medio
        c.drawString(x+2, 750, f"{x}") # Repetir arriba

    # LINEAS ROJAS (EJE Y - VERTICAL)
    c.setStrokeColorRGB(1, 0, 0, 0.5)
    for y in range(0, 850, 20): # Cada 20 puntos
        c.line(0, y, 600, y)
        c.drawString(5, y+2, f"{y}")
        c.drawString(300, y+2, f"{y}")

    c.save()
    packet.seek(0)
    pdf_regla = PdfReader(packet)

    for page in pdf_original.pages:
        page.merge_page(pdf_regla.pages[0])
        pdf_writer.add_page(page)

    with open(output_path, "wb") as f:
        pdf_writer.write(f)

# --- INTERFAZ LIGERA ---
st.title("📏 MODO REGLA")
st.info("Introduce un DNI para descargar el PDF con las medidas.")

if st.session_state['dni_validado'] is None:
    with st.form("medir"):
        dni = st.text_input("DNI:")
        submit = st.form_submit_button("BUSCAR Y MEDIR")
    
    if submit and dni:
        for f in os.listdir(CARPETA_PENDIENTES):
            if f.startswith(dni):
                st.session_state['dni_validado'] = dni
                st.session_state['archivo_actual'] = f
                st.rerun()
        st.error("No encontrado.")
else:
    archivo = st.session_state['archivo_actual']
    ruta = os.path.join(CARPETA_PENDIENTES, archivo)
    salida = os.path.join(CARPETA_FIRMADOS, "MEDIDA.pdf")
    
    dibujar_regla(ruta, salida)
    
    st.success("✅ ¡PDF Cuadriculado Listo!")
    with open(salida, "rb") as f:
        st.download_button("📥 DESCARGAR PDF CON REGLA", f, file_name="MEDIDAS.pdf", type="primary")
        
    if st.button("🔙 VOLVER"):
        st.session_state['dni_validado'] = None
        st.rerun()