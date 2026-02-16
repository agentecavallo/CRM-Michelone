import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
from datetime import datetime, timedelta
from streamlit_js_eval import get_geolocation
import uuid

# --- 1. CONNESSIONE A GOOGLE SHEETS (PUNTO 5) ---
def connetti_google_sheet():
    # Definiamo i permessi necessari
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        # Recupera la stringa dai Secrets e puliscila da eventuali spazi bianchi
        secret_raw = st.secrets["service_account"].strip()
        creds_info = json.loads(secret_raw)
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # Prova ad aprire il foglio
        sheet = client.open("CRM_Dati").sheet1 
        return sheet
    except Exception as e:
        # Se non c'è un vero errore, non mostrare nulla
        if "Response [200]" not in str(e):
            st.error(f"❌ Errore di connessione: {e}")
        return None

# --- RESTO DEL CODICE PER IL FUNZIONAMENTO ---
def carica_dati():
    sheet = connetti_google_sheet()
    if sheet:
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    return pd.DataFrame()

def salva_visita_drive():
    s = st.session_state
    if s.get('cliente_key', '').strip() != "" and s.get('note_key', '').strip() != "":
        sheet = connetti_google_sheet()
        if sheet:
            data_oggi = s.data_key.strftime("%d/%m/%Y")
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            if scelta == "7 gg": data_fup = (s.data_key + timedelta(days=7)).strftime("%Y-%m-%d")
            elif scelta == "30 gg": data_fup = (s.data_key + timedelta(days=30)).strftime("%Y-%m-%d")

            nuova_riga = [
                data_oggi, s.agente_key, s.cliente_key, s.tipo_key, 
                s.localita_key.upper(), s.prov_key.upper(), s.note_key, 
                data_fup, s.get('lat_val', ''), s.get('lon_val', ''), str(uuid.uuid4())
            ]
            sheet.append_row(nuova_riga)
            st.toast("✅ Salvato su Drive!")
            st.rerun()
    else:
        st.error("⚠️ Compila Cliente e Note!")

# --- INTERFACCIA ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼")
st.title("💼 CRM Michelone Cloud")

# Form di inserimento
with st.expander("➕ REGISTRA NUOVA VISITA"):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale"], key="tipo_key", horizontal=True)
    st.text_input("Località", key="localita_key")
    st.text_input("Prov.", key="prov_key", max_chars=2)
    st.date_input("Data", datetime.now(), key="data_key")
    st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key")
    st.radio("Pianifica Ricontatto", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA SU DRIVE", on_click=salva_visita_drive)

st.divider()

# Visualizzazione dati
df = carica_dati()
if not df.empty:
    st.subheader("🔍 Archivio Visite")
    st.dataframe(df)
else:
    st.info("In attesa di dati dal foglio Google...")

