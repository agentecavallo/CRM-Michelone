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
    s = st.session_state
    if s.cliente_key.strip() != "" and s.note_key.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        data_fup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if s.reminder_key else ""
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (s.cliente_key, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                   s.data_key.strftime("%d/%m/%Y"), s.note_key, data_fup, s.data_key.strftime("%Y-%m-%d"), 
                   s.agente_key, s.get('lat_val', ""), s.get('lon_val', "")))
        conn.commit()
        conn.close()
        # Reset
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        s.lat_val = ""; s.lon_val = ""; s.reminder_key = False
        st.toast("✅ Salvato!")
    else: st.error("⚠️ Compila i campi obbligatori!")

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼")
inizializza_db()

st.title("💼 CRM Visite Agenti")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.markdown("---")
    st.write("📍 **Posizione GPS**")
    
    # Questo comando deve stare da solo per funzionare bene
    loc_data = get_geolocation()
    
    if loc_data:
        lat = loc_data['coords']['latitude']
        lon = loc_data['coords']['longitude']
        st.session_state.lat_val = str(lat)
        st.session_state.lon_val = str(lon)
        
        if st.button("🔄 Recupera Indirizzo da GPS"):
            try:
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'Mozilla/5.0'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov = a.get('county', a.get('state', ''))[:2].upper()
                if citta: st.session_state.localita_key = citta.upper()
                if prov: st.session_state.prov_key = prov
                st.success(f"Trovato: {citta}")
            except:
                st.error("GPS attivo, ma non trovo l'indirizzo. Scrivilo a mano.")
    else:
        st.info("Attendi il rilevamento GPS o scrivi l'indirizzo sotto.")

    c_loc, c_prov = st.columns([4, 1])
    with c_loc: st.text_input("Località", key="localita_key")
    with c_prov: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- RICERCA ---
st.subheader("🔍 Archivio")
# Caricamento dati semplificato per ricerca
conn = sqlite3.connect('crm_mobile.db')
df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
conn.close()

t_ricerca = st.text_input("Filtra per nome o città...")
if t_ricerca:
    df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]

if not df.empty:
    for _, row in df.iterrows():
        with st.expander(f"{row['agente']} | {row['data']} - {row['cliente']}"):
            st.write(f"Città: {row['localita']} ({row['provincia']})")
            st.write(f"Note: {row['note']}")
            if row['latitudine'] and row['longitudine']:
                map_url = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                st.markdown(f"[📍 Vai su Mappe]({map_url})")
            if st.button("Elimina", key=f"del_{row['id']}"):
                conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                c.execute("DELETE FROM visite WHERE id = ?", (row['id'],)); conn.commit(); conn.close()
                st.rerun()