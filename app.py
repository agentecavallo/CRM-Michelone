import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation
import uuid

# --- 1. CONNESSIONE A GOOGLE SHEETS ---
def connetti_google_sheet():
    # Definisci i permessi
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Carica le credenziali dai Secrets di Streamlit
    try:
        creds_dict = json.loads(st.secrets["service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CRM_Dati").sheet1  # Apre il primo foglio
        return sheet
    except Exception as e:
        st.error(f"❌ Errore connessione: Non trovo il foglio 'CRM_Dati'. Controlla di averlo condiviso con l'email del bot! ({e})")
        return None

# --- 2. FUNZIONI DI GESTIONE DATI ---
def carica_dati():
    sheet = connetti_google_sheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    return pd.DataFrame()

def salva_visita_drive():
    s = st.session_state
    cliente = s.get('cliente_key', '')
    note = s.get('note_key', '')
    
    if cliente.strip() != "" and note.strip() != "":
        sheet = connetti_google_sheet()
        if sheet:
            # Preparazione dati
            data_oggi = s.data_key.strftime("%d/%m/%Y")
            
            # Follow Up
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            if scelta == "7 gg":
                data_fup = (s.data_key + timedelta(days=7)).strftime("%Y-%m-%d")
            elif scelta == "30 gg":
                data_fup = (s.data_key + timedelta(days=30)).strftime("%Y-%m-%d")

            # ID Univoco per gestire cancellazioni future
            id_univoco = str(uuid.uuid4())

            # Riga da inserire (stesso ordine delle colonne nel foglio Drive)
            # Data, Agente, Cliente, Tipo, Località, Provincia, Note, FollowUp, Lat, Lon, ID
            nuova_riga = [
                data_oggi,
                s.agente_key,
                cliente,
                s.tipo_key,
                s.localita_key.upper(),
                s.prov_key.upper(),
                note,
                data_fup,
                s.get('lat_val', ''),
                s.get('lon_val', ''),
                id_univoco
            ]
            
            sheet.append_row(nuova_riga)
            
            # Reset campi
            s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
            s.lat_val = ""; s.lon_val = ""; s.fup_opt = "No" 
            if 'gps_temp' in s: del s['gps_temp']
            
            st.toast("✅ Salvato su Drive!")
            st.rerun()
    else:
        st.error("⚠️ Compila Cliente e Note!")

def elimina_riga_drive(id_da_eliminare):
    sheet = connetti_google_sheet()
    if sheet:
        records = sheet.get_all_records()
        for i, r in enumerate(records):
            # Nota: +2 perché i dati partono dalla riga 2 (1 è intestazione)
            if str(r.get('ID', '')) == str(id_da_eliminare):
                sheet.delete_rows(i + 2) 
                st.toast("🗑️ Cancellato da Drive")
                return

def aggiorna_followup_drive(id_da_aggiornare):
    sheet = connetti_google_sheet()
    if sheet:
        records = sheet.get_all_records()
        for i, r in enumerate(records):
            if str(r.get('ID', '')) == str(id_da_aggiornare):
                # Aggiorna colonna FollowUp (H è la colonna 8)
                sheet.update_cell(i + 2, 8, "") 
                st.toast("✅ Completato!")
                return

# --- 3. CALLBACK GPS ---
def applica_dati_gps():
    if 'gps_temp' in st.session_state:
        dati = st.session_state['gps_temp']
        st.session_state.localita_key = dati['citta']
        st.session_state.prov_key = dati['prov']
        st.session_state.lat_val = dati['lat']
        st.session_state.lon_val = dati['lon']
        del st.session_state['gps_temp']

# --- 4. INTERFACCIA ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

st.title("💼 CRM Michelone (Cloud)")

# --- MODULO INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    st.markdown("---")
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    # GPS
    loc_data = get_geolocation()
    if loc_data:
        if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
            try:
                lat = loc_data['coords']['latitude']
                lon = loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'CRM_Michelone'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', a.get('state', ''))
                prov_sigla = "RM" if ("Roma" in prov_full or "Rome" in prov_full) else prov_full[:2].upper()
                
                st.session_state['gps_temp'] = {'citta': citta.upper(), 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Indirizzo non trovato.")

        if 'gps_temp' in st.session_state:
            dati = st.session_state['gps_temp']
            st.info(f"🛰️ Trovato: **{dati['citta']} ({dati['prov']})**")
            c_yes, c_no = st.columns(2)
            with c_yes: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
            with c_no: 
                if st.button("❌ ANNULLA", use_container_width=True): del st.session_state['gps_temp']; st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    
    st.button("💾 SALVA SU DRIVE", on_click=salva_visita_drive, use_container_width=True)

st.divider()

# --- CARICAMENTO DATI DA DRIVE ---
df = carica_dati()

# --- ALERT SCADENZE ---
if not df.empty:
    oggi = datetime.now().strftime("%Y-%m-%d")
    # Filtra righe con FollowUp pieno e data passata o oggi
    if 'FollowUp' in df.columns:
        df_scadenze = df[df['FollowUp'] != ""].copy()
        if not df_scadenze.empty:
            # Assicuriamoci che siano stringhe per il confronto
            df_scadenze = df_scadenze[df_scadenze['FollowUp'].astype(str) <= oggi]
            
            if not df_scadenze.empty:
                st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
                for index, row in df_scadenze.iterrows():
                    icon = "🤝" if row['Tipo'] == "Cliente" else "🚀"
                    try:
                        d_scad = datetime.strptime(str(row['FollowUp']), "%Y-%m-%d")
                        d_oggi = datetime.strptime(oggi, "%Y-%m-%d")
                        ritardo = (d_oggi - d_scad).days
                        msg = "OGGI" if ritardo == 0 else f"Scaduto da {ritardo} gg"
                    except: msg = "Scaduto"
                    
                    with st.container():
                        c_txt, c_btn = st.columns([4, 1])
                        with c_txt:
                            st.markdown(f"**{icon} {row['Cliente']}** ({row['Località']})")
                            st.caption(f"📅 {msg} | Note: {row['Note']}")
                        with c_btn:
                            if st.button("✅", key=f"ok_{row['ID']}"):
                                aggiorna_followup_drive(row['ID'])
                                st.rerun()
                st.divider()

# --- RICERCA ---
st.subheader("🔍 Archivio Drive")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if not df.empty:
    # Filtro dataframe locale
    df_filt = df.copy()
    
    if t_ricerca:
        # Filtra convertendo tutto in stringa per sicurezza
        df_filt = df_filt[df_filt.astype(str).apply(lambda row: t_ricerca.lower() in row.to_string().lower(), axis=1)]
    
    if f_agente not in ["Tutti", "Seleziona..."]:
        df_filt = df_filt[df_filt['Agente'] == f_agente]

    # Mostra risultati
    st.caption(f"Visualizzo {len(df_filt)} visite.")
    
    # Ordiniamo per inserimento inverso (ultimi in alto)
    for index, row in df_filt.iloc[::-1].iterrows():
        icon = "🤝" if row['Tipo'] == "Cliente" else "🚀"
        with st.expander(f"{icon} {row['Agente']} | {row['Data']} - {row['Cliente']}"):
            st.write(f"**📍 Città:** {row['Località']} ({row['Provincia']})")
            st.write(f"**📝 Note:** {row['Note']}")
            
            c_del, c_conf = st.columns([1, 4])
            if st.button("🗑️ Elimina", key=f"pre_del_{row['ID']}"):
                st.session_state[f"conf_{row['ID']}"] = True
            
            if st.session_state.get(f"conf_{row['ID']}", False):
                st.error("Eliminare definitivamente da Drive?")
                c_y, c_n = st.columns(2)
                with c_y:
                    if st.button("SÌ", key=f"yes_{row['ID']}"):
                        elimina_riga_drive(row['ID'])
                        st.session_state[f"conf_{row['ID']}"] = False
                        st.rerun()
                with c_n:
                    if st.button("NO", key=f"no_{row['ID']}"):
                        st.session_state[f"conf_{row['ID']}"] = False
                        st.rerun()

else:
    st.info("Il foglio Drive è vuoto o non accessibile.")
