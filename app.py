import streamlit as st
import os
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import base64
from PIL import Image
import requests

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Portal de Firmas", page_icon="✍️", layout="centered")

# LEER SECRETOS
if "drive_script_url" in st.secrets["general"]:
    WEB_APP_URL = st.secrets["general"]["drive_script_url"]
else:
    st.error("⚠️ Falta configurar el secreto drive_script_url")
    st.stop()

# TU CARPETA DE DRIVE
DRIVE_FOLDER_ID = "1g-ht7BZCUiyN4um1M9bytrrVAZu7gViN"

# === CAMBIO AQUÍ: AHORA APUNTAMOS A LA CARPETA ===
CARPETA_PENDIENTES = "PENDIENTES"  
# =================================================

CARPETA_FIRMADOS = "FIRMADOS"
os.makedirs(CARPETA_FIRMADOS, exist_ok=True)
# Aseguramos que exista la carpeta PENDIENTES para que no de error si está vacía
os.makedirs(CARPETA_PENDIENTES, exist_ok=True)

if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'archivo_actual' not in st.session_state: st.session_state['archivo_actual'] = None
if 'canvas_key' not in st.session_state: st.session_state['canvas_key'] = 0

# --- FUNCIÓN: ENVIAR AL PUENTE DE DRIVE ---
def enviar_a_drive_script(ruta_archivo, nombre_archivo):
    try:
        with open(ruta_archivo, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        payload = {
            "file": pdf_base64,
            "filename": nombre_archivo,
            "folderId": DRIVE_FOLDER_ID
        }
        
        response = requests.post(WEB_APP_URL, json=payload)
        
        if response.status_code == 200:
            return True
        else:
            st.warning(f"Respuesta del servidor: {response.text}")
            return False
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return False

# --- FUNCIÓN DE ESTAMPADO ---
def estampar_firma(pdf_path, imagen_firma, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    ANCHO, ALTO = 110, 60

    # === 📍 COORDENADAS ===
    COORDENADAS = {
        5: [(380, 388), (380, 260)],
        6: [(380, 115)],
        8: [(380, 175)]
    }

    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        num_pag = i + 1 
        if num_pag in COORDENADAS:
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter, bottomup=True)
            for (posX, posY) in COORDENADAS[num_pag]:
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
        
        # BUSCAR EN LA CARPETA PENDIENTES
        if os.path.exists(CARPETA_PENDIENTES):
            for archivo in os.listdir(CARPETA_PENDIENTES):
                if archivo.startswith(dni_input) and archivo.lower().endswith(".pdf"):
                    archivo_encontrado = archivo
                    break
        
        if archivo_encontrado:
            st.session_state['dni_validado'] = dni_input
            st.session_state['archivo_actual'] = archivo_encontrado
            st.rerun()
        else:
            st.error("❌ Contrato no encontrado en la carpeta PENDIENTES.")
else:
    archivo = st.session_state['archivo_actual']
    # AHORA LA RUTA INCLUYE LA CARPETA
    ruta_pdf = os.path.join(CARPETA_PENDIENTES, archivo)
    
    st.success(f"📄 Contrato: {archivo}")
    
    try:
        with open(ruta_pdf, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except: pass

    st.markdown("---")
    st.header("👇 Firme aquí")
    
    canvas_result = st_canvas(
        stroke_width=2, stroke_color="#000000", background_color="#ffffff",
        height=200, width=600, drawing_mode="freedraw",
        display_toolbar=False,
        key=f"canvas_{st.session_state['canvas_key']}",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ Borrar"):
            st.session_state['canvas_key'] += 1
            st.rerun()
    
    with col2:
        if st.button("✅ ACEPTAR Y FIRMAR", type="primary", use_container_width=True):
            if canvas_result.image_data is not None:
                ruta_temp = "firma_temp.png"
                nombre_final = archivo
                ruta_salida = os.path.join(CARPETA_FIRMADOS, nombre_final)
                
                with st.spinner("Procesando contrato..."):
                    try:
                        img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
                        data = img.getdata()
                        newData = []
                        for item in data:
                            if item[0] > 230 and item[1] > 230 and item[2] > 230:
                                newData.append((255, 255, 255, 0))
                            else:
                                newData.append(item)
                        img.putdata(newData)
                        img.save(ruta_temp, "PNG")
                        
                        estampar_firma(ruta_pdf, ruta_temp, ruta_salida)
                        
                        exito = enviar_a_drive_script(ruta_salida, nombre_final)
                        
                        if exito:
                            st.balloons()
                            st.success("✅ Contrato firmado correctamente.")
                            with open(ruta_salida, "rb") as f:
                                st.download_button("📥 Descargar mi copia", f, file_name=nombre_final, mime="application/pdf")
                        else:
                            st.warning("Contrato firmado localmente. Hubo un problema de conexión con el archivo central.")
                            with open(ruta_salida, "rb") as f:
                                st.download_button("📥 Descargar copia ahora", f, file_name=nombre_final)

                    except Exception as e:
                        st.error(f"Error en el proceso: {e}")
                    finally:
                        if os.path.exists(ruta_temp): os.remove(ruta_temp)
            else:
                st.warning("Por favor, dibuje su firma antes de aceptar.")

    if st.button("⬅️ Salir"):
        st.session_state['dni_validado'] = None
        st.rerun()
