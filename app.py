import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
from datetime import datetime, timedelta
from streamlit_js_eval import get_geolocation
import uuid

# --- 1. CONNESSIONE A GOOGLE SHEETS ---
def connetti_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        secret_raw = st.secrets["service_account"].strip()
        creds_info = json.loads(secret_raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CRM_Dati").sheet1 
        return sheet
    except Exception as e:
        if "Response [200]" not in str(e):
            st.error(f"❌ Errore connessione: {e}")
        return None

# --- 2. FUNZIONI DATI ---
def carica_dati():
    sheet = connetti_google_sheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame(columns=["Data", "Agente", "Cliente", "Tipo", "Località", "Provincia", "Note", "FollowUp", "Latitudine", "Longitudine", "ID"])
        return df
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
            # Reset campi
            s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
            st.toast("✅ Salvato su Drive!")
            st.rerun()
    else:
        st.error("⚠️ Compila almeno Cliente e Note!")

def elimina_riga(id_da_eliminare):
    sheet = connetti_google_sheet()
    if sheet:
        records = sheet.get_all_records()
        for i, r in enumerate(records):
            if str(r.get('ID', '')) == str(id_da_eliminare):
                sheet.delete_rows(i + 2)
                st.rerun()

# --- 3. INTERFACCIA ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="wide")

st.title("💼 CRM Michelone Cloud")

# --- SEZIONE INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nome Cliente", key="cliente_key")
        st.radio("Tipo", ["Cliente", "Potenziale"], key="tipo_key", horizontal=True)
    with col2:
        st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
        st.date_input("Data Visita", datetime.now(), key="data_key")

    st.markdown("---")
    c_loc, c_prov, c_gps = st.columns([3, 1, 2])
    with c_loc: st.text_input("Località", key="localita_key")
    with c_prov: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    # GEOLOCALIZZAZIONE
    with c_gps:
        st.write(" ") # Spaziatore
        loc = get_geolocation()
        if loc and st.button("📍 USA POSIZIONE GPS", use_container_width=True):
            lat = loc['coords']['latitude']
            lon = loc['coords']['longitude']
            st.session_state['lat_val'] = str(lat)
            st.session_state['lon_val'] = str(lon)
            # Reverse Geocoding per trovare città
            try:
                res = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}").json()
                addr = res.get('address', {})
                citta = addr.get('city', addr.get('town', addr.get('village', '')))
                st.session_state.localita_key = citta.upper()
                st.toast("📍 Posizione acquisita!")
            except: pass

    st.text_area("Note del colloquio", key="note_key", height=100)
    
    st.write("📅 **Pianifica Ricontatto (Follow-up):**")
    st.radio("Scadenza", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True)
    
    st.button("💾 SALVA SU GOOGLE DRIVE", on_click=salva_visita_drive, use_container_width=True, type="primary")

st.divider()

# --- RICERCA E ARCHIVIO ---
df = carica_dati()

if not df.empty:
    st.subheader("🔍 Ricerca nell'Archivio")
    
    # Filtri
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        cerca = st.text_input("Cerca per nome o parola chiave...")
    with f_col2:
        agente_scelto = st.selectbox("Filtra per Agente", ["Tutti"] + ["HSE", "BIENNE", "PALAGI", "SARDEGNA"])

    # Applica filtri
    mask = df.astype(str).apply(lambda x: cerca.lower() in x.str.lower().any(), axis=1) if cerca else [True]*len(df)
    df_filt = df[mask]
    if agente_scelto != "Tutti":
        df_filt = df_filt[df_filt['Agente'] == agente_scelto]

    # Alert Scadenze
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scaduti = df[df['FollowUp'] != ""]
    df_scaduti = df_scaduti[df_scaduti['FollowUp'] <= oggi]
    
    if not df_scaduti.empty:
        st.error(f"⚠️ Hai {len(df_scaduti)} ricontatti scaduti o per oggi!")

    # Visualizzazione Schede
    for i, row in df_filt.iloc[::-1].iterrows():
        with st.expander(f"{row['Data']} - {row['Cliente']} ({row['Località']}) - {row['Agente']}"):
            st.write(f"**Tipo:** {row['Tipo']}")
            st.write(f"**Note:** {row['Note']}")
            if row['FollowUp']: st.warning(f"📅 Ricontatto fissato per: {row['FollowUp']}")
            
            if st.button("🗑️ Elimina Visita", key=f"del_{row['ID']}"):
                elimina_riga(row['ID'])
                st.toast("Eliminato...")
else:
    st.info("Nessuna visita registrata nel foglio Google.")