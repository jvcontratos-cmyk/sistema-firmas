import streamlit as st
import os
import shutil
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import base64
from PIL import Image
import requests
import fitz  # PyMuPDF
import gspread 
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA (MODO KIOSCO) ---
st.set_page_config(page_title="Portal de Contratos", page_icon="✍️", layout="wide")

# --- CSS NUCLEAR MEJORADO (CON EL PARCHE FINAL) ---
st.markdown("""
    <style>
    /* Ocultar Header superior (Hamburguesa, Deploy, etc.) */
    header {visibility: hidden;}
    [data-testid="stHeader"] {display: none;}
    
    /* Ocultar Footer y marcas de agua */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    
    /* Ocultar la barra inferior donde sale "Manage app" */
    .stAppDeployButton {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    [data-testid="stStatusWidget"] {display: none !important;} /* <--- ESTA LÍNEA BORRA EL MANAGE APP */
    
    /* Ocultar botones internos del canvas */
    div[data-testid="stCanvas"] button {display: none !important;}
    div[data-testid="stElementToolbar"] {display: none !important;}
    
    /* Ajustar espacios */
    .block-container {padding-top: 2rem !important;}
    </style>
    """, unsafe_allow_html=True)

# 1. LEER SECRETOS Y CONFIGURAR GOOGLE SHEETS
if "gcp_service_account" in st.secrets:
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client_sheets = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error conectando con Google: {e}")
        st.stop()
else:
    st.error("⚠️ Falta configuración interna.")
    st.stop()

# URL DEL SCRIPT (PUENTE)
if "drive_script_url" in st.secrets["general"]:
    WEB_APP_URL = st.secrets["general"]["drive_script_url"]
else:
    st.stop()

# CONFIGURACIÓN
SHEET_ID = "1OmzmHkZsKjJlPw2V2prVlv_LbcS8RzmdLPP1eL6EGNE"
DRIVE_FOLDER_ID = "1g-ht7BZCUiyN4um1M9bytrrVAZu7gViN"

CARPETA_PENDIENTES = "PENDIENTES"  
CARPETA_FIRMADOS = "FIRMADOS"
CARPETA_PROCESADOS = "PROCESADOS"

os.makedirs(CARPETA_FIRMADOS, exist_ok=True)
os.makedirs(CARPETA_PENDIENTES, exist_ok=True)
os.makedirs(CARPETA_PROCESADOS, exist_ok=True)

# VARIABLES DE SESIÓN
if 'dni_validado' not in st.session_state: st.session_state['dni_validado'] = None
if 'archivo_actual' not in st.session_state: st.session_state['archivo_actual'] = None
if 'canvas_key' not in st.session_state: st.session_state['canvas_key'] = 0
if 'firmado_ok' not in st.session_state: st.session_state['firmado_ok'] = False

# --- BARRA LATERAL (FAQ) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/471/471662.png", width=50)
    st.subheader("Preguntas Frecuentes")
    
    # PREGUNTA 1: SUELDO
    with st.expander("💰 ¿Por qué mi sueldo figura diferente en el contrato?"):
        st.markdown("""
        En el contrato de trabajo se estipula únicamente la **Remuneración Básica** correspondiente al puesto.
        
        El monto informado durante su reclutamiento es el **Sueldo Bruto**, el cual incluye el básico más otros conceptos (como horas extras, bonificaciones, etc.).
        
        *Podrá ver el detalle completo de sus ingresos reflejado en su **boleta de pago** a fin de mes.*
        """)

    # PREGUNTA 2: HORAS (Corregido icono y texto)
    with st.expander("🕒 ¿Por qué el contrato dice 8hrs si trabajo 12hrs?"):
        st.markdown("""
        La ley peruana establece que la **Jornada Ordinaria** base es de 8 horas diarias.
        
        Si su turno es de 12 horas:
        * Las primeras 8 horas cubren esa jornada legal.
        * Las **4 horas restantes** se consideran y pagan como **HORAS EXTRAS**.
        
        *Este pago adicional se verá reflejado en su **boleta de pago** a fin de mes.*
        """)
    
    st.markdown("---")
    st.info("📞 **¿Dudas adicionales?**\nContacte al área de RRHH.")

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
            # Hora Perú (UTC -5)
            hora_peru = datetime.utcnow() - timedelta(hours=5)
            fecha_fmt = hora_peru.strftime("%Y-%m-%d %H:%M:%S")
            
            sh.update_cell(cell.row, 2, "FIRMADO") # Columna B
            sh.update_cell(cell.row, 3, fecha_fmt) # Columna C (Fecha y Hora)
            return True
    except: return False

def enviar_a_drive_script(ruta_archivo, nombre_archivo):
    try:
        with open(ruta_archivo, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        payload = {"file": pdf_base64, "filename": nombre_archivo, "folderId": DRIVE_FOLDER_ID}
        requests.post(WEB_APP_URL, json=payload)
        return True
    except: return False

def estampar_firma(pdf_path, imagen_firma, output_path):
    pdf_original = PdfReader(pdf_path)
    pdf_writer = PdfWriter()
    total_paginas = len(pdf_original.pages)
    ANCHO, ALTO = 110, 60
    COORDENADAS = {5: [(380, 388), (380, 260)], 6: [(380, 115)], 8: [(380, 175)]}
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

    if submitted and dni_input:
        with st.spinner("Verificando..."):
            estado_sheet = consultar_estado_dni(dni_input)
        
        # MENSAJE DE ALERTA (AZUL/AMABLE)
        if estado_sheet == "FIRMADO":
            st.info(f"ℹ️ El DNI {dni_input} ya registra un contrato firmado.")
            st.markdown("""
            **Si necesita una copia de su contrato** (porque no pudo descargarla anteriormente) o cree que esto es un error, 
            por favor **contacte al área de Recursos Humanos**.
            """)
        
        else:
            archivo_encontrado = None
            if os.path.exists(CARPETA_PENDIENTES):
                for archivo in os.listdir(CARPETA_PENDIENTES):
                    if archivo.startswith(dni_input) and archivo.lower().endswith(".pdf"):
                        archivo_encontrado = archivo
                        break
            
            if not archivo_encontrado and os.path.exists(CARPETA_PROCESADOS):
                for archivo in os.listdir(CARPETA_PROCESADOS):
                    if archivo.startswith(dni_input):
                        st.info("ℹ️ Su contrato ya fue procesado localmente. Contacte a RRHH.")
                        st.stop()

            if archivo_encontrado:
                st.session_state['dni_validado'] = dni_input
                st.session_state['archivo_actual'] = archivo_encontrado
                st.session_state['firmado_ok'] = False
                st.rerun()
            else:
                st.error("❌ Contrato no ubicado (Verifique que su DNI esté correcto).")

else:
    archivo = st.session_state['archivo_actual']
    
    if st.session_state['firmado_ok']:
        st.success("✅ ¡Firma registrada exitosamente!")
        st.markdown(f"**Archivo:** {archivo}")
        # MENSAJE DE ÉXITO CORREGIDO
        st.info("Su contrato ha sido guardado en la base de datos.")
        
        ruta_salida = os.path.join(CARPETA_FIRMADOS, archivo)
        if os.path.exists(ruta_salida):
            with open(ruta_salida, "rb") as f:
                st.download_button("📥 DESCARGAR MI CONTRATO FIRMADO", f, file_name=archivo, mime="application/pdf", type="primary")
        
        st.markdown("---")
        if st.button("🏠 FINALIZAR Y SALIR"):
            st.session_state['dni_validado'] = None
            st.session_state['firmado_ok'] = False
            st.rerun()

    else:
        ruta_pdf = os.path.join(CARPETA_PENDIENTES, archivo)
        st.success(f"✅ Documento listo: **{archivo}**")
        st.info("Lea el contrato y firme al final.")
        
        with st.container(height=500, border=True):
            mostrar_pdf_como_imagenes(ruta_pdf)

        st.markdown("---")
        st.header("👇 Firme aquí")
        
        canvas_result = st_canvas(stroke_width=2, stroke_color="#000000", background_color="#ffffff", height=200, width=600, drawing_mode="freedraw", display_toolbar=False, key=f"canvas_{st.session_state['canvas_key']}")

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
                    
                    with st.spinner("Procesando firma y registrando fecha..."):
                        try:
                            # 1. Imagen
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
                            
                            # 2. Estampar
                            ruta_origen = os.path.join(CARPETA_PENDIENTES, archivo)
                            estampar_firma(ruta_origen, ruta_temp, ruta_salida)
                            
                            # 3. Drive
                            enviar_a_drive_script(ruta_salida, nombre_final)
                            
                            # 4. Mover
                            ruta_destino = os.path.join(CARPETA_PROCESADOS, archivo)
                            if os.path.exists(ruta_destino): os.remove(ruta_destino)
                            shutil.move(ruta_origen, ruta_destino)
                            
                            # 5. Excel (Con Fecha y Hora)
                            registrar_firma_sheet(st.session_state['dni_validado'])
                            
                            st.session_state['firmado_ok'] = True
                            st.balloons()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error técnico: {e}")
                        finally:
                            if os.path.exists(ruta_temp): os.remove(ruta_temp)
                else:
                    st.warning("⚠️ Por favor, dibuje su firma.")

        if st.button("⬅️ Salir"):
            st.session_state['dni_validado'] = None
            st.rerun()
