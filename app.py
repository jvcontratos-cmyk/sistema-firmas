import streamlit as st
import pandas as pd

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Acceso Líderes", page_icon="🔑", layout="centered")

# --- CSS PARA DISEÑO LIMPIO (Estilo imagen 3) ---
st.markdown("""
    <style>
    /* Ocultar elementos de Streamlit */
    #MainMenu, footer, header {visibility: hidden;}
    
    /* Contenedor principal estilo tarjeta */
    .stApp {
        background-color: #f5f5f5;
    }
    .login-box {
        background-color: white;
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05);
        text-align: center;
    }
    /* Estilo del logo */
    .logo-img {
        max-width: 150px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- LÓGICA DE INTERFAZ ---
def main():
    # Logo central (Asegúrate de tener el logo_liderman.png en tu GitHub)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("logo_liderman.png", use_container_width=True)
        
    st.markdown("<br>", unsafe_allow_html=True)

    # Tabs para separar Inicio de Sesión y Registro
    tab_login, tab_registro = st.tabs(["🔒 Iniciar Sesión", "📝 Registrarse"])

    with tab_login:
        with st.container():
            usuario = st.text_input("👤 Usuario (DNI)", key="user_login")
            clave = st.text_input("🔑 Contraseña", type="password", key="pass_login")
            
            if st.button("Iniciar Sesión", use_container_width=True, type="primary"):
                st.info("Aquí conectaremos con tu Excel para validar.")

    with tab_registro:
        st.markdown("##### Activa tu cuenta de Líder Zonal")
        dni_reg = st.text_input("🆔 Ingresa tu DNI", key="dni_reg")
        nueva_clave = st.text_input("🆕 Crea tu contraseña", type="password", key="pass_reg")
        confirmar_clave = st.text_input("✅ Confirma tu contraseña", type="password")
        
        if st.button("Completar Registro", use_container_width=True):
            # Aquí irá la lógica:
            # 1. ¿DNI está en la lista de zonales?
            # 2. ¿Ya tenía clave?
            # 3. ¿Las claves coinciden?
            st.warning("Validando DNI en la base de datos de Zonales...")

if __name__ == "__main__":
    main()
