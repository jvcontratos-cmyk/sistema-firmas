import streamlit as st
import os
import io
import base64
from PIL import Image
import requests
import fitz  # PyMuPDF
import gspread 
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build 
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime, timedelta

# Librerías para PDF y Gráficos
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Portal de Contratos", 
    page_icon="✍️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS LIMPIO: SOLO OCULTACIÓN (SIN BARRAS RARAS) ---
st.markdown("""
    <style>
    /* 1. BORRAR HEADER Y MENÚS */
    header {visibility: hidden !important;}
    [data-testid="stHeader"] {display: none !important;}
    
    /* 2. BORRAR FOOTER Y FULLSCREEN */
    footer {display: none !important; visibility: hidden !important; height: 0px !important;}
    button[title="View fullscreen"] {display: none !important;}
    .viewerBadge_container__1QSob {display: none !important;}
    
    /* 3. BORRAR ELEMENTOS FLOTANTES */
    .stAppDeployButton, [data-testid="stToolbar"], div[class*="viewerBadge"] {display: none !important;}
    #MainMenu {display: none !important;}
    
    /* 4. AJUSTE DE MÁRGENES */
    .block-container {padding-top: 1rem !important; padding-bottom: 2rem !important;}
    body::after {content: none !important;}
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

# --- FUNCIONES ---

def consultar_estado_dni(dni):
    try:
        sh = client_sheets.open_by_key(SHEET_ID).sheet1
        cell = sh.find(dni)
        if cell:
            return sh.cell(cell.row, 2).value 
        return None
    except: return None

def registrar_firma_sheet(dni):
    try:
        sh = client_sheets.open_by_key(SHEET_ID).sheet1
        cell = sh.find(dni)
        if cell:
            hora_peru = datetime.utcnow() - timedelta(hours=5)
            fecha_fmt = hora_peru.strftime("%Y-%m-%d %H:%M:%S")
            sh.update_cell(cell.row, 2, "FIRMADO")
            sh.update_cell(cell.row, 3, fecha_fmt)
            return True
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

def estampar_firma_y_foto_pagina9(pdf_path, imagen_firma_path, imagen_foto_bytes, output_path):
    """
    Rellena la PÁGINA 9 (Consentimiento) con Firma, Foto y Fecha.
    """
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    
    # Coordenadas Ajustadas para la Página 9 (Hoja de Consentimiento)
    X_FIRMA, Y_FIRMA = 70, 250
    W_FIRMA, H_FIRMA = 200, 120
    
    X_FOTO, Y_FOTO = 340, 250
    W_FOTO, H_FOTO = 200, 150 
    
    X_FECHA, Y_FECHA = 150, 180 

    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        
        # SI ES LA ÚLTIMA PÁGINA (o la 9, índice 8)
        if i == total_paginas - 1: 
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter)
            
            # A. PONER FIRMA
            try:
                c.drawImage(imagen_firma_path, X_FIRMA, Y_FIRMA, width=W_FIRMA, height=H_FIRMA, mask='auto', preserveAspectRatio=True)
            except: pass
            
            # B. PONER FOTO BIOMÉTRICA
            if imagen_foto_bytes:
                try:
                    image_bio = ImageReader(io.BytesIO(imagen_foto_bytes))
                    c.drawImage(image_bio, X_FOTO, Y_FOTO, width=W_FOTO, height=H_FOTO, preserveAspectRatio=True)
                except: pass
            
            # C. PONER FECHA Y HORA
            hora_actual = (datetime.utcnow() - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")
            c.setFont("Helvetica-Bold", 10)
            c.drawString(X_FECHA, Y_FECHA, hora_actual)
            
            c.save()
            packet.seek(0)
            sello = PdfReader(packet)
            pagina.merge_page(sello.pages[0])
            
        pdf_writer.add_page(pagina)
    
    # Guardar PDF Final
    with open(output_path, "wb") as f: pdf_writer.write(f)

def mostrar_pdf_como_imagenes(ruta_pdf):
    try:
        doc = fitz.open(ruta_pdf)
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=150)
            st.image(pix.tobytes("png"), use_container_width=True)
    except: st.error("Error visualizando documento.")

# --- INTERFAZ CENTRAL ---
st.title("✍️ Portal de Contratos")

if st.session_state['dni_validado'] is None:
    st.markdown("Ingrese su documento para buscar su contrato.")
    with st.form("login_form"):
        dni_input = st.text_input("DIGITE SU DNI", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

    # === [AQUÍ ESTÁ EL ARREGLO] === 
    # La lógica va INMEDIATAMENTE después del botón, ANTES de los FAQ.
    if submitted and dni_input:
        with st.spinner("Conectando con base de datos..."):
            estado_sheet = consultar_estado_dni(dni_input)
        
        if estado_sheet == "FIRMADO":
            st.info(f"ℹ️ El DNI {dni_input} ya registra un contrato firmado.")
            st.markdown("**Si necesita copia**, contacte a RRHH.")
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
                    st.error("Error al descargar. Intente nuevamente.")
            else:
                st.error("❌ Contrato no ubicado (Verifique que su DNI esté correcto).")
    # ==============================

    # === FAQ (AHORA SALE DESPUÉS) ===
    st.markdown("---")
    st.subheader("❓ Preguntas Frecuentes")
    with st.expander("💰 ¿Por qué mi sueldo figura diferente en el contrato?"):
        st.markdown("En el contrato se estipula la **Remuneración Básica**. El monto informado en reclutamiento es el **Sueldo Bruto**.")
    with st.expander("🕒 ¿Por qué el contrato dice 8hrs si trabajo 12hrs?"):
        st.markdown("La jornada base es de 8 horas. El resto se paga como **HORAS EXTRAS**.")
    st.info("📞 **¿Dudas adicionales?** Contacte al área de Administración de Personal.")

else:
    # --- PANTALLA DE FIRMA ---
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
        st.success(f"✅ Documento listo: **{nombre_archivo}**")
        st.info("Lea el contrato. Al final encontrará la validación de identidad.")
        
        with st.container(height=500, border=True):
            if os.path.exists(ruta_pdf_local):
                mostrar_pdf_como_imagenes(ruta_pdf_local)

        st.markdown("---")
        
        # === ZONA DE BIOMETRÍA Y FIRMA (CANDADO) ===
        col_bio, col_firma = st.columns([1, 1])
        
        # 1. FOTO
        st.subheader("1. Validación de Identidad")
        if st.session_state['foto_bio'] is None:
            st.warning("📸 Tome una foto para activar la firma.")
            foto = st.camera_input("Selfie de verificación", label_visibility="collapsed")
            if foto:
                st.session_state['foto_bio'] = foto.getvalue()
                st.success("Foto OK")
                st.rerun()
        else:
            st.success("✅ Identidad Validada")
            st.image(st.session_state['foto_bio'], width=150)
            if st.button("🔄 Retomar Foto"):
                st.session_state['foto_bio'] = None
                st.rerun()

        # 2. FIRMA (Solo si hay foto)
        if st.session_state['foto_bio'] is not None:
            st.markdown("---")
            st.subheader("2. Conformidad y Firma")
            st.caption("Dibuje su firma:")
            
            canvas_result = st_canvas(
                stroke_width=2, stroke_color="#000000", background_color="#ffffff", 
                height=200, width=600, drawing_mode="freedraw", 
                display_toolbar=False, key=f"canvas_{st.session_state['canvas_key']}"
            )

            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("🗑️ Borrar"):
                    st.session_state['canvas_key'] += 1
                    st.rerun()
            
            with col2:
                if st.button("✅ ACEPTAR Y FIRMAR", type="primary", use_container_width=True):
                    if canvas_result.image_data is not None:
                        ruta_firma = os.path.join(CARPETA_TEMP, "firma.png")
                        ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
                        
                        # AQUÍ ESTÁ EL CAMBIO DE TEXTO QUE PEDISTE
                        with st.spinner("⏳ Procesando firma..."):
                            try:
                                # Guardar Firma
                                img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
                                data = img.getdata()
                                newData = []
                                for item in data:
                                    if item[0] > 230 and item[1] > 230 and item[2] > 230:
                                        newData.append((255, 255, 255, 0))
                                    else:
                                        newData.append(item)
                                img.putdata(newData)
                                img.save(ruta_firma, "PNG")
                                
                                # ESTAMPAR EN PAGINA 9
                                estampar_firma_y_foto_pagina9(
                                    ruta_pdf_local, 
                                    ruta_firma, 
                                    st.session_state['foto_bio'], 
                                    ruta_salida_firmado
                                )
                                
                                # Subir y Registrar
                                enviar_a_drive_script(ruta_salida_firmado, nombre_archivo)
                                registrar_firma_sheet(st.session_state['dni_validado'])
                                borrar_archivo_drive(st.session_state['archivo_id'])
                                
                                st.session_state['firmado_ok'] = True
                                st.balloons()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                            finally:
                                if os.path.exists(ruta_firma): os.remove(ruta_firma)
                    else:
                        st.warning("⚠️ Falta la firma.")

