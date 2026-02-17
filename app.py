import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

def inizializza_db():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS visite 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cliente TEXT, localita TEXT, provincia TEXT,
                  tipo_cliente TEXT, data TEXT, note TEXT,
                  data_followup TEXT, data_ordine TEXT, agente TEXT,
                  latitudine TEXT, longitudine TEXT)''')
    conn.commit()
    conn.close()

inizializza_db()

# --- 2. FUNZIONI DI SUPPORTO ---

def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup):
        os.makedirs(cartella_backup)
    
    files = [f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')]
    fare_backup = False
    
    if not files:
        fare_backup = True
    else:
        percorsi_completi = [os.path.join(cartella_backup, f) for f in files]
        file_piu_recente = max(percorsi_completi, key=os.path.getctime)
        if datetime.now() - datetime.fromtimestamp(os.path.getctime(file_piu_recente)) > timedelta(days=7):
            fare_backup = True
            
    if fare_backup:
        conn = sqlite3.connect('crm_mobile.db')
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
        conn.close()
        if not df.empty:
            nome_file = f"Backup_Auto_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            df.to_excel(os.path.join(cartella_backup, nome_file), index=False)
            st.toast("🛡️ Backup Settimanale Eseguito!", icon="✅")

controllo_backup_automatico()

def applica_dati_gps():
    if 'gps_temp' in st.session_state:
        dati = st.session_state['gps_temp']
        st.session_state.localita_key = dati['citta']
        st.session_state.prov_key = dati['prov']
        st.session_state.lat_val = dati['lat']
        st.session_state.lon_val = dati['lon']
        del st.session_state['gps_temp']

def salva_visita():
    s = st.session_state
    cliente = s.get('cliente_key', '')
    note = s.get('note_key', '')
    
    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        
        data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
        data_ord = s.data_key.strftime("%Y-%m-%d")
        
        scelta = s.get('fup_opt', 'No')
        data_fup = ""
        mappa_giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
        
        if scelta in mappa_giorni:
            data_fup = (s.data_key + timedelta(days=mappa_giorni[scelta])).strftime("%Y-%m-%d")
        
        lat = s.get('lat_val', "")
        lon = s.get('lon_val', "")
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, data_visita_fmt, 
                   note, data_fup, data_ord, s.agente_key, lat, lon))
        conn.commit()
        conn.close()
        
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        s.lat_val = ""; s.lon_val = ""; s.fup_opt = "No" 
        if 'gps_temp' in s: del s['gps_temp']
        
        st.toast("✅ Visita salvata!", icon="💾")
        st.rerun() 
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

def genera_excel_backup():
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Database_Completo')
    return output.getvalue()

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    st.markdown("---")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_Michelone_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', a.get('state', ''))
                prov_sigla = "RM" if prov_full and "Roma" in prov_full else (prov_full[:2].upper() if prov_full else "??")
                st.session_state['gps_temp'] = {'citta': citta.upper() if citta else "", 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except Exception as e: st.warning(f"Errore GPS: {e}")
        else: st.warning("⚠️ Consenti la geolocalizzazione.")

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
    st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- 4. ALERT SCADENZE ---
conn = sqlite3.connect('crm_mobile.db')
oggi = datetime.now().strftime("%Y-%m-%d")
df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)
conn.close()

if not df_scadenze.empty:
    st.error(f"⚠️ **DA RICONTATTARE: {len(df_scadenze)}**")
    for _, row in df_scadenze.iterrows():
        with st.container():
            col_txt, col_btn = st.columns([4, 1])
            with col_txt:
                st.markdown(f"**{row['cliente']}** ({row['localita']})")
                st.caption(f"Scadenza: {row['data_followup']} | Note: {row['note']}")
            with col_btn:
                if st.button("✅", key=f"fatto_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                    c.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    conn.commit(); conn.close(); st.rerun()
    st.divider()

# --- 5. ARCHIVIO E RICERCA ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca Cliente o Città...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Filtra Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 CERCA", use_container_width=True):
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    conn.close()
    
    if t_ricerca: df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]

    if not df.empty:
        for _, row in df.iterrows():
            with st.expander(f"{row['data']} - {row['cliente']} ({row['agente']})"):
                st.write(f"**Località:** {row['localita']} ({row['provincia']})")
                st.write(f"**Note:** {row['note']}")
                if row['latitudine']:
                    st.markdown(f"[📍 Vai su Mappa](http://maps.google.com/?q={row['latitudine']},{row['longitudine']})")
    else:
        st.warning("Nessun risultato.")

# --- 6. GESTIONE DATI ---
st.subheader("🛠️ Gestione Dati")
with st.expander("💾 BACKUP"):
    st.download_button("📦 SCARICA BACKUP EXCEL", genera_excel_backup(), f"Backup_CRM_{oggi}.xlsx", use_container_width=True)

if os.path.exists("logo.jpg"):
    st.image("logo.jpg", width=100)
