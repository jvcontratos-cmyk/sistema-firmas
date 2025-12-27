import streamlit as st
import os
import re
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
    
    /* PANTALLA COMPLETA */
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
    
    [data-testid="stImage"] > div { opacity: 1 !important; }

    /* ACORDEÓN */
    .streamlit-expanderHeader {
        background-color: #f0f2f6;
        border-radius: 10px;
        font-weight: bold;
    }
    
    /* CUADRO ROJO LIDERMAN */
    [data-testid='stFileUploaderDropzone'] span, 
    [data-testid='stFileUploaderDropzone'] small,
    [data-testid='stFileUploaderDropzone'] button { display: none !important; }

    [data-testid='stFileUploaderDropzone'] {
        min-height: 120px !important;
        border: 2px dashed #cccccc !important;
        background-color: #f9f9f9 !important; 
        border-radius: 10px !important;
        position: relative !important;
    }

    [data-testid='stFileUploaderDropzone']::after {
        content: "📷 TOCAR AQUÍ PARA ABRIR LA CÁMARA (CELULAR)"; 
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

# --- CONFIGURACIÓN DE IDs INTELIGENTE (EL CEREBRO NUEVO) ---
SHEET_ID = "1OmzmHkZsKjJlPw2V2prVlv_LbcS8RzmdLPP1eL6EGNE"
ID_CARPETA_FOTOS = "1JJHIw0u-MxfL11hY-rrgAODqctau1QpN"

# Diccionario de rutas según la sede (nombre de la pestaña en Excel)
RUTAS_DRIVE = {
    "LIMA": {
        "PENDIENTES": "1ghXH11Lazi3kHKTaQ4F-zTd-6pjuPI84",
        "FIRMADOS": "1NlM81Vo2NuWCxyFD-xfpAFMbywvdVJoL"
    },
    "PROVINCIA": {
        "PENDIENTES": "19p6rbh1UN-ToXKyvzGaE6DUCgukhFM3C",
        "FIRMADOS": "1a3A_zFBdjhnrrX3g975dWJV-94xsDpkD"
    }
}

# Diccionario de rutas según la sede (YA ESTABA)
RUTAS_DRIVE = {
    "LIMA": {
        "PENDIENTES": "1ghXH11Lazi3kHKTaQ4F-zTd-6pjuPI84",
        "FIRMADOS": "1NlM81Vo2NuWCxyFD-xfpAFMbywvdVJoL"
    },
    "PROVINCIA": {
        "PENDIENTES": "19p6rbh1UN-ToXKyvzGaE6DUCgukhFM3C",
        "FIRMADOS": "1a3A_zFBdjhnrrX3g975dWJV-94xsDpkD"
    }
}

# --- NUEVO: BIBLIOTECA MAESTRA DE COORDENADAS ---
# Define en qué páginas y coordenadas X/Y van las firmas simples según el TIPO.
# NOTA: La última página siempre se procesa aparte con foto y fecha.
COORDENADAS_MAESTRAS = {
    # El contrato estándar de Lima y Ciudad Provincia (NO TOCAR)
    "Normal": { 
        5: [(380, 388), (380, 260)], 
        6: [(400, 130)], 
        8: [(380, 175)]
    },
    # El nuevo contrato de Mina (11 páginas total aprox)
    # ¡OJO JEFE! He puesto coordenadas X,Y aproximadas (ej: 400, 250).
    # Tendremos que ajustarlas viendo dónde caen en la primera prueba.
    "Mina": {
        # --- PÁGINA 7 (AJUSTADA A TU FOTO) ---
        # Firma 1 (Arriba Derecha, Trabajador): X=400, Y=260
        # Firma 2 (Abajo Izquierda, Nombre): X=100, Y=160
        7: [(350, 345), (95, 200)], 
        
        # --- PÁGINAS 9 Y 10 (NO LAS TOCAMOS AÚN) ---
        9: [(300, 160)],             
        10: [(375, 150)]             
    },
    # Espacios futuros
    "Banco": {},
    "Antamina": {}
}

# Carpetas temporales
CARPETA_TEMP = "TEMP_WORK"
os.makedirs(CARPETA_TEMP, exist_ok=True)

# VARIABLES DE SESIÓN
if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'sede_usuario' not in st.session_state: st.session_state['sede_usuario'] = None # <--- NUEVO   
if 'tipo_contrato' not in st.session_state: st.session_state['tipo_contrato'] = "Normal" # <--- NUEVO (Por defecto Normal)
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
            if orientation == 3: image = image.rotate(180, expand=True)
            elif orientation == 6: image = image.rotate(270, expand=True)
            elif orientation == 8: image = image.rotate(90, expand=True)
    except: pass
    return image

def optimizar_imagen(image, max_width=800):
    image = corregir_rotacion_imagen(image)
    width_percent = (max_width / float(image.size[0]))
    new_height = int((float(image.size[1]) * float(width_percent)))
    image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    if image.mode != 'RGB': image = image.convert('RGB')
    return image
    
def consultar_estado_dni_multisede(dni):
    """Busca el DNI en Lima y Provincia y retorna: Sede, Estado, TIPO"""
    try:
        wb = client_sheets.open_by_key(SHEET_ID)
        dni_buscado = str(dni).strip()
        
        # 1. Buscar en LIMA
        try:
            sh_lima = wb.worksheet("LIMA")
            dnis_lima = sh_lima.col_values(1)
            for i, valor in enumerate(dnis_lima):
                if str(valor).strip() == dni_buscado:
                    # Retornamos: (Sede, Estado, TIPO - Columna 4)
                    tipo = sh_lima.cell(i + 1, 4).value or "Normal" # Si está vacío, asume Normal
                    return "LIMA", sh_lima.cell(i + 1, 2).value, tipo
        except: pass 
        
        # 2. Buscar en PROVINCIA
        try:
            sh_prov = wb.worksheet("PROVINCIA")
            dnis_prov = sh_prov.col_values(1)
            for i, valor in enumerate(dnis_prov):
                if str(valor).strip() == dni_buscado:
                    tipo = sh_prov.cell(i + 1, 4).value or "Normal"
                    return "PROVINCIA", sh_prov.cell(i + 1, 2).value, tipo
        except: pass
    except: pass

    return None, None, None # No encontrado

def registrar_firma_sheet(dni, sede, nombre_archivo_pdf, link_firma, link_foto):
    """Registra datos y CONVIERTE LOS LINKS OBLIGATORIAMENTE"""
    try:
        wb = client_sheets.open_by_key(SHEET_ID)
        sh = wb.worksheet(sede)
        
        dnis_en_excel = sh.col_values(1)
        dni_buscado = str(dni).strip()
        nombre_trabajador = nombre_archivo_pdf.replace(dni_buscado, "").replace(".pdf", "").replace("-", "").strip()

        # --- FUNCIÓN DE LIMPIEZA AGRESIVA ---
        def obtener_link_thumbnail(url_sucia):
            # 1. Buscamos el ID entre las barras /d/ y /
            match = re.search(r"/d/([a-zA-Z0-9_-]+)", url_sucia)
            if match:
                file_id = match.group(1)
                # 2. Devolvemos SIEMPRE el link tipo thumbnail que sí funciona
                return f"https://drive.google.com/thumbnail?sz=w1000&id={file_id}"
            
            # 3. Intento secundario por si el link viene con id=
            match_id = re.search(r"id=([a-zA-Z0-9_-]+)", url_sucia)
            if match_id:
                file_id = match_id.group(1)
                return f"https://drive.google.com/thumbnail?sz=w1000&id={file_id}"
                
            return url_sucia # Si todo falla, devuelve el original

        # Limpiamos los links
        link_firma_clean = obtener_link_thumbnail(link_firma)
        link_foto_clean = obtener_link_thumbnail(link_foto)

        for i, valor_celda in enumerate(dnis_en_excel):
            if str(valor_celda).strip() == dni_buscado:
                fila = i + 1 
                hora_peru = datetime.utcnow() - timedelta(hours=5)
                fecha_fmt = hora_peru.strftime("%d/%m/%Y %H:%M:%S")
                
                sh.update_cell(fila, 2, "FIRMADO")
                sh.update_cell(fila, 3, fecha_fmt)
                sh.update_cell(fila, 5, nombre_trabajador)
                
                # Usamos los links limpios
                sh.update_cell(fila, 6, f'=IMAGE("{link_firma_clean}")')      
                sh.update_cell(fila, 9, f'=IMAGE("{link_foto_clean}")')       
                return True
        return False
    except Exception as e:
        st.error(f"Error Excel: {e}")
        return False
        
def buscar_archivo_drive(dni, folder_id):
    """Busca el PDF en la carpeta específica que le digamos (dinámica)"""
    try:
        query = f"'{folder_id}' in parents and name contains '{dni}' and mimeType = 'application/pdf' and trashed = false"
        results = service_drive.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if items: return items[0] 
        return None
    except: return None

def descargar_archivo_drive(file_id, nombre_destino):
    """Esta no cambia, pero la incluyo para mantener el orden"""
    try:
        request = service_drive.files().get_media(fileId=file_id)
        fh = io.FileIO(nombre_destino, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        return True
    except: return False

def borrar_archivo_drive(file_id):
    """Esta tampoco cambia, pero la incluyo"""
    try:
        service_drive.files().delete(fileId=file_id).execute()
        return True
    except: return False

def enviar_a_drive_script(ruta_archivo, nombre_archivo, folder_destino_id):
    """Envía el PDF al script, especificando la carpeta destino correcta"""
    try:
        with open(ruta_archivo, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Le mandamos también el folderId correcto
        payload = {
            "file": pdf_base64, 
            "filename": nombre_archivo, 
            "folderId": folder_destino_id 
        }
        requests.post(WEB_APP_URL, json=payload)
        return True
    except: return False

def enviar_a_drive_script_retorna_url(ruta_archivo, nombre_archivo, folder_destino_id):
    """Sube archivo y RETORNA el JSON con el Link (fileUrl)"""
    try:
        with open(ruta_archivo, "rb") as f:
            contenido_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        payload = {
            "file": contenido_base64, 
            "filename": nombre_archivo, 
            "folderId": folder_destino_id 
        }
        # AQUI ESTÁ LA MAGIA: Guardamos la respuesta en 'response'
        response = requests.post(WEB_APP_URL, json=payload)
        return response.json() # Retorna el diccionario con 'fileUrl'
    except: return None

def estampar_firma(pdf_path, imagen_firma, output_path, tipo_contrato="Normal"): # <--- ESTA ES LA NUEVA
    # Esta función ahora es INTELIGENTE. Busca las coordenadas según el tipo.
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    ANCHO, ALTO = 100, 50
    
    # 1. BUSCAMOS LA CONFIGURACIÓN PARA ESTE TIPO DE CONTRATO
    # Si el tipo no existe en el diccionario, usa {} (vacío) para no romper nada.
    config_coordenadas = COORDENADAS_MAESTRAS.get(tipo_contrato, {})
    
    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        num_pag = i + 1 
        
        # 2. VERIFICAMOS SI ESTA PÁGINA ESTÁ EN LA CONFIGURACIÓN DEL TIPO ACTUAL
        if num_pag in config_coordenadas:
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter, bottomup=True)
            # Dibujamos todas las firmas necesarias en esta página
            for (posX, posY) in config_coordenadas[num_pag]:
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
    
    X_FIRMA, Y_FIRMA = 110, 400
    W_FIRMA, H_FIRMA = 130, 130 
    
    X_FOTO, Y_FOTO = 290, 380
    W_FOTO, H_FOTO = 200, 150 
    
    X_FECHA, Y_FECHA = 150, 308 

    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        if i == total_paginas - 1: 
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter)
            try:
                # anchor='c' centra la firma en su caja.
                # preserveAspectRatio=True evita que se deforme/estire.
                c.drawImage(imagen_firma_path, X_FIRMA, Y_FIRMA, width=W_FIRMA, height=H_FIRMA, mask='auto', preserveAspectRatio=True, anchor='c')
            except: pass
            
            if imagen_foto_bytes:
                try:
                    image_bio = ImageReader(io.BytesIO(imagen_foto_bytes))
                    c.drawImage(image_bio, X_FOTO, Y_FOTO, width=W_FOTO, height=H_FOTO, preserveAspectRatio=True, anchor='c')
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
    st.markdown("**INGRESE SU NÚMERO DE DOCUMENTO PARA BUSCAR SU CONTRATO.**")
    
    with st.form("login_form"):
        dni_input = st.text_input("**DIGITE SU DNI**", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

    if submitted and dni_input:
        with st.spinner("**BUSCANDO EN BASE DE DATOS...**"):
            # Magia Multisede (Devuelve LIMA o PROVINCIA en mayúsculas)
            sede_encontrada, estado_sheet, tipo_encontrado = consultar_estado_dni_multisede(dni_input)
        
        if sede_encontrada:
            # Guardamos datos en sesión
            st.session_state['sede_usuario'] = sede_encontrada
            st.session_state['tipo_contrato'] = tipo_encontrado
            
            if estado_sheet == "FIRMADO":
                st.info(f"ℹ️ **EL DNI {dni_input} ({sede_encontrada}) YA REGISTRA UN CONTRATO FIRMADO.**")
                st.markdown("""**SI NECESITA UNA COPIA, CONTACTE A ADMINISTRACIÓN.**""")
            else:
                with st.spinner(f"**BUSCANDO CONTRATO EN {sede_encontrada}...**"):
                    # Buscamos usando la llave en MAYÚSCULAS
                    id_carpeta_busqueda = RUTAS_DRIVE[sede_encontrada]["PENDIENTES"]
                    archivo_drive = buscar_archivo_drive(dni_input, id_carpeta_busqueda)
                
                if archivo_drive:
                    # PROCESO DE DESCARGA
                    ruta_local = os.path.join(CARPETA_TEMP, archivo_drive['name'])
                    descargo_ok = descargar_archivo_drive(archivo_drive['id'], ruta_local)
                    if descargo_ok:
                        st.session_state['dni_validado'] = dni_input
                        st.session_state['archivo_id'] = archivo_drive['id'] 
                        st.session_state['archivo_nombre'] = archivo_drive['name']
                        st.session_state['firmado_ok'] = False
                        st.session_state['foto_bio'] = None
                        st.rerun()
                    else: st.error("**ERROR DE CONEXIÓN AL DESCARGAR EL DOCUMENTO. INTENTE NUEVAMENTE.**")
                else: 
                    # 🔴 MENSAJE LIMPIO PARA EL USUARIO (SIN CÓDIGOS RAROS)
                    st.error(f"**❌ CONTRATO NO UBICADO (VERIFIQUE QUE SU DNI ESTÉ CORRECTAMENTE ESCRITO), SI ESTÁ TODO CORRECTO, CONTACTE AL ÁREA DE ADMINISTRACIÓN DE PERSONAL.**")
                    st.markdown("**❌ CONTRATO NO UBICADO (VERIFIQUE QUE SU DNI ESTÉ CORRECTAMENTE ESCRITO), SI ESTÁ TODO CORRECTO, CONTACTE AL ÁREA DE ADMINISTRACIÓN DE PERSONAL.**")
        else:
            st.error("**❌ CONTRATO NO UBICADO (VERIFIQUE QUE SU DNI ESTÉ CORRECTAMENTE ESCRITO), SI ESTÁ TODO CORRECTO, CONTACTE AL ÁREA DE ADMINISTRACIÓN DE PERSONAL.**")
    
    st.markdown("---")
    st.subheader("❓ Preguntas Frecuentes")
    with st.expander("💰 ¿Por qué mi sueldo figura diferente en el contrato?"):
        st.markdown("En el contrato de trabajo se estipula únicamente la **Remuneración Básica** correspondiente al puesto. El monto informado durante su reclutamiento es el **Sueldo Bruto** (básico + otros conceptos). *Lo verá reflejado en su **boleta de pago** a fin de mes.*")
    with st.expander("🕒 ¿Por qué el contrato dice 8hrs si mi puesto de trabajo es de 12hrs?"):
        st.markdown("La ley peruana establece que la **Jornada Ordinaria** base es de 8 horas diarias. Si su turno es de 12 horas, las 4 horas restantes se consideran y pagan como **HORAS EXTRAS**. *Este pago adicional se verá reflejado en su **boleta de pago** a fin de mes.*")
    # === BOTÓN PRO DE WHATSAPP (Soporte Rápido) ===
    # ¡OJO GORILA! CAMBIA ESTE NÚMERO POR EL TUYO (Con código 51 delante si es Perú)
    celular_soporte = "51958840140" 
    
    # Preparamos el mensaje automático con el DNI que escribió
    mensaje_wsp = f"Hola, soy el colaborador con DNI {dni_input if dni_input else 'PENDIENTE'}. Tengo una duda en el Portal de Contratos."
    mensaje_encoded = requests.utils.quote(mensaje_wsp)
    link_wsp = f"https://wa.me/{celular_soporte}?text={mensaje_encoded}"

    # Renderizamos el Botón Verde
    st.markdown(f"""
        <a href="{link_wsp}" target="_blank" style="text-decoration: none;">
            <div style="
                background-color: #25D366; 
                color: white; 
                padding: 15px; 
                border-radius: 10px; 
                text-align: center; 
                font-weight: bold; 
                font-size: 18px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                gap: 10px; 
                box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
                transition: transform 0.1s;
                margin-top: 10px;
            ">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="white"><path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/></svg>
                <span>¿NECESITAS AYUDA? ESCRÍBENOS AQUÍ</span>
            </div>
        </a>
    """, unsafe_allow_html=True)
else:
    # 2. APP PRINCIPAL
    nombre_archivo = st.session_state['archivo_nombre']
    ruta_pdf_local = os.path.join(CARPETA_TEMP, nombre_archivo)
    
    # === PANTALLA DE ÉXITO (YA FIRMADO) ===
    if st.session_state['firmado_ok']:
        st.success("**✅ ¡FIRMA Y BIOMETRÍA REGISTRADAS!**")
        st.info("Contrato guardado exitosamente.")
        ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
        if os.path.exists(ruta_salida_firmado):
            with open(ruta_salida_firmado, "rb") as f:
                st.download_button("**📥 DESCARGAR CONTRATO FIRMADO**", f, file_name=f"FIRMADO_{nombre_archivo}", mime="application/pdf", type="primary")
        
        st.markdown("---")
        if st.button("🏠 SALIR"):
            st.session_state['dni_validado'] = None
            st.session_state['firmado_ok'] = False
            st.rerun()

    # === PANTALLA DE PROCESO (LECTURA + FOTO + FIRMA) ===
    else:
        st.success(f"Hola, **{nombre_archivo.replace('.pdf','')}**")
        st.info("👇 **SIGA LOS PASOS 1, 2 Y 3 PARA COMPLETAR SU FIRMA.**")
        
        # --- PASO 1: LECTURA ULTRA PRO (ZERO FLASH - MODO NETFLIX) ---
        st.markdown("### 1. Lectura del Contrato")
        st.caption("**TOQUE LA IMAGEN PARA LEER EN PANTALLA COMPLETA Y HACER ZOOM CON LOS DEDOS**.")

        try:
            # 1. CARGA MASIVA: Preparamos TODAS las páginas de una vez
            # Esto elimina el parpadeo porque el navegador ya tendrá todas las fotos listas.
            doc = fitz.open(ruta_pdf_local)
            total_paginas = len(doc)
            
            # Creamos una lista de Javascript con todas las imágenes codificadas
            lista_imagenes_js = []
            for i in range(total_paginas):
                pagina = doc[i]
                # DPI 200 es suficiente para pantalla y carga rápido. 300 puede ser pesado si son muchas hojas.
                pix = pagina.get_pixmap(dpi=200) 
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode('utf-8')
                lista_imagenes_js.append(f"'data:image/png;base64,{b64}'")
            
            # Convertimos la lista de Python a un String de Array Javascript: ['data...', 'data...']
            js_array_string = "[" + ",".join(lista_imagenes_js) + "]"

            # --- CÓDIGO HTML + JS (EL MOTOR FERRARI) ---
            # Ya no hay botones Python ocultos. Todo ocurre en el navegador del cliente.
            html_zero_flash = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <link href="https://cdnjs.cloudflare.com/ajax/libs/viewerjs/1.11.6/viewer.min.css" rel="stylesheet">
                <script src="https://cdnjs.cloudflare.com/ajax/libs/viewerjs/1.11.6/viewer.min.js"></script>
                <style>
                    body {{ margin: 0; padding: 0; font-family: sans-serif; }}
                    
                    .contrato-container {{
                        text-align: center;
                        border: 1px solid #ddd;
                        border-radius: 8px;
                        padding: 5px;
                        background: white;
                        cursor: zoom-in;
                    }}
                    #imagen-contrato {{
                        max-width: 100%;
                        height: auto;
                        max-height: 450px;
                        display: block;
                        margin: 0 auto;
                        object-fit: contain;
                    }}
                    
                    /* BARRA DE NAVEGACIÓN PEGADA Y ESTILIZADA */
                    .nav-container-pro {{
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 15px;
                        padding: 5px;
                        width: 100%;
                        user-select: none;
                        margin-top: 5px; 
                    }}
                    .nav-btn-pro {{
                        font-size: 28px;
                        font-weight: bold;
                        padding: 0 15px;
                        cursor: pointer;
                        transition: transform 0.1s;
                        line-height: 1;
                        color: #FF4B4B; /* Rojo Streamlit por defecto */
                    }}
                    .nav-btn-pro.disabled {{
                        color: #ccc;
                        cursor: default;
                    }}
                    .nav-btn-pro:active:not(.disabled) {{ transform: scale(0.8); }}
                    
                    .nav-text-capsule {{
                        background-color: #f0f2f6;
                        padding: 8px 20px;
                        border-radius: 20px;
                        font-weight: 600;
                        color: #444;
                        font-size: 14px;
                        min-width: 120px;
                        text-align: center;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                    }}
                    .viewer-title {{ display: none; }}
                </style>
            </head>
            <body>
                <div class="contrato-container">
                    <img id="imagen-contrato" src="" alt="Contrato">
                    <div style="margin-top:2px; color:#999; font-size:11px;">👆 <i>**RECUERDE HACER ZOOM CON LOS DEDOS**</i></div>
                </div>

                <div class="nav-container-pro">
                    <div class="nav-btn-pro" id="btn-prev" onclick="cambiarPagina(-1)">❮</div>
                    <div class="nav-text-capsule" id="contador-paginas">Cargando...</div>
                    <div class="nav-btn-pro" id="btn-next" onclick="cambiarPagina(1)">❯</div>
                </div>

                <script>
                    // 1. RECIBIMOS TODAS LAS IMÁGENES DESDE PYTHON
                    const paginas = {js_array_string};
                    let indiceActual = 0;
                    const total = paginas.length;
                    
                    const imgElement = document.getElementById('imagen-contrato');
                    const txtContador = document.getElementById('contador-paginas');
                    const btnPrev = document.getElementById('btn-prev');
                    const btnNext = document.getElementById('btn-next');
                    let viewer = null;

                    // 2. FUNCIÓN PARA ACTUALIZAR LA VISTA (INSTANTÁNEA)
                    function actualizarVista() {{
                        // Cambiamos la fuente de la imagen (Magia sin parpadeo)
                        imgElement.src = paginas[indiceActual];
                        
                        // Actualizamos texto
                        txtContador.innerText = `Pág. ${{indiceActual + 1}} / ${{total}}`;
                        
                        // Actualizamos colores de botones (Gris si es el final)
                        if (indiceActual === 0) {{
                            btnPrev.classList.add('disabled');
                        }} else {{
                            btnPrev.classList.remove('disabled');
                        }}
                        
                        if (indiceActual === total - 1) {{
                            btnNext.classList.add('disabled');
                        }} else {{
                            btnNext.classList.remove('disabled');
                        }}

                        // Si el visor de zoom está abierto, hay que actualizarlo también
                        if (viewer) {{
                            viewer.update();
                        }}
                    }}

                    // 3. FUNCIÓN DE NAVEGACIÓN
                    window.cambiarPagina = function(direccion) {{
                        const nuevoIndice = indiceActual + direccion;
                        if (nuevoIndice >= 0 && nuevoIndice < total) {{
                            indiceActual = nuevoIndice;
                            actualizarVista();
                        }}
                    }};

                    // 4. INICIALIZAR AL CARGAR
                    // Cargamos la página 0 al inicio
                    actualizarVista();

                    // Iniciamos el Zoom Potente
                    viewer = new Viewer(imgElement, {{
                        toolbar: {{ zoomIn:1, zoomOut:1, oneToOne:1, reset:1, rotateLeft:0, rotateRight:0, flipHorizontal:0, flipVertical:0 }},
                        navbar: 0, 
                        title: 0, 
                        tooltip: 0, 
                        movable: 1, 
                        zoomable: 1, 
                        rotatable: 0, 
                        scalable: 0, 
                        inline: false, 
                        transition: 0, 
                        backdrop: 'rgba(0,0,0,0.9)' 
                    }});
                </script>
            </body>
            </html>
            """
            
            # Renderizamos todo (Altura 600px para que quepa bien)
            st.components.v1.html(html_zero_flash, height=600, scrolling=False)

        except Exception as e:
            st.error(f"Error cargando visor: {e}")
        # PASO 2: FOTO HÍBRIDA
        st.markdown("---")
        st.subheader("2. Foto de Identidad")
        
        if st.session_state['foto_bio'] is None:
            usar_webcam = st.checkbox("💻 **¿ESTÁS EN COMPUTADORA / LAPTOP? CLICK AQUÍ PARA USAR LA CÁMARA WEB**", value=False)
            foto_input = None
            if usar_webcam:
                foto_input = st.camera_input("📸 TOMAR FOTO", label_visibility="visible")
            else:
                st.warning("📸 **SI ESTÁS EN CELULAR, TOCA EL RECUADRO DE ABAJO PARA ABRIR LA CÁMARA:**")
                foto_input = st.file_uploader("📸 TOMAR FOTO (CÁMARA)", type=["jpg", "png", "jpeg"], label_visibility="collapsed")
            
            if foto_input is not None:
                with st.spinner("Procesando foto..."):
                    image_raw = Image.open(foto_input)
                    image_opt = optimizar_imagen(image_raw)
                    img_byte_arr = io.BytesIO()
                    image_opt.save(img_byte_arr, format='JPEG', quality=85)
                    st.session_state['foto_bio'] = img_byte_arr.getvalue()
                    st.rerun()    
        else:
            col_a, col_b = st.columns([1,3])
            with col_a: st.image(st.session_state['foto_bio'], width=100)
            with col_b:
                st.success("✅ Foto guardada")
                if st.button("🔄 Cambiar Foto"):
                    st.session_state['foto_bio'] = None
                    st.rerun()

        # PASO 3: FIRMA
        st.markdown("---")
        st.subheader("3. Firma y Conformidad")
        
        if st.session_state['foto_bio'] is None:
            st.error("⚠️ PRIMERO DEBE TOMARSE LA FOTO EN EL PASO 2 👆")
        else:
            st.caption("**DIBUJE SU FIRMA. EN CASO FALLÓ, USE LA PAPELERA 🗑️ PARA BORRAR**")
            with st.form(key="formulario_firma", clear_on_submit=False):
                canvas_result = st_canvas(
                    stroke_width=2, stroke_color="#000000", background_color="#ffffff", 
                    height=200, width=340, drawing_mode="freedraw", 
                    display_toolbar=True, key=f"canvas_{st.session_state['canvas_key']}"
                )
                st.write("") 
                enviar_firma = st.form_submit_button("✅ FINALIZAR Y FIRMAR", type="primary", use_container_width=True)

            if enviar_firma:
                # === 🛡️ INICIO PANTALLA DE CARGA TOTAL (ELEGANTE) ===
                st.markdown("""
<style>
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>
<div style="
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(8px);
    z-index: 999999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
">
    <div style="
        border: 10px solid #f3f3f3; 
        border-top: 10px solid #FF4B4B; 
        border-radius: 50%; 
        width: 80px; 
        height: 80px; 
        animation: spin 1s linear infinite;
        margin-bottom: 20px;
    "></div>
    <div style="font-size: 24px; font-weight: bold; color: #333; font-family: sans-serif;">
        PROCESANDO DOCUMENTO...
    </div>
    <div style="font-size: 16px; color: #666; margin-top: 10px; font-family: sans-serif;">
        Por favor espere, no cierre la ventana.
    </div>
</div>
""", unsafe_allow_html=True)
                # === 🛡️ FIN PANTALLA DE CARGA ===

                if canvas_result.image_data is not None:
                    img_data = canvas_result.image_data.astype('uint8')
                    if img_data[:, :, 3].sum() == 0:
                        st.warning("**⚠️ EL RECUADRO ESTÁ VACIO. POR FAVOR FIRME**")
                    else:
                        ruta_firma = os.path.join(CARPETA_TEMP, "firma.png")
                        ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
                        
                        try:
                            # 1. Guardar la imagen de la firma temporalmente
                            img = Image.fromarray(img_data, 'RGBA')
                            data = img.getdata()
                            newData = []
                            es_blanco = True 
                            for item in data:
                                if item[0] < 200: es_blanco = False 
                                if item[0] > 230 and item[1] > 230 and item[2] > 230:
                                    newData.append((255, 255, 255, 0))
                                else: newData.append(item)
                            
                            if es_blanco: 
                                st.warning("**⚠️ EL RECUADRO PARECE VACIO.**")
                            else:
                                img.putdata(newData)
                                img.save(ruta_firma, "PNG")
                                
                                # 2. Estampamos usando el TIPO detectado (CORRECCIÓN APLICADA AQUÍ)
                                tipo_actual = st.session_state['tipo_contrato']
                                
                                # Estampa firmas intermedias (según coordenadas maestras)
                                estampar_firma(ruta_pdf_local, ruta_firma, ruta_salida_firmado, tipo_actual)
                                
                                # Estampa la última página (Foto + Fecha + Firma final)
                                # AQUÍ ESTABA EL ERROR: Ahora usamos el nombre correcto 'pagina9'
                                estampar_firma_y_foto_pagina9(ruta_salida_firmado, ruta_firma, st.session_state['foto_bio'], ruta_salida_firmado)
                                
                                # ---------------------------------------------------------
                                # 🚀 INICIO DEL PASO 3: SUBIDA TRIPLE Y REGISTRO
                                # ---------------------------------------------------------
                                
                                # ---------------------------------------------------------
                                # 1. PREPARAMOS LOS DESTINOS
                                # ---------------------------------------------------------
                                sede_actual = st.session_state['sede_usuario']
                    
                    # A) CONTRATOS (PDF) -> A la carpeta de la Sede (Ej. FIRMADOS_PROVINCIA)
                    id_carpeta_contratos = RUTAS_DRIVE[sede_actual]["FIRMADOS"]
                    
                    # B) FOTOS Y FIRMAS -> A TU CARPETA ESPECÍFICA
                    # ¡¡¡PEGA AQUÍ EL ID DE TU CARPETA FIRMAS_FOTOS!!!
                    ID_CARPETA_FOTOS = "1k7I6Dw4dJB3waMufAFQvIP9M7KTMMg0P" # <--- EJEMPLO, PON EL TUYO

                    st.write(f"🚀 Subiendo documentos...")

                    # 2. SUBIMOS EL PDF -> CARPETA DE CONTRATOS
                    resp_pdf = enviar_a_drive_script_retorna_url(ruta_salida_firmado, nombre_archivo, id_carpeta_contratos)
                    
                    # 3. SUBIMOS LA FIRMA (PNG) -> CARPETA DE FOTOS
                    nombre_firma_png = f"FIRMA_{st.session_state['dni_validado']}.png"
                    resp_firma = enviar_a_drive_script_retorna_url(ruta_firma, nombre_firma_png, ID_CARPETA_FOTOS)
                    
                    # 4. SUBIMOS LA FOTO (JPG) -> CARPETA DE FOTOS
                    ruta_foto_temp = os.path.join(CARPETA_TEMP, "FOTO_TEMP.jpg")
                    with open(ruta_foto_temp, "wb") as f_foto:
                        f_foto.write(st.session_state['foto_bio'])
                    
                    nombre_foto_jpg = f"FOTO_{st.session_state['dni_validado']}.jpg"
                    resp_foto = enviar_a_drive_script_retorna_url(ruta_foto_temp, nombre_foto_jpg, ID_CARPETA_FOTOS)

                    # 5. REGISTRAMOS EN EXCEL
                    if resp_pdf and resp_firma and resp_foto:
                        link_firma_raw = resp_firma.get("fileUrl", "")
                        link_foto_raw = resp_foto.get("fileUrl", "")
                        
                        registro_ok = registrar_firma_sheet(
                            st.session_state['dni_validado'], 
                            sede_actual,
                            st.session_state['archivo_nombre'], 
                            link_firma_raw,                     
                            link_foto_raw                       
                        )
                        
                        if registro_ok:
                            st.success("✅ ¡TODO LISTO! FIRMA REGISTRADA.")
                            st.session_state['firmado_ok'] = True
                            borrar_archivo_drive(st.session_state['archivo_id']) 
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("❌ Falló el registro en Excel.")
                    else:
                        st.error("❌ Error al subir archivos a Drive.")

                        # === 🛡️ CIERRE DE SEGURIDAD (Esto evita el SyntaxError) ===
                        except Exception as e:
                            st.error(f"❌ ERROR TÉCNICO: {e}")
                        finally:
                            if os.path.exists(ruta_firma): os.remove(ruta_firma)
                else:
                    st.warning("⚠️ Falta su firma.")
                
        if st.button("⬅️ **IR A LA PÁGINA PRINCIPAL**"):
            st.session_state['dni_validado'] = None
            st.rerun()



