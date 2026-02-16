import streamlit as st
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation

# --- 1. CONFIGURAZIONE E STILE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

# CSS per il logo fisso in basso a destra
# SOSTITUISCI 'URL_DEL_TUO_LOGO' con il link reale della tua immagine
URL_LOGO = "https://tuosito.it/logo_michelone.png" 

st.markdown(
    f"""
    <style>
    .footer-logo {{
        position: fixed;
        bottom: 10px;
        right: 10px;
        width: 100px;
        z-index: 100;
        filter: drop-shadow(2px 2px 4px rgba(0,0,0,0.3));
    }}
    </style>
    <img src="{URL_LOGO}" class="footer-logo">
    """,
    unsafe_allow_html=True
)

# --- 2. FUNZIONI DI SUPPORTO ---
def inizializza_db():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    # Aggiunta colonna 'foto' di tipo BLOB
    c.execute('''CREATE TABLE IF NOT EXISTS visite 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cliente TEXT, localita TEXT, provincia TEXT,
                  tipo_cliente TEXT, data TEXT, note TEXT,
                  data_followup TEXT, data_ordine TEXT, agente TEXT,
                  latitudine TEXT, longitudine TEXT, foto BLOB)''')
    conn.commit()
    conn.close()

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
        
        # Follow up
        scelta = s.get('fup_opt', "No")
        data_fup = ""
        if scelta == "7 gg":
            data_fup = (s.data_key + timedelta(days=7)).strftime("%Y-%m-%d")
        elif scelta == "30 gg":
            data_fup = (s.data_key + timedelta(days=30)).strftime("%Y-%m-%d")

        # Gestione Foto
        foto_bytes = None
        if s.get('foto_caricata'):
            foto_bytes = s.foto_caricata.getvalue()

        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine, foto) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                   data_visita_fmt, note, data_fup, data_ord, s.agente_key, 
                   s.get('lat_val', ""), s.get('lon_val', ""), foto_bytes))
        conn.commit()
        conn.close()
        
        # Reset
        for k in ['cliente_key', 'localita_key', 'prov_key', 'note_key', 'lat_val', 'lon_val']:
            st.session_state[k] = ""
        st.session_state.fup_opt = "No"
        
        st.toast("✅ Visita salvata!")
        st.rerun() 
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA ---
inizializza_db()
st.title("💼 CRM Michelone")

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
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'CRM_Michelone'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', a.get('state', ''))
                prov_sigla = "RM" if "Roma" in prov_full or "Rome" in prov_full else prov_full[:2].upper()
                
                st.session_state['gps_temp'] = {'citta': citta.upper(), 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Indirizzo non trovato.")

    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: **{d['citta']} ({d['prov']})**")
        c1, c2 = st.columns(2)
        with c1: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
        with c2: 
            if st.button("❌ ANNULLA", use_container_width=True): 
                del st.session_state['gps_temp']; st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=100)
    
    # AGGIUNTA FOTO: Camera o File
    st.file_uploader("📸 Allega o Scatta Foto", type=['jpg', 'jpeg', 'png'], key="foto_caricata")
    
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- 4. ALERT SCADENZE ---
conn = sqlite3.connect('crm_mobile.db')
oggi = datetime.now().strftime("%Y-%m-%d")
df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}'", conn)
conn.close()

if not df_scadenze.empty:
    st.error(f"⚠️ **DA RICONTATTARE ({len(df_scadenze)})**")
    for _, row in df_scadenze.iterrows():
        with st.container():
            c_txt, c_btn = st.columns([4, 1])
            c_txt.markdown(f"**{row['cliente']}** ({row['localita']})")
            if c_btn.button("✅", key=f"fup_{row['id']}"):
                conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                c.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                conn.commit(); conn.close(); st.rerun()

# --- 5. ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if t_ricerca or f_agente != "Tutti":
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    conn.close()

    if t_ricerca: df = df[df.apply(lambda r: t_ricerca.lower() in str(r).lower(), axis=1)]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]

    for _, row in df.iterrows():
        with st.expander(f"📅 {row['data']} - {row['cliente']}"):
            st.write(f"**📍 Posizione:** {row['localita']} ({row['provincia']})")
            st.write(f"**📝 Note:** {row['note']}")
            
            # MOSTRA FOTO SE PRESENTE
            if row['foto']:
                st.image(row['foto'], caption=f"Foto di {row['cliente']}", use_container_width=True)
            
            if row['latitudine']:
                st.markdown(f"[📍 Apri in Google Maps](https://www.google.com/maps?q={row['latitudine']},{row['longitudine']})")
            
            if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                c.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                conn.commit(); conn.close(); st.rerun()
