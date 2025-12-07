import streamlit as st
import os
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import base64
from PIL import Image

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Portal de Firmas", page_icon="✍️", layout="centered")

# NOTA: En la nube, los archivos subidos están en la raíz ("."), no en carpetas.
CARPETA_PENDIENTES = "." 
CARPETA_FIRMADOS = "FIRMADOS"
os.makedirs(CARPETA_FIRMADOS, exist_ok=True)

if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'archivo_actual' not in st.session_state: st.session_state['archivo_actual'] = None
if 'canvas_key' not in st.session_state: st.session_state['canvas_key'] = 0

# --- FUNCIÓN DE ESTAMPADO ---
def estampar_firma(pdf_path, imagen_firma, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)

    # Tamaño de la firma
    ANCHO, ALTO = 110, 60

    # === 📍 MAPA DE POSICIONES EXACTAS (FINAL) ===
    # Formato: (X=Horizontal, Y=Vertical)
    COORDENADAS = {
        # HOJA 5 (DOBLE FIRMA)
        5: [
            # ARRIBA: Exacto en la línea Y=400 según la regla
            (350, 400),  
            # ABAJO: Exacto en la línea Y=180 según la regla
            (350, 180)   
        ],
        
        # HOJA 6 (UNA FIRMA)
        # Exacto en la línea Y=240 según la regla
        6: [
            (350, 240)   
        ],
        
        # HOJA 8 (UNA FIRMA)
        # 🔒 INTACTA - NO TOCAR (Orden del Jefe)
        8: [
            (360, 175)
        ]
    }

    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        num_pag = i + 1 

        if num_pag in COORDENADAS:
            packet = io.BytesIO()
            # Usamos bottomup=True para que Y=0 sea abajo (como la regla)
            c = canvas.Canvas(packet, pagesize=letter, bottomup=True)
            
            for (posX, posY) in COORDENADAS[num_pag]:
                # Dibujamos la firma. Se ajusta un poco el Y para que la base de la firma
                # quede justo sobre la línea medida.
                c.drawImage(imagen_firma, posX, posY, width=ANCHO, height=ALTO, mask='auto')
            
            c.save()
            packet.seek(0)
            sello = PdfReader(packet)
            pagina.merge_page(sello.pages[0])

        pdf_writer.add_page(pagina)

    with open(output_path, "wb") as f:
        pdf_writer.write(f)

# --- INTERFAZ ---
st.title("✍️ Portal de Contratos")

if st.session_state['dni_validado'] is None:
    st.markdown("Ingrese su documento para buscar su contrato.")
    with st.form("login_form"):
        dni_input = st.text_input("DIGITE SU DNI", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

    if submitted and dni_input:
        archivo_encontrado = None
        # Busca archivos PDF que empiecen con el DNI en la carpeta raíz
        for archivo in os.listdir(CARPETA_PENDIENTES):
            if archivo.startswith(dni_input) and archivo.lower().endswith(".pdf"):
                archivo_encontrado = archivo
                break
        
        if archivo_encontrado:
            st.session_state['dni_validado'] = dni_input
            st.session_state['archivo_actual'] = archivo_encontrado
            st.rerun()
        else:
            st.error("❌ Contrato no encontrado. Verifique el DNI.")
else:
    archivo = st.session_state['archivo_actual']
    # Ruta directa porque está en la raíz
    ruta_pdf = archivo
    
    st.success(f"📄 Contrato encontrado: {archivo}")
    
    # Visor de PDF (Intenta mostrarlo, si falla no rompe la app)
    try:
        with open(ruta_pdf, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.warning("No se pudo previsualizar el PDF, pero puede firmarlo abajo.")

    st.markdown("---")
    st.header("👇 Firme aquí")

    # Área de firma
    canvas_result = st_canvas(
        stroke_width=2,
        stroke_color="#000000",
        background_color="#ffffff",
        height=200,
        width=600,
        drawing_mode="freedraw",
        key=f"canvas_{st.session_state['canvas_key']}",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ Borrar"):
            st.session_state['canvas_key'] += 1
            st.rerun()
    
    with col2:
        if st.button("✅ ACEPTAR Y FIRMAR CONTRATO", type="primary", use_container_width=True):
            if canvas_result.image_data is not None:
                ruta_temp = "firma_temp.png"
                # Usamos el mismo nombre para la salida, en la carpeta FIRMADOS
                ruta_salida = os.path.join(CARPETA_FIRMADOS, f"FIRMADO_{archivo}")
                
                with st.spinner("Procesando firma..."):
                    try:
                        # 1. Convertir el dibujo a imagen transparente
                        img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
                        data = img.getdata()
                        newData = []
                        for item in data:
                            # Si es blanco, hacerlo transparente
                            if item[0] > 230 and item[1] > 230 and item[2] > 230:
                                newData.append((255, 255, 255, 0))
                            else:
                                newData.append(item)
                        img.putdata(newData)
                        img.save(ruta_temp, "PNG")
                        
                        # 2. Estampar la firma en el PDF
                        estampar_firma(ruta_pdf, ruta_temp, ruta_salida)
                        
                        # 3. Éxito y descarga
                        st.balloons()
                        st.success("¡Contrato firmado correctamente!")
                        with open(ruta_salida, "rb") as f:
                            st.download_button(
                                label="📥 DESCARGAR CONTRATO FIRMADO",
                                data=f,
                                file_name=f"FIRMADO_{archivo}",
                                mime="application/pdf",
                                type="primary"
                            )
                    except Exception as e:
                        st.error(f"Ocurrió un error al firmar: {e}")
                    finally:
                        # Limpieza de archivo temporal
                        if os.path.exists(ruta_temp): os.remove(ruta_temp)
            else:
                st.warning("⚠️ Por favor, dibuje su firma antes de aceptar.")

    if st.button("⬅️ Salir / Cambiar DNI"):
        st.session_state['dni_validado'] = None
        st.rerun()
