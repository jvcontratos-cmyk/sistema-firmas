import streamlit as st
import os
import shutil
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
# Import necesario para procesar la foto
from reportlab.lib.utils import ImageReader 
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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Portal de Contratos", 
    page_icon="✍️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS LIMPIO ---
# --- CSS MAESTRO (LIMPIEZA + ZOOM ROJO + BOTÓN CÁMARA FIXED) ---
st.markdown("""
    <style>
    /* 1. Ocultar elementos base de Streamlit */
    header {visibility: hidden !important;}
    [data-testid="stHeader"] {display: none !important;}
    footer {display: none !important; visibility: hidden !important; height: 0px !important;}
    .stAppDeployButton, [data-testid="stToolbar"], div[class*="viewerBadge"] {display: none !important;}
    #MainMenu {display: none !important;}
    .block-container {padding-top: 1rem !important; padding-bottom: 0rem !important;}
    body::after {content: none !important;}
    
    /* 2. BOTÓN DE ZOOM (PANTALLA COMPLETA) - ROJO Y GRANDE */
    button[title="View fullscreen"] {
        display: block !important;
        background-color: rgba(255, 75, 75, 0.9) !important;
        width: 50px !important;
        height: 50px !important;
        border-radius: 50% !important;
        color: white !important;
        transform: scale(1.2);
        right: 15px !important;
        top: 15px !important;
        z-index: 9999 !important;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.3) !important;
    }

    /* 3. ESTILO PARA EL ACORDEÓN (VER CONTRATO) */
    .streamlit-expanderHeader {
        background-color: #f0f2f6;
        border-radius: 10px;
        font-weight: bold;
    }

    /* 4. REPARACIÓN TOTAL DEL BOTÓN DE CÁMARA */
    
    /* A) Ocultar TODAS las instrucciones de texto (Drag & Drop, Limit, etc) */
    [data-testid='stFileUploaderDropzone'] span, 
    [data-testid='stFileUploaderDropzone'] small,
    [data-testid='stFileUploaderDropzone'] div::before {
        display: none !important;
    }
    
    /* B) Ajustar el contenedor para que solo se vea el botón */
    [data-testid='stFileUploaderDropzone'] {
        padding: 0px !important;
        min-height: 0px !important;
        border: none !important;
        background-color: transparent !important;
    }
    
    /* C) Estilo del Botón (Hacerlo ancho y ocultar texto inglés) */
    [data-testid="stFileUploader"] button {
        width: 100% !important; /* Ocupa todo el ancho */
        color: transparent !important; /* Oculta "Browse files" */
        background-color: #f0f2f6 !important; /* Color de fondo gris claro */
        border: 1px solid #d0d0d0 !important;
        height: 50px !important; /* Altura fija para que no se deforme */
        position: relative !important;
    }
    
    /* D) Poner el texto en Español CENTRADO MATEMÁTICAMENTE */
    [data-testid="stFileUploader"] button::after {
        content: "📷 TOMAR FOTO (CÁMARA)";
        color: #31333F !important;
        font-size: 16px !important;
        font-weight: bold !important;
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%); /* Esto centra el texto a la fuerza */
        width: 100%;
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
# Variable para guardar la foto temporalmente
if 'foto_bio' not in st.session_state: st.session_state['foto_bio'] = None 

# --- FUNCIONES ---

def consultar_estado_dni(dni):
    try:
        sh = client_sheets.open_by_key(SHEET_ID).sheet1
        # ESTRATEGIA BLINDADA: Bajamos toda la columna A y buscamos manual
        # Esto arregla el error si en Excel está como número y aquí como texto
        dnis_en_excel = sh.col_values(1) 
        dni_buscado = str(dni).strip()
        
        for i, valor_celda in enumerate(dnis_en_excel):
            if str(valor_celda).strip() == dni_buscado:
                # Retornamos el valor de la columna 2 (ESTADO) de esa fila
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
                fila = i + 1 # Sumamos 1 porque Python cuenta desde 0
                hora_peru = datetime.utcnow() - timedelta(hours=5)
                fecha_fmt = hora_peru.strftime("%Y-%m-%d %H:%M:%S")
                
                # Escribimos en Columna 2 (Estado) y 3 (Fecha)
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

# --- FUNCIÓN PÁGINA 9 (AJUSTE FINAL: FECHA +5pt DERECHA) ---
def estampar_firma_y_foto_pagina9(pdf_path, imagen_firma_path, imagen_foto_bytes, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    
    # === COORDENADAS ===
    # FIRMA (Cuadro Izquierdo) - INTACTA
    X_FIRMA, Y_FIRMA = 100, 370
    W_FIRMA, H_FIRMA = 230, 150
    
    # FOTO (Cuadro Derecho) - INTACTA
    X_FOTO, Y_FOTO = 290, 380
    W_FOTO, H_FOTO = 230, 150 
    
    # FECHA (Abajo Izquierda) - AJUSTADO: X=150 (Antes 145)
    X_FECHA, Y_FECHA = 150, 308 
    # ===================

    for i in range(total_paginas):
        pagina = pdf_original.pages[i]
        
        # SI ES LA ÚLTIMA PÁGINA
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
            c.drawString(X_FECHA, Y_FECHA, f"{hora_actual}")
            
            c.save()
            packet.seek(0)
            sello = PdfReader(packet)
            pagina.merge_page(sello.pages[0])
            
        pdf_writer.add_page(pagina)
    
    with open(output_path, "wb") as f: pdf_writer.write(f)

def mostrar_pdf_como_imagenes(ruta_pdf):
    try:
        doc = fitz.open(ruta_pdf)
        for pagina in doc:
            # Aumentamos calidad a 220 para que se lea bien en el iPhone al hacer zoom
            pix = pagina.get_pixmap(dpi=220)
            st.image(pix.tobytes("png"), use_container_width=True)
    except: st.error("Error visualizando documento.")

# --- INTERFAZ CENTRAL ---
st.title("✍️ Portal de Contratos")

if st.session_state['dni_validado'] is None:
    st.markdown("Ingrese su documento para buscar su contrato.")
    with st.form("login_form"):
        dni_input = st.text_input("DIGITE SU DNI", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

# === LÓGICA DE VALIDACIÓN CORREGIDA ===
    if submitted and dni_input:
        with st.spinner("Conectando con base de datos..."):
            # 1. VERIFICAMOS PRIMERO EN EL EXCEL
            estado_sheet = consultar_estado_dni(dni_input)
        
        # 2. SI YA FIRMÓ: LE PONEMOS EL FRENO DE MANO
        if estado_sheet == "FIRMADO":
            st.info(f"ℹ️ El DNI {dni_input} ya registra un contrato firmado.")
            st.markdown("""
            **Si necesita una copia de su contrato** o cree que esto es un error, 
            por favor **contacte al área de Recursos Humanos**.
            """)
            # AL NO PONER NADA MÁS AQUÍ, EL CÓDIGO SE DETIENE Y NO DEJA AVANZAR
        
        # 3. SI NO HA FIRMADO: BUSCAMOS EN DRIVE
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
                st.error("❌ Contrato no ubicado (Verifique que su DNI esté correcto en la lista).")
    # === HASTA AQUÍ TERMINA EL BLOQUE A PEGAR ===
    # FAQ
    st.markdown("---")
    st.subheader("❓ Preguntas Frecuentes")
    with st.expander("💰 ¿Por qué mi sueldo figura diferente en el contrato?"):
        st.markdown("En el contrato de trabajo se estipula únicamente la **Remuneración Básica** correspondiente al puesto. El monto informado durante su reclutamiento es el **Sueldo Bruto** (básico + otros conceptos). *Lo verá reflejado en su **boleta de pago** a fin de mes.*")
    with st.expander("🕒 ¿Por qué el contrato dice 8hrs si trabajo 12hrs?"):
        st.markdown("La ley peruana establece que la **Jornada Ordinaria** base es de 8 horas diarias. Si su turno es de 12 horas, las 4 horas restantes se consideran y pagan como **HORAS EXTRAS**. *Este pago adicional se verá reflejado en su **boleta de pago** a fin de mes.*")
    st.info("📞 **¿Dudas adicionales?** Contacte al área de Administración de Personal.")

else:
    nombre_archivo = st.session_state['archivo_nombre']
    ruta_pdf_local = os.path.join(CARPETA_TEMP, nombre_archivo)
    
    # PANTALLA DE ÉXITO (YA FIRMADO)
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

    # PANTALLA DE FIRMA (PASOS 1, 2 y 3)
    else:
        st.success(f"Hola, **{nombre_archivo.replace('.pdf','')}**")
        st.info("👇 **Siga los pasos 1, 2 y 3 para completar su ingreso.**")
        
        # --- PASO 1: CONTRATO (COLAPSABLE / ACORDEÓN) ---
        # "expanded=False" hace que empiece cerrado para que no estorbe en celulares
        with st.expander("📄 1. CLIC AQUÍ PARA LEER EL CONTRATO (ABRIR/CERRAR)", expanded=False):
            st.info("🔍 Puede ampliar las páginas usando el botón ROJO en la esquina.")
            with st.container(height=500, border=True):
                if os.path.exists(ruta_pdf_local):
                    mostrar_pdf_como_imagenes(ruta_pdf_local)
        
        # --- PASO 2: FOTO (MÉTODO ROBUSTO - BOTÓN NATIVO) ---
        st.markdown("---")
        st.subheader("2. Foto de Identidad")
        
        if st.session_state['foto_bio'] is None:
            st.warning("📸 Toque el botón y seleccione **'Cámara'**:")
            # Usamos file_uploader pero etiquetado para que usen la cámara
            foto_input = st.file_uploader("📸 TOMAR FOTO (CÁMARA)", type=["jpg", "png", "jpeg"], label_visibility="collapsed")
            if foto_input is not None:
                st.session_state['foto_bio'] = foto_input.getvalue()
                st.rerun()
        else:
            col_a, col_b = st.columns([1,3])
            with col_a:
                st.image(st.session_state['foto_bio'], width=100)
            with col_b:
                st.success("✅ Foto guardada")
                if st.button("🔄 Cambiar Foto"):
                    st.session_state['foto_bio'] = None
                    st.rerun()

        # --- PASO 3: FIRMA DIGITAL (SIN PARPADEO) ---
        st.markdown("---")
        st.subheader("3. Firma y Conformidad")
        
        # Candado: Solo deja firmar si ya hay foto
        if st.session_state['foto_bio'] is None:
            st.error("⚠️ Primero debe tomarse la foto en el paso 2 👆")
        else:
            st.caption("Dibuje su firma. Use la **Papelera 🗑️** de la barra para borrar si se equivoca.")
            
            # === AQUÍ EMPIEZA LA "CAJA FUERTE" (FORMULARIO) ===
            # Esto congela la pantalla para que no parpadee mientras dibujan
            with st.form(key="formulario_firma", clear_on_submit=False):
                
                # El canvas está DENTRO del form. 
                canvas_result = st_canvas(
                    stroke_width=2, 
                    stroke_color="#000000", 
                    background_color="#ffffff", 
                    height=200, 
                    width=600, 
                    drawing_mode="freedraw",
                    # ¡AQUÍ ESTÁ LA BASURITA! True activa la barra con la papelera
                    display_toolbar=True, 
                    key=f"canvas_{st.session_state['canvas_key']}"
                )
                
                st.write("") # Espacio visual
                
                # ESTE BOTÓN ENVÍA TODO DE GOLPE (Solo parpadea 1 vez aquí al final)
                enviar_firma = st.form_submit_button("✅ FINALIZAR Y FIRMAR", type="primary", use_container_width=True)

            # === LÓGICA DE GUARDADO (FUERA DEL FORM) ===
            if enviar_firma:
                if canvas_result.image_data is not None:
                    # Detectar si está vacío (Anti-Trampa)
                    img_data = canvas_result.image_data.astype('uint8')
                    # Convertimos a imagen para analizar
                    img_temp = Image.fromarray(img_data)
                    # Convertimos a escala de grises para ver si hay trazos
                    # (Si la imagen es pura transparencia o blanco, el resultado es uniforme)
                    # Una forma rápida: sumar los valores del canal Alpha (transparencia)
                    # Si todo es transparente (0), no han dibujado nada.
                    
                    # Lógica simplificada de validación visual
                    if img_data[:, :, 3].sum() == 0:
                        st.warning("⚠️ El recuadro está vacío. Por favor firme.")
                    else:
                        ruta_firma = os.path.join(CARPETA_TEMP, "firma.png")
                        ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
                        
                        with st.spinner("⏳ Guardando contrato..."):
                            try:
                                # 1. Procesar Firma (Volver transparente el fondo)
                                img = Image.fromarray(img_data, 'RGBA')
                                data = img.getdata()
                                newData = []
                                es_blanco = True # Asumimos que es blanco hasta encontrar un pixel oscuro
                                for item in data:
                                    if item[0] < 200: es_blanco = False 
                                    if item[0] > 230 and item[1] > 230 and item[2] > 230:
                                        newData.append((255, 255, 255, 0))
                                    else:
                                        newData.append(item)
                                
                                if es_blanco:
                                    st.warning("⚠️ El recuadro parece vacío. Por favor firme bien.")
                                else:
                                    img.putdata(newData)
                                    img.save(ruta_firma, "PNG")
                                    
                                    # 2. Estampar
                                    estampar_firma(ruta_pdf_local, ruta_firma, ruta_salida_firmado)
                                    estampar_firma_y_foto_pagina9(ruta_salida_firmado, ruta_firma, st.session_state['foto_bio'], ruta_salida_firmado)
                                    
                                    # 3. Enviar
                                    enviar_a_drive_script(ruta_salida_firmado, nombre_archivo)
                                    
                                    if registrar_firma_sheet(st.session_state['dni_validado']):
                                        st.session_state['firmado_ok'] = True
                                        borrar_archivo_drive(st.session_state['archivo_id'])
                                        st.balloons()
                                        st.rerun()
                                    else:
                                        st.error("⚠️ Error de conexión con Excel.")
                            
                            except Exception as e:
                                st.error(f"Error técnico: {e}")
                            finally:
                                if os.path.exists(ruta_firma): os.remove(ruta_firma)
                else:
                    st.warning("⚠️ Falta su firma.")

        if st.button("⬅️ Cancelar"):
            st.session_state['dni_validado'] = None
            st.rerun()


