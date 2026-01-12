import streamlit as st
import os
import io
import fitz  # PyMuPDF
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# --- CONFIGURACIÓN DE PÁGINA LAB ---
st.set_page_config(page_title="LAB COORDENADAS", page_icon="🧪", layout="wide")

# CSS para limpiar la interfaz
st.markdown("""
    <style>
    footer {visibility: hidden;} 
    header {visibility: hidden;}
    .block-container {padding-top: 2rem;}
    </style>
    """, unsafe_allow_html=True)

st.title("🧪 Laboratorio de Coordenadas (Vista Real)")
st.info("Lo que ves en la imagen es el PDF real procesado. Las coordenadas coinciden 1:1.")

# --- 1. BIBLIOTECA MAESTRA ---
COORDENADAS_MAESTRAS = {
    "Normal": { 
        5: [(375, 360), (360, 180)], 
        6: [(395, 120)], 
        8: [(350, 140)]
    },
    "Mina": {
        7: [(350, 345), (95, 200)], 
        9: [(300, 160)], 
        10: [(375, 150)]
    },
    "Guardian": {
        5: [(400, 415), (100, 280)],
        7: [(370, 400)], 
        8: [(355, 175)]
    },
    "Banco": {
        4: [(340, 380), (340, 215)],
        5: [(340, 160)], 
        7: [(380, 220)]
    }
}

# --- 2. MOTOR DE ESTAMPADO REAL ---
def estampar_proceso_real(pdf_file, tipo_contrato):
    pdf_original = PdfReader(pdf_file)
    pdf_writer = PdfWriter()
    
    # Imagen temporal para visualización (Logo Liderman)
    # Si no existe, el código dibujará el cuadro rojo igual
    ruta_logo = "logo_liderman.png" 
    
    config = COORDENADAS_MAESTRAS.get(tipo_contrato, {})
    
    for i, pagina in enumerate(pdf_original.pages):
        num_pag = i + 1
        if num_pag in config:
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter, bottomup=True)
            for (posX, posY) in config[num_pag]:
                # Dibujamos el área de la firma (100x50 unidades de PDF)
                c.setStrokeColorRGB(1, 0, 0) # Rojo
                c.setLineWidth(2)
                c.rect(posX, posY, 100, 50, stroke=1, fill=0)
                
                # Texto de ayuda sobre el cuadro
                c.setFont("Helvetica-Bold", 8)
                c.setFillColorRGB(1, 0, 0)
                c.drawString(posX, posY + 55, f"X:{posX} Y:{posY}")
                
                if os.path.exists(ruta_logo):
                    c.drawImage(ruta_logo, posX, posY, width=100, height=50, mask='auto')
            c.save()
            packet.seek(0)
            sello = PdfReader(packet)
            pagina.merge_page(sello.pages[0])
        pdf_writer.add_page(pagina)
    
    output = io.BytesIO()
    pdf_writer.write(output)
    return output.getvalue()

# --- 3. INTERFAZ Y VISOR ---
col_control, col_visor = st.columns([1, 2])

with col_control:
    st.subheader("⚙️ Controles")
    archivo_subido = st.file_uploader("Subir contrato PDF", type="pdf")
    tipo_sel = st.selectbox("Tipo de Contrato", list(COORDENADAS_MAESTRAS.keys()))
    
    if archivo_subido:
        if st.button("🚀 PROCESAR Y VER", type="primary", use_container_width=True):
            st.session_state['pdf_resultado'] = estampar_proceso_real(archivo_subido, tipo_sel)

    st.divider()
    st.write("📍 **Coordenadas en edición:**")
    st.json(COORDENADAS_MAESTRAS[tipo_sel])

with col_visor:
    if 'pdf_resultado' in st.session_state:
        pdf_bytes = st.session_state['pdf_resultado']
        
        # Convertimos PDF a imagen para el visor
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        st.subheader("📄 Previsualización de Firmas")
        
        paginas_con_firma = [p for p in COORDENADAS_MAESTRAS[tipo_sel].keys()]
        
        for num_pag in paginas_con_firma:
            if num_pag <= len(doc):
                page = doc.load_page(num_pag - 1)
                pix = page.get_pixmap(dpi=120)
                st.image(pix.tobytes("png"), caption=f"VISTA REAL - PÁGINA {num_pag}", use_container_width=True)
        
        st.download_button(
            "📥 DESCARGAR PDF PROCESADO", 
            pdf_bytes, 
            file_name=f"PRUEBA_{tipo_sel}.pdf", 
            mime="application/pdf",
            use_container_width=True
        )
    else:
        st.info("Sube un PDF y dale a 'Procesar' para ver las coordenadas aquí.")



