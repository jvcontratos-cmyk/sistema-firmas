import streamlit as st
import os
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io

# --- CONFIGURACIÓN DE PÁGINA LAB ---
st.set_page_config(page_title="LAB COORDENADAS", page_icon="🧪", layout="wide")

st.markdown("<style>footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st.title("🧪 Laboratorio de Coordenadas")
st.warning("Usa esta web solo para calibrar. No registra datos en Excel.")

# --- 1. BIBLIOTECA MAESTRA (Aquí es donde harás tus cambios) ---
COORDENADAS_MAESTRAS = {
    "Normal": { 
        5: [(380, 388), (380, 260)], 
        6: [(400, 130)], 
        8: [(380, 175)]
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

# --- 2. MOTOR DE ESTAMPADO ---
def estampar_prueba(pdf_path, tipo_contrato):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    # Usamos el logo como firma de prueba para visualizar posición
    imagen_test = "logo_liderman.png" 
    
    config = COORDENADAS_MAESTRAS.get(tipo_contrato, {})
    
    for i, pagina in enumerate(pdf_original.pages):
        num_pag = i + 1
        if num_pag in config:
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter, bottomup=True)
            for (posX, posY) in config[num_pag]:
                # Dibujamos un recuadro y el logo para ver el área exacta
                c.setStrokeColorRGB(1, 0, 0) # Rojo para el borde de prueba
                c.rect(posX, posY, 100, 50, stroke=1, fill=0)
                if os.path.exists(imagen_test):
                    c.drawImage(imagen_test, posX, posY, width=100, height=50, mask='auto')
            c.save()
            packet.seek(0)
            sello = PdfReader(packet)
            pagina.merge_page(sello.pages[0])
        pdf_writer.add_page(pagina)
    
    output = io.BytesIO()
    pdf_writer.write(output)
    return output.getvalue()

# --- 3. INTERFAZ DE USUARIO ---
col_ui, col_json = st.columns([2, 1])

with col_ui:
    archivo = st.file_uploader("📂 Sube el PDF que quieres probar", type="pdf")
    tipo = st.selectbox("🎯 Selecciona el Tipo de Contrato", list(COORDENADAS_MAESTRAS.keys()))
    
    if archivo:
        if st.button("🚀 ESTAMPAR FIRMAS DE PRUEBA", type="primary", use_container_width=True):
            with st.spinner("Calibrando..."):
                pdf_resultado = estampar_prueba(archivo, tipo)
                st.success("✅ Estampado listo")
                st.download_button(
                    label="📥 DESCARGAR Y VER POSICIONES",
                    data=pdf_resultado,
                    file_name=f"TEST_{tipo}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

with col_json:
    st.write("📊 **Mapa de coordenadas actual:**")
    st.json(COORDENADAS_MAESTRAS[tipo])

st.info("💡 **Instrucción:** Cambia los números en el código de GitHub (sección COORDENADAS_MAESTRAS), guarda cambios y refresca esta página para ver el movimiento.")
