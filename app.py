import streamlit as st
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation

# --- 1. FUNZIONI DEL DATABASE ---
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

def salva_visita():
    # Recupero dati in modo sicuro prima di pulire
    cliente = st.session_state.get('cliente_key', '')
    localita = st.session_state.get('localita_key', '').upper()
    provincia = st.session_state.get('prov_key', '').upper()
    tipo = st.session_state.get('tipo_key', 'Cliente')
    note = st.session_state.get('note_key', '')
    agente = st.session_state.get('agente_key', 'HSE')
    data_sel = st.session_state.get('data_key', datetime.now())
    # Per ora lasciamo il followup fisso a 7gg se implementato, o vuoto
    data_fup_db = "" 

    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        data_f = data_sel.strftime("%d/%m/%Y")
        data_ordine = data_sel.strftime("%Y-%m-%d")
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, localita, provincia, tipo, data_f, note, data_fup_db, data_ordine, agente, 
                   st.session_state.get('lat_val', ''), st.session_state.get('lon_val', '')))
        conn.commit()
        conn.close()
        
        # Pulizia campi corretta per evitare StreamlitAPIException
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        if 'gps_temp' in st.session_state:
            del st.session_state['gps_temp']
        st.toast("✅ Visita salvata!")
    else:
        st.error("⚠️ Compila i campi obbligatori!")

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

st.title("💼 CRM Visite Agenti")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.markdown("---")

    # Correzione layout e NameError
    col_l, col_p = st.columns([3, 1]) 
    with col_l:
        st.text_input("Località", key="localita_key")
    with col_p:
        st.text_input("Prov.", key="prov_key", max_chars=2)

    # Logica GPS corretta per evitare crash
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
                
                st.session_state['gps_temp'] = {
                    'citta': citta.upper() if citta else "",
                    'prov': prov_sigla,
                    'lat': str(lat),
                    'lon': str(lon)
                }
            except:
                st.warning("GPS attivo, ma indirizzo non trovato.")

        if 'gps_temp' in st.session_state:
            dati = st.session_state['gps_temp']
            st.info(f"🛰️ Trovato: **{dati['citta']} ({dati['prov']})**")
            
            # Funzione interna per gestire l'inserimento senza errori
            if st.button("✅ INSERISCI DATI", use_container_width=True):
                st.session_state.localita_key = dati['citta']
                st.session_state.prov_key = dati['prov']
                st.session_state.lat_val = dati['lat']
                st.session_state.lon_val = dati['lon']
                del st.session_state['gps_temp']
                st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- RICERCA ---
st.subheader("🔍 Archivio")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca nome o città...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    conn.close()
    if t_ricerca:
        df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    if f_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['agente'] == f_agente]

    for _, row in df.iterrows():
        with st.expander(f"{row['agente']} | {row['data']} - {row['cliente']}"):
            st.write(f"**📍 Città:** {row['localita']} ({row['provincia']})")
            st.write(f"**📝 Note:** {row['note']}")
            if row['latitudine']:
                link = f"https://www.google.com/maps?q={row['latitudine']},{row['longitudine']}"
                st.markdown(f"[📍 Vedi su Mappa]({link})")
            if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                c.execute("DELETE FROM visite WHERE id = ?", (row['id'],)); conn.commit(); conn.close()
                st.rerun()