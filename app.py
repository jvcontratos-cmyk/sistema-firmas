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

# --- CSS PERSONALIZADO (TEXTO PLANO PARA EVITAR ERRORES) ---
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
        content: "📷 TOCAR AQUÍ"; 
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
        if items: return items[0] 
        return None
    except: return None

def descargar_archivo_drive(file_id, nombre_destino):
    try:
        request = service_drive.files().get_media(fileId=file_id)
        fh = io.FileIO(nombre_destino, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
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
    st.markdown("Ingrese su documento para buscar su contrato.")
    
    with st.form("login_form"):
        dni_input = st.text_input("DIGITE SU DNI", max_chars=15)
        submitted = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)

    if submitted and dni_input:
        with st.spinner("Buscando..."):
            estado_sheet = consultar_estado_dni(dni_input)
        
        if estado_sheet == "FIRMADO":
            st.info(f"ℹ️ El DNI {dni_input} ya registra un contrato firmado.")
            st.markdown("""**Si necesita una copia de su contrato**, contacte al área de Administración de Personal.""")
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
                else: st.error("Error al descargar el documento.")
            else: st.error("❌ Contrato no ubicado.")
    
    st.markdown("---")
    st.subheader("❓ Preguntas Frecuentes")
    with st.expander("💰 ¿Por qué mi sueldo figura diferente en el contrato?"):
        st.markdown("En el contrato de trabajo se estipula únicamente la **Remuneración Básica**. El **Sueldo Bruto** (básico + bonos) se verá en su **boleta de pago**.")
    st.info("📞 **¿Dudas?** Contacte al área de Administración de Personal.")

    # --- INTERFAZ CENTRAL (PARTE INFERIOR) ---
else:
    nombre_archivo = st.session_state['archivo_nombre']
    ruta_pdf_local = os.path.join(CARPETA_TEMP, nombre_archivo)
    
    # === PANTALLA DE ÉXITO (YA FIRMADO) ===
    if st.session_state['firmado_ok']:
        st.success("✅ ¡Firma y Biometría registradas!")
        st.info("Contrato guardado exitosamente.")
        ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
        if os.path.exists(ruta_salida_firmado):
            with open(ruta_salida_firmado, "rb") as f:
                st.download_button("📥 DESCARGAR CONTRATO FIRMADO", f, file_name=f"FIRMADO_{nombre_archivo}", mime="application/pdf", type="primary")
        
        st.markdown("---")
        if st.button("🏠 SALIR"):
            st.session_state['dni_validado'] = None
            st.session_state['firmado_ok'] = False
            st.rerun()

    # === PANTALLA DE PROCESO (LECTURA + FOTO + FIRMA) ===
    else:
        st.success(f"Hola, **{nombre_archivo.replace('.pdf','')}**")
        st.info("👇 **SIGA LOS PASOS 1, 2 Y 3 PARA COMPLETAR SU FIRMA.**")
        
        # --- PASO 1: LECTURA ULTRA PRO (CON VIEWER.JS) ---
        st.markdown("### 1. Lectura del Contrato")
        st.caption("*TOQUE LA IMAGEN PARA LEER EN PANTALLA COMPLETA.*.")

        # 1. Preparamos la imagen de la página actual
        try:
            doc = fitz.open(ruta_pdf_local)
            total_paginas = len(doc)
            pagina = doc[st.session_state['pagina_actual']]
            # Calidad ALTA (300 DPI) para que al hacer zoom se vea nítido
            pix = pagina.get_pixmap(dpi=300) 
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            
            # 2. INYECCIÓN DE CÓDIGO NUCLEAR (HTML + JS + CSS EXTERNO)
            # Esto carga la librería Viewer.js desde internet sin instalar nada
            componente_visualizador = f"""
            <link href="https://cdnjs.cloudflare.com/ajax/libs/viewerjs/1.11.6/viewer.min.css" rel="stylesheet">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/viewerjs/1.11.6/viewer.min.js"></script>

            <style>
                .contrato-container {{
                    text-align: center;
                    margin-bottom: 10px;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 5px;
                    background: white;
                    cursor: zoom-in; /* Manito de lupa */
                }}
                #imagen-contrato {{
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 0 auto;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                /* Ocultar botones feos de la librería si queremos */
                .viewer-title {{ display: none; }}
            </style>

            <div class="contrato-container">
                <img id="imagen-contrato" src="data:image/png;base64,{img_base64}" alt="Contrato Página {st.session_state['pagina_actual'] + 1}">
                <div style="margin-top:5px; color:#555; font-size:12px;">👆 <i>Toque la hoja para ampliar y hacer zoom con los dedos</i> 🔍</div>
            </div>

            <script>
                // ESPERAMOS A QUE CARGUE LA IMAGEN
                var img = document.getElementById('imagen-contrato');
                
                // INICIAMOS EL VISOR POTENTE
                // Esto crea una capa por encima de Streamlit
                var viewer = new Viewer(img, {{
                    toolbar: {{
                        zoomIn: 1,
                        zoomOut: 1,
                        oneToOne: 1,
                        reset: 1,
                        rotateLeft: 0,
                        rotateRight: 0,
                        flipHorizontal: 0,
                        flipVertical: 0,
                    }},
                    navbar: false,
                    title: false,
                    tooltip: false,
                    movable: true,
                    zoomable: true,
                    rotatable: false,
                    scalable: false,
                    inline: false, // ESTO ES CLAVE: MODO MODAL (PANTALLA COMPLETA REAL)
                    transition: false, // Más rápido en celulares lentos
                    backdrop: 'rgba(0,0,0,0.9)' // Fondo negro oscuro
                }});
            </script>
            """
            
            # Renderizamos la bomba HTML
            st.components.v1.html(componente_visualizador, height=500, scrolling=False)

        except Exception as e:
            st.error(f"Error cargando visor: {e}")

        # --- BARRA DE NAVEGACIÓN ESTILO "TOOLBAR" ---
        st.write("") # Un pequeño espacio antes
        
        # Usamos columnas: [Botón Ant] [ Texto Centro ] [Botón Sig]
        # La proporción [1, 3, 1] hace que los botones sean chicos y el texto tenga espacio
        c_nav_ant, c_nav_txt, c_nav_sig = st.columns([1, 3, 1], gap="small")
        
        with c_nav_ant:
            if st.session_state['pagina_actual'] > 0:
                # Usamos solo flecha para ahorrar espacio en móvil
                if st.button("⬅️", use_container_width=True, help="Página Anterior"):
                    st.session_state['pagina_actual'] -= 1
                    st.rerun()
                    
        with c_nav_txt:
            # Texto centrado y bonito
            st.markdown(
                f"""
                <div style="
                    text-align: center;
                    padding-top: 8px; /* Alineación vertical con los botones */
                    font-weight: bold;
                    color: #555;
                    font-size: 14px;
                ">
                    Pág. {st.session_state['pagina_actual'] + 1} de {total_paginas}
                </div>
                """, 
                unsafe_allow_html=True
            )
            
        with c_nav_sig:
            if st.session_state['pagina_actual'] < total_paginas - 1:
                # Usamos solo flecha para ahorrar espacio
                if st.button("➡️", type="primary", use_container_width=True, help="Página Siguiente"):
                    st.session_state['pagina_actual'] += 1
                    st.rerun()
        
            # PASO 2: FOTO HÍBRIDA
            st.markdown("---")
            st.subheader("2. Foto de Identidad")
            
            if st.session_state['foto_bio'] is None:
                usar_webcam = st.checkbox("💻 ¿*ESTÁS USANDO COMPUTADORA/LAPTOPT? USA ESTE BOTÓN PARA TOMARTE LA FOTO", value=False)
                foto_input = None
                if usar_webcam:
                    foto_input = st.camera_input("📸 TOMAR FOTO", label_visibility="visible")
                else:
                    st.warning("📸 *TOQUE EL CUADRO PARA TOMARSE LA FOTO*:")
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

            # PASO 3: FIRMA (WIDTH 400PX)
            st.markdown("---")
            st.subheader("3. Firma y Conformidad")
            
            if st.session_state['foto_bio'] is None:
                st.error("⚠️ PRIMERO DEBE TOMARSE LA FOTO EN EL PASO 2 👆")
            else:
                st.caption("Dibuje su firma. Use la **Papelera 🗑️** para borrar.")
                with st.form(key="formulario_firma", clear_on_submit=False):
                    canvas_result = st_canvas(
                        stroke_width=2, stroke_color="#000000", background_color="#ffffff", 
                        height=200, width=340, drawing_mode="freedraw", # <--- CAMBIAR A 340 AQUÍ
                        display_toolbar=True, key=f"canvas_{st.session_state['canvas_key']}"
                    )
                    st.write("") 
                    enviar_firma = st.form_submit_button("✅ FINALIZAR Y FIRMAR", type="primary", use_container_width=True)

                if enviar_firma:
                    if canvas_result.image_data is not None:
                        img_data = canvas_result.image_data.astype('uint8')
                        if img_data[:, :, 3].sum() == 0:
                            st.warning("⚠️ El recuadro está vacío. Por favor firme.")
                        else:
                            ruta_firma = os.path.join(CARPETA_TEMP, "firma.png")
                            ruta_salida_firmado = os.path.join(CARPETA_TEMP, f"FIRMADO_{nombre_archivo}")
                            
                            with st.spinner("⏳ Guardando contrato..."):
                                try:
                                    img = Image.fromarray(img_data, 'RGBA')
                                    data = img.getdata()
                                    newData = []
                                    es_blanco = True 
                                    for item in data:
                                        if item[0] < 200: es_blanco = False 
                                        if item[0] > 230 and item[1] > 230 and item[2] > 230:
                                            newData.append((255, 255, 255, 0))
                                        else: newData.append(item)
                                    
                                    if es_blanco: st.warning("⚠️ El recuadro parece vacío.")
                                    else:
                                        img.putdata(newData)
                                        img.save(ruta_firma, "PNG")
                                        estampar_firma(ruta_pdf_local, ruta_firma, ruta_salida_firmado)
                                        estampar_firma_y_foto_pagina9(ruta_salida_firmado, ruta_firma, st.session_state['foto_bio'], ruta_salida_firmado)
                                        enviar_a_drive_script(ruta_salida_firmado, nombre_archivo)
                                        if registrar_firma_sheet(st.session_state['dni_validado']):
                                            st.session_state['firmado_ok'] = True
                                            borrar_archivo_drive(st.session_state['archivo_id'])
                                            st.balloons()
                                            st.rerun()
                                        else: st.error("⚠️ Error de conexión con Excel.")
                                except Exception as e: st.error(f"Error técnico: {e}")
                                finally:
                                    if os.path.exists(ruta_firma): os.remove(ruta_firma)
                    else: st.warning("⚠️ Falta su firma.")

            if st.button("⬅️ Cancelar"):
                st.session_state['dni_validado'] = None
                st.rerun()
















