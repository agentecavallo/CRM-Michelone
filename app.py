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
        # Recupera la stringa dai Secrets e puliscila
        secret_raw = st.secrets["service_account"].strip()
        creds_info = json.loads(secret_raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # Apri il foglio (assicurati che si chiami esattamente così su Drive)
        sheet = client.open("CRM_Dati").sheet1 
        return sheet
    except Exception as e:
        if "Response [200]" not in str(e):
            st.error(f"❌ Errore connessione: {e}")
        return None

# --- 2. FUNZIONI GESTIONE DATI ---
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

            # Prepariamo la riga per Google Sheets
            nuova_riga = [
                data_oggi, 
                s.agente_key, 
                s.cliente_key, 
                s.tipo_key, 
                s.localita_key.upper(), 
                s.prov_key.upper(), 
                s.note_key, 
                data_fup, 
                s.get('lat_val', ''), 
                s.get('lon_val', ''), 
                str(uuid.uuid4()) # ID Univoco per eliminazione sicura
            ]
            sheet.append_row(nuova_riga)
            
            # Reset dei campi dopo il salvataggio
            s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
            s.lat_val = ""; s.lon_val = ""
            st.toast("✅ Salvato correttamente su Google Drive!")
            st.rerun()
    else:
        st.error("⚠️ Errore: Inserisci almeno il nome Cliente e le Note!")

def elimina_riga(id_da_eliminare):
    sheet = connetti_google_sheet()
    if sheet:
        records = sheet.get_all_records()
        for i, r in enumerate(records):
            if str(r.get('ID', '')) == str(id_da_eliminare):
                sheet.delete_rows(i + 2) # +2 perché gspread conta da 1 e c'è l'intestazione
                st.toast("🗑️ Visita eliminata dal database")
                st.rerun()

# --- 3. INTERFACCIA UTENTE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="wide")

# Logo e Titolo
col_logo, col_tit = st.columns([1, 6])
with col_logo:
    st.image("https://cdn-icons-png.flaticon.com/512/2912/2912761.png", width=80)
with col_tit:
    st.title("CRM Michelone Cloud")

# ESPANDER: INSERIMENTO NUOVA VISITA
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Nome Cliente", key="cliente_key")
        st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    with c2:
        st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
        st.date_input("Data Visita", datetime.now(), key="data_key")

    st.markdown("---")
    
    # Riga Località e GPS
    l1, l2, l3 = st.columns([3, 1, 2])
    with l1: st.text_input("Località (Città)", key="localita_key")
    with l2: st.text_input("Prov.", key="prov_key", max_chars=2)
    with l3:
        st.write(" ") # Allineamento
        # Funzione GPS Streamlit
        loc_data = get_geolocation()
        if st.button("📍 USA POSIZIONE GPS", use_container_width=True):
            if loc_data:
                lat = loc_data['coords']['latitude']
                lon = loc_data['coords']['longitude']
                st.session_state['lat_val'] = str(lat)
                st.session_state['lon_val'] = str(lon)
                # Reverse Geocoding per trovare la città
                try:
                    r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", timeout=5).json()
                    citta = r.get('address', {}).get('city', r.get('address', {}).get('town', r.get('address', {}).get('village', '')))
                    st.session_state.localita_key = citta.upper()
                    st.toast(f"📍 Posizione acquisita: {citta}")
                except:
                    st.toast("📍 Coordinate acquisite (Nome città non disponibile)")
            else:
                st.error("⚠️ GPS non autorizzato. Controlla il lucchetto nella barra del browser!")

    st.text_area("Note del colloquio", key="note_key", placeholder="Cosa vi siete detti?", height=120)
    
    st.write("📅 **Pianifica Ricontatto (Follow-up):**")
    st.radio("Fra quanto tempo?", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True)
    
    st.button("💾 SALVA SU GOOGLE DRIVE", on_click=salva_visita_drive, use_container_width=True, type="primary")

st.divider()

# --- 4. SEZIONE RICERCA E ARCHIVIO (SEMPRE VISIBILE) ---
st.subheader("🔍 Ricerca nell'Archivio")
filtro_testo, filtro_agente = st.columns(2)
with filtro_testo:
    cerca = st.text_input("Cerca per nome cliente, città o note...", placeholder="Esempio: Rossi o Roma...")
with filtro_agente:
    ag_scelto = st.selectbox("Filtra per Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

# Caricamento dati
df = carica_dati()

if not df.empty:
    # Applichiamo i filtri
    df_filt = df.copy()
    if cerca:
        # Filtra su tutte le colonne convertendo tutto in stringa
        df_filt = df_filt[df_filt.astype(str).apply(lambda x: cerca.lower() in x.str.lower().any(), axis=1)]
    if ag_scelto != "Tutti":
        df_filt = df_filt[df_filt['Agente'] == ag_scelto]

    # Controllo Scadenze (Alert rosso)
    oggi = datetime.now().strftime("%Y-%m-%d")
    if 'FollowUp' in df_filt.columns:
        scaduti = df_filt[(df_filt['FollowUp'] != "") & (df_filt['FollowUp'] <= oggi)]
        if not scaduti.empty:
            st.error(f"⚠️ Attenzione! Ci sono {len(scaduti)} ricontatti da gestire oggi!")

    # Visualizzazione risultati
    if not df_filt.empty:
        st.write(f"Trovate {len(df_filt)} visite:")
        for i, row in df_filt.iloc[::-1].iterrows(): # Ultime visite per prime
            with st.expander(f"📌 {row['Data']} - {row['Cliente']} ({row['Località']})"):
                st.write(f"**Agente:** {row['Agente']} | **Tipo:** {row['Tipo']}")
                st.info(f"**Note:** {row['Note']}")
                if row['FollowUp']:
                    st.warning(f"📅 Da ricontattare entro il: {row['FollowUp']}")
                
                # Tasto eliminazione
                if st.button("🗑️ Elimina Record", key=f"del_{row['ID']}"):
                    elimina_riga(row['ID'])
    else:
        st.info("Nessun risultato trovato con questi filtri.")
else:
    st.info("L'archivio su Google Drive è vuoto. Registra la tua prima visita qui sopra!")
