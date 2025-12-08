import streamlit as st
import os
import shutil  # Librería para mover archivos
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import base64
from PIL import Image
import requests
import fitz  # PyMuPDF

# --- CONFIGURACIÓN DE PÁGINA (MODO KIOSCO) ---
st.set_page_config(page_title="Portal de Contratos", page_icon="✍️", layout="centered")

# --- CSS NUCLEAR (SIN MENÚS NI BOTONES RAROS) ---
st.markdown("""
    <style>
    header {visibility: hidden;}
    [data-testid="stHeader"] {display: none;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    div[data-testid="stCanvas"] button {display: none !important;}
    div[data-testid="stElementToolbar"] {display: none !important;}
    .block-container {padding-top: 1rem !important;}
    </style>
    """, unsafe_allow_html=True)

# LEER SECRETOS
if "drive_script_url" in st.secrets["general"]:
    WEB_APP_URL = st.secrets["general"]["drive_script_url"]
else:
    st.error("⚠️ Error de configuración interna.")
    st.stop()

# CONFIGURACIÓN DE CARPETAS
DRIVE_FOLDER_ID = "1g-ht7BZCUiyN4um1M9bytrrVAZu7gViN"
CARPETA_PENDIENTES = "PENDIENTES"  
CARPETA_FIRMADOS = "FIRMADOS"
CARPETA_PROCESADOS = "PROCESADOS"  # Nueva carpeta "Cementerio"

os.makedirs(CARPETA_FIRMADOS, exist_ok=True)
os.makedirs(CARPETA_PENDIENTES, exist_ok=True)
os.makedirs(CARPETA_PROCESADOS, exist_ok=True)

# VARIABLES DE SESIÓN
if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'archivo_actual' not in st.session_state: st.session_state['archivo_actual'] = None
if 'canvas_key' not in st.session_state: st.session_state['canvas_key'] = 0
if 'firmado_ok' not in st.session_state: st.session_state['firmado_ok'] = False # Estado del Candado

# --- FUNCIÓN: ENVIAR A DRIVE ---
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
        return response.status_code == 200
    except:
        return False

# --- FUNCIÓN: ESTAMPAR FIRMA ---
def estampar_firma(pdf_path, imagen_firma, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    ANCHO, ALTO = 110, 60

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

# --- FUNCIÓN: MOSTRAR IMÁGENES ---
def mostrar_pdf_como_imagenes(ruta_pdf):
    try:
        doc = fitz.open(ruta_pdf)
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            st.image(img_bytes, use_container_width=True)
    except:
        st.error("Error visualizando el documento.")

# --- INTERFAZ PRINCIPAL ---
st.title("✍️ Portal de Contratos")

# PANTALLA 1: LOGIN
if st.session_state['dni_validado'] is None:
    st.markdown("Ingrese su documento para buscar su contrato.")
    with st.form("login_form"):
        dni_input = st.text_input("DIGITE SU DNI", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

    if submitted and dni_input:
        archivo_encontrado = None
        
        # 1. BUSCAR EN PENDIENTES
        if os.path.exists(CARPETA_PENDIENTES):
            for archivo in os.listdir(CARPETA_PENDIENTES):
                if archivo.startswith(dni_input) and archivo.lower().endswith(".pdf"):
                    archivo_encontrado = archivo
                    break
        
        if archivo_encontrado:
            # ¡Lo encontramos! Pasamos a firmar
            st.session_state['dni_validado'] = dni_input
            st.session_state['archivo_actual'] = archivo_encontrado
            st.session_state['firmado_ok'] = False # Reseteamos estado
            st.rerun()
        else:
            # 2. SI NO ESTÁ, BUSCAR EN PROCESADOS (HISTORIAL)
            ya_firmado = False
            if os.path.exists(CARPETA_PROCESADOS):
                for archivo in os.listdir(CARPETA_PROCESADOS):
                    if archivo.startswith(dni_input) and archivo.lower().endswith(".pdf"):
                        ya_firmado = True
                        break
            
            if ya_firmado:
                st.warning("⛔ Este contrato ya fue firmado anteriormente.")
                st.info("Si necesita una copia, contacte a RRHH.")
            else:
                st.error("❌ Contrato no ubicado en el sistema.")

# PANTALLA 2: LECTURA Y FIRMA
else:
    archivo = st.session_state['archivo_actual']
    
    # SI YA FIRMÓ CON ÉXITO (FASE B)
    if st.session_state['firmado_ok']:
        st.success("✅ ¡Firma registrada exitosamente!")
        st.markdown(f"**Archivo:** {archivo}")
        st.info("Su contrato ha sido enviado a la central y archivado.")
        
        st.markdown("---")
        st.write("Puede descargar su copia personal aquí:")
        
        # Ruta del archivo firmado
        ruta_salida = os.path.join(CARPETA_FIRMADOS, archivo)
        
        # BOTÓN DE DESCARGA
        if os.path.exists(ruta_salida):
            with open(ruta_salida, "rb") as f:
                st.download_button(
                    label="📥 DESCARGAR MI CONTRATO FIRMADO",
                    data=f,
                    file_name=archivo,
                    mime="application/pdf",
                    type="primary" # Botón rojo/destacado
                )
        
        st.markdown("---")
        # BOTÓN SALIR
        if st.button("🏠 FINALIZAR Y SALIR"):
            st.session_state['dni_validado'] = None
            st.session_state['firmado_ok'] = False
            st.rerun()

    # SI AÚN NO FIRMA (FASE A)
    else:
        ruta_pdf = os.path.join(CARPETA_PENDIENTES, archivo)
        st.success(f"✅ Documento listo: **{archivo}**")
        st.info("Lea el contrato y firme al final.")
        
        st.markdown("---")
        # VISOR
        with st.container(height=500, border=True):
            mostrar_pdf_como_imagenes(ruta_pdf)

        st.markdown("---")
        st.header("👇 Firme aquí")
        
        # LIENZO
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
                    
                    with st.spinner("Procesando y bloqueando documento..."):
                        try:
                            # 1. Crear imagen firma
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
                            
                            # 2. Estampar PDF
                            ruta_origen = os.path.join(CARPETA_PENDIENTES, archivo)
                            estampar_firma(ruta_origen, ruta_temp, ruta_salida)
                            
                            # 3. Enviar a Drive (Nube)
                            enviar_a_drive_script(ruta_salida, nombre_final)
                            
                            # 4. MOVER ARCHIVO A "PROCESADOS" (Bloqueo local)
                            ruta_destino_final = os.path.join(CARPETA_PROCESADOS, archivo)
                            # Si ya existe en procesados, lo sobreescribimos por si acaso
                            if os.path.exists(ruta_destino_final):
                                os.remove(ruta_destino_final)
                            shutil.move(ruta_origen, ruta_destino_final)
                            
                            # 5. ACTIVAR ESTADO DE ÉXITO Y RECARGAR
                            st.session_state['firmado_ok'] = True
                            st.balloons()
                            st.rerun() # Recarga para mostrar la pantalla de FASE B

                        except Exception as e:
                            st.error(f"Error técnico: {e}")
                        finally:
                            if os.path.exists(ruta_temp): os.remove(ruta_temp)
                else:
                    st.warning("⚠️ Por favor, dibuje su firma.")

        if st.button("⬅️ Salir"):
            st.session_state['dni_validado'] = None
            st.rerun()
