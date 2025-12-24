import streamlit as st
import os
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
import io
import base64
from PIL import Image, ExifTags
import requests
import fitz  # PyMuPDF
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Portal de Contratos", 
    page_icon="✍️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS PERSONALIZADO ---
st.markdown("""
    <style>
    header {visibility: hidden !important;}
    [data-testid="stHeader"] {display: none !important;}
    footer {display: none !important; visibility: hidden !important; height: 0px !important;}
    .stAppDeployButton, [data-testid="stToolbar"], div[class*="viewerBadge"] {display: none !important;}
    #MainMenu {display: none !important;}
    .block-container {padding-top: 1rem !important; padding-bottom: 0rem !important;}
    body::after {content: none !important;}
    
    /* ESTILO PARA PANTALLA COMPLETA NATIVA DE STREAMLIT */
    [data-testid="stImageFullScreenButton"],
    [data-testid="StyledFullScreenButton"],
    button[title="View fullscreen"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        background-color: #FF4B4B !important; 
        color: white !important;
        border: 2px solid white !important;
        border-radius: 50% !important;
        width: 50px !important;
        height: 50px !important;
        right: 10px !important;
        top: 10px !important;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5) !important;
        z-index: 999999 !important; 
    }

    [data-testid="stImageFullScreenButton"] svg,
    [data-testid="StyledFullScreenButton"] svg,
    button[title="View fullscreen"] svg {
        fill: white !important;
        stroke: white !important;
        width: 30px !important;
        height: 30px !important;
    }
    
    [data-testid="stImage"] > div {
        opacity: 1 !important;
    }

    [data-testid="stImageFullScreenButton"]:active {
        transform: scale(0.9) !important;
    }
    
    .streamlit-expanderHeader {
        background-color: #f0f2f6;
        border-radius: 10px;
        font-weight: bold;
    }
    
    /* ESTILO CUADRO ROJO LIDERMAN */
    [data-testid='stFileUploaderDropzone'] span, 
    [data-testid='stFileUploaderDropzone'] small,
    [data-testid='stFileUploaderDropzone'] button {
         display: none !important;
    }

    [data-testid='stFileUploaderDropzone'] {
        min-height: 120px !important;
        border: 2px dashed #cccccc !important;
        background-color: #f9f9f9 !important; 
        border-radius: 10px !important;
        position: relative !important;
    }

    [data-testid='stFileUploaderDropzone']::after {
        content: "📷 TOCAR AQUÍ PARA FOTO"; 
        font-size: 18px !important;
        color: #555555 !important;
        font-weight: bold !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        white-space: nowrap !important;
        pointer-events: none !important; 
    }
    </style>
    """, unsafe_allow_html=True)

# 1. AUTENTICACIÓN GOOGLE
if "gcp_service_account" in st.secrets:
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client_sheets = gspread.authorize(creds)
        service_drive = build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error conectando con Google: {e}")
        st.stop()
else:
    st.error("⚠️ Falta configuración interna.")
    st.stop()

# URL DEL SCRIPT
if "drive_script_url" in st.secrets["general"]:
    WEB_APP_URL = st.secrets["general"]["drive_script_url"]
else:
    st.stop()

# --- CONFIGURACIÓN DE IDs ---
SHEET_ID = "1OmzmHkZsKjJlPw2V2prVlv_LbcS8RzmdLPP1eL6EGNE"
DRIVE_FOLDER_PENDING_ID = "1tu19AXukyc_DvS0xkOxoL5wa9gLEJNS7" 
DRIVE_FOLDER_SIGNED_ID = "1g-ht7BZCUiyN4um1M9bytrrVAZu7gViN"

# Carpetas temporales
CARPETA_TEMP = "TEMP_WORK"
os.makedirs(CARPETA_TEMP, exist_ok=True)

# VARIABLES DE SESIÓN
if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'archivo_id' not in st.session_state: st.session_state['archivo_id'] = None
if 'archivo_nombre' not in st.session_state: st.session_state['archivo_nombre'] = None
if 'canvas_key' not in st.session_state: st.session_state['canvas_key'] = 0
if 'firmado_ok' not in st.session_state: st.session_state['firmado_ok'] = False
if 'foto_bio' not in st.session_state: st.session_state['foto_bio'] = None 
if 'modo_lectura' not in st.session_state: st.session_state['modo_lectura'] = False
if 'pagina_actual' not in st.session_state: st.session_state['pagina_actual'] = 0
if 'zoom_nivel' not in st.session_state: st.session_state['zoom_nivel'] = 100
    
# --- FUNCIONES ---

def corregir_rotacion_imagen(image):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = image._getexif()
        if exif is not None:
            orientation = exif.get(orientation)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass
    return image

def optimizar_imagen(image, max_width=800):
    image = corregir_rotacion_imagen(image)
    width_percent = (max_width / float(image.size[0]))
    new_height = int((float(image.size[1]) * float(width_percent)))
    image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return image

def consultar_estado_dni(dni):
    try:
        sh = client_sheets.open_by_key(SHEET_ID).sheet1
        dnis_en_excel = sh.col_values(1) 
        dni_buscado = str(dni).strip()
        for i, valor_celda in enumerate(dnis_en_excel):
            if str(valor_celda).strip() == dni_buscado:
                return sh.cell(i + 1, 2).value 
        return None
    except: return None

def registrar_firma_sheet(dni):
    try:
        sh = client_sheets.open_by_key(SHEET_ID).sheet1
        dnis_en_excel = sh.col_values(1)
        dni_buscado = str(dni).strip()
        for i, valor_celda in enumerate(dnis_en_excel):
            if str(valor_celda).strip() == dni_buscado:
                fila = i + 1 
                hora_peru = datetime.utcnow() - timedelta(hours=5)
                fecha_fmt = hora_peru.strftime("%Y-%m-%d %H:%M:%S")
                sh.update_cell(fila, 2, "FIRMADO")
                sh.update_cell(fila, 3, fecha_fmt)
                return True
        return False
    except: return False

def buscar_archivo_drive(dni):
    try:
        query = f"'{DRIVE_FOLDER_PENDING_ID}' in parents and name contains '{dni}' and mimeType = 'application/pdf' and trashed = false"
        results = service_drive.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if items:
            return items[0] 
        return None
    except Exception as e:
        return None

def descargar_archivo_drive(file_id, nombre_destino):
    try:
        request = service_drive.files().get_media(fileId=file_id)
        fh = io.FileIO(nombre_destino, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return True
    except: return False

def borrar_archivo_drive(file_id):
    try:
        service_drive.files().delete(fileId=file_id).execute()
        return True
    except: return False

def enviar_a_drive_script(ruta_archivo, nombre_archivo):
    try:
        with open(ruta_archivo, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        payload = {"file": pdf_base64, "filename": nombre_archivo, "folderId": DRIVE_FOLDER_SIGNED_ID}
        requests.post(WEB_APP_URL, json=payload)
        return True
    except: return False

def estampar_firma(pdf_path, imagen_firma, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    ANCHO, ALTO = 100, 50
    COORDENADAS = {5: [(380, 388), (380, 260)], 6: [(400, 130)], 8: [(380, 175)]}
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
    with open(output_path, "wb") as f: pdf_writer.write(f)

def estampar_firma_y_foto_pagina9(pdf_path, imagen_firma_path, imagen_foto_bytes, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    
    X_FIRMA, Y_FIRMA = 100, 370
    W_FIRMA, H_FIRMA = 230, 150
    
    X_FOTO, Y_FOTO = 290, 380
    W_FOTO, H_FOTO = 230, 150 
    
    X_FECHA, Y_FECHA = 150, 308 

    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        
        if i == total_paginas - 1: 
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter)
            
            try:
                c.drawImage(imagen_firma_path, X_FIRMA, Y_FIRMA, width=W_FIRMA, height=H_FIRMA, mask='auto', preserveAspectRatio=True)
            except: pass
            
            if imagen_foto_bytes:
                try:
                    image_bio = ImageReader(io.BytesIO(imagen_foto_bytes))
                    c.drawImage(image_bio, X_FOTO, Y_FOTO, width=W_FOTO, height=H_FOTO, preserveAspectRatio=True)
                except: pass
            
            hora_actual = (datetime.utcnow() - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")
            c.setFont("Helvetica-Bold", 10)
            c.drawString(X_FECHA, Y_FECHA, f"{hora_actual}")
            
            c.save()
            packet.seek(0)
            sello = PdfReader(packet)
            pagina.merge_page(sello.pages[0])
            
        pdf_writer.add_page(pagina)
    
    with open(output_path, "wb") as f: pdf_writer.write(f)

# --- INTERFAZ CENTRAL ---

if st.session_state['dni_validado'] is None:
    # 1. CABECERA (LOGO)
    c_izq, c_centro, c_der = st.columns([1, 2, 1])
    with c_centro:
        if os.path.exists("logo_liderman.png"):
            st.image("logo_liderman.png", use_container_width=True)
        else:
            st.warning("⚠️ (Falta logo_liderman.png)")

    st.title("✍️ Portal de Contratos")
    
    st.markdown("Ingrese su documento para buscar su contrato.")
    
    with st.form("login_form"):
        dni_input = st.text_input("DIGITE SU DNI", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

    if submitted and dni_input:
        with st.spinner("Buscando..."):
            estado_sheet = consultar_estado_dni(dni_input)
        
        if estado_sheet == "FIRMADO":
            st.info(f"ℹ️ El DNI {dni_input} ya registra un contrato firmado.")
            st.markdown("""
            **Si necesita una copia de su contrato** o cree que esto es un error, 
            por favor **contacte al área de Administración de Personal**.
            """)
        
        else:
            with st.spinner("Buscando contrato en la nube..."):
                archivo_drive = buscar_archivo_drive(dni_input)
            
            if archivo_drive:
                ruta_local = os.path.join(CARPETA_TEMP, archivo_drive['name'])
                descargo_ok = descargar_archivo_drive(archivo_drive['id'], ruta_local)
                
                if descargo_ok:
                    st.session_state['dni_validado'] = dni_input
                    st.session_state['archivo_id'] = archivo_drive['id'] 
                    st.session_state['archivo_nombre'] = archivo_drive['name']
                    st.session_state['firmado_ok'] = False
                    st.session_state['foto_bio'] = None
                    st.rerun()
                else:
                    st.error("Error al descargar el documento. Intente nuevamente.")
            else:
                st.error("❌ Contrato no ubicado (Verifique que su DNI esté correctamente escrito.)")
    
    # FAQ LOGIN
    st.markdown("---")
    st.subheader("❓ Preguntas Frecuentes")
    with st.expander("💰 ¿Por qué mi sueldo figura diferente en el contrato?"):
        st.markdown("En el contrato de trabajo se estipula únicamente la **Remuneración Básica** correspondiente al puesto. El monto informado durante su reclutamiento es el **Sueldo Bruto** (básico + otros conceptos). *Lo verá reflejado en su **boleta de pago** a fin de mes.*")
    with st.expander("🕒 ¿Por qué el contrato dice 8hrs si mi puesto de trabajo es de 12hrs?"):
        st.markdown("La ley peruana establece que la **Jornada Ordinaria** base es de 8 horas diarias. Si su turno es de 12 horas, las 4 horas restantes se consideran y pagan como **HORAS EXTRAS**. *Este pago adicional se verá reflejado en su **boleta de pago** a fin de mes.*")
    st.info("📞 **¿Dudas adicionales?** Contacte al área de Administración de Personal.")

else:
    # 2. APP PRINCIPAL (DESPUÉS DEL LOGIN)
    nombre_archivo = st.session_state['archivo_nombre']
    ruta_pdf_local = os.path.join(CARPETA_TEMP, nombre_archivo)
    
    if st.session_state['firmado_ok']:
        st.success("✅ ¡Firma y Biometría registradas!")
        st.info("Contrato guardado exitosamente.")
        
        ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
        if os.path.exists(ruta_salida_firmado):
            with open(ruta_salida_firmado, "rb") as f:
                st.download_button("📥 DESCARGAR CONTRATO", f, file_name=f"FIRMADO_{nombre_archivo}", mime="application/pdf", type="primary")
        
        st.markdown("---")
        if st.button("🏠 SALIR"):
            st.session_state['dni_validado'] = None
            st.session_state['firmado_ok'] = False
            st.rerun()

    else:
        # PANTALLA DE PROCESOS (LECTURA, FOTO, FIRMA)
        if st.session_state['modo_lectura']:
            # VISOR PANTALLA COMPLETA CON ZOOM JS
            c_close, c_tit = st.columns([1, 4])
            with c_close:
                if st.button("❌ CERRAR", type="secondary", use_container_width=True):
                    st.session_state['modo_lectura'] = False
                    st.rerun()
            with c_tit:
                st.markdown(f"<h4 style='text-align: center; margin: 0; padding-top: 5px;'>📄 Página {st.session_state['pagina_actual'] + 1}</h4>", unsafe_allow_html=True)

            try:
                doc = fitz.open(ruta_pdf_local)
                total_paginas = len(doc)
                pagina = doc[st.session_state['pagina_actual']]

                pix = pagina.get_pixmap(dpi=250) 
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                
                st.markdown(
                    f"""
                    <style>
                        #image-container {{
                            width: 100%;
