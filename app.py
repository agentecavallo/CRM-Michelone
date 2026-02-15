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
    
    colonne = ["localita", "provincia", "tipo_cliente", "data_followup", "data_ordine", "agente", "latitudine", "longitudine"]
    for col in colonne:
        try: c.execute(f"ALTER TABLE visite ADD COLUMN {col} TEXT")
        except: pass
    conn.commit()
    conn.close()

def salva_visita():
    s = st.session_state
    if s.cliente_key.strip() != "" and s.note_key.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        data_ordine = s.data_key.strftime("%Y-%m-%d")
        data_fup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if s.reminder_key else ""
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (s.cliente_key, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                   s.data_key.strftime("%d/%m/%Y"), s.note_key, data_fup, data_ordine, 
                   s.agente_key, s.get('lat_val', ""), s.get('lon_val', "")))
        conn.commit()
        conn.close()
        # Reset manuale per sicurezza
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.session_state.lat_val = ""
        st.session_state.lon_val = ""
        st.toast("✅ Salvato con successo!")
    else: st.error("⚠️ Inserisci Cliente e Note!")

def carica_visite(filtro_testo="", data_inizio=None, data_fine=None, filtro_agente="Seleziona...", solo_followup=False):
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite", conn)
    conn.close()
    df[['localita', 'provincia', 'latitudine', 'longitudine']] = df[['localita', 'provincia', 'latitudine', 'longitudine']].fillna("")
    if solo_followup:
        oggi = datetime.now().strftime("%Y-%m-%d")
        return df[(df['data_followup'] != "") & (df['data_followup'] <= oggi)]
    if filtro_testo.strip():
        df = df[df.apply(lambda row: filtro_testo.lower() in str(row).lower(), axis=1)]
    if data_inizio and data_fine:
        df = df[(df['data_ordine'] >= data_inizio.strftime("%Y-%m-%d")) & (df['data_ordine'] <= data_fine.strftime("%Y-%m-%d"))]
    if filtro_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['agente'] == filtro_agente]
    return df.sort_values(by='data_ordine', ascending=False)

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

# Inizializzazione chiavi nello state se non esistono
if 'localita_key' not in st.session_state: st.session_state.localita_key = ""
if 'prov_key' not in st.session_state: st.session_state.prov_key = ""

st.title("💼 CRM Visite Agenti")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    # TASTO GPS MIGLIORATO
    if st.button("📍 RILEVA POSIZIONE E GPS", use_container_width=True):
        loc = get_geolocation()
        if loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            st.session_state.lat_val = str(lat)
            st.session_state.lon_val = str(lon)
            try:
                # Servizio di geocodifica
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'CRM_App_Michelone'}).json()
                addr = r.get('address', {})
                
                # Cerchiamo la città tra varie etichette possibili
                citta = addr.get('city', addr.get('town', addr.get('village', addr.get('suburb', ''))))
                prov = addr.get('county', addr.get('state', ''))
                
                if citta: st.session_state.localita_key = citta.upper()
                if prov: st.session_state.prov_key = prov[:2].upper()
                st.success(f"📍 Posizione rilevata: {citta}")
            except:
                st.warning("Coordinate catturate, ma non riesco a trovare il nome della città. Inseriscila a mano.")

    # DISPOSIZIONE OTTIMIZZATA
    col_loc, col_prov = st.columns([4, 1])
    with col_loc:
        st.text_input("Località", key="localita_key")
    with col_prov:
        st.text_input("Prov.", key="prov_key", max_chars=2)
    
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Ricerca")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    d_i, d_f = (periodo[0], periodo[1]) if isinstance(periodo, list) and len(periodo) == 2 else (None, None)
    df = carica_visite(t_ricerca, d_i, d_f, f_agente)
    
    if not df.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        st.download_button("📊 SCARICA EXCEL", output.getvalue(), "report_crm.xlsx", use_container_width=True)

        for _, row in df.iterrows():
            icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            with st.expander(f"{icon} {row['agente']} | {row['data']} - {row['cliente']}"):
                st.write(f"**📍 Località:** {row['localita']} ({row['provincia']})")
                st.write(f"**📝 Note:** {row['note']}")
                if row['latitudine']:
                    map_url = f"https://www.google.com/maps?q={row['latitudine']},{row['longitudine']}"
                    st.markdown(f"[📍 Apri su Google Maps]({map_url})")
                if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                    c.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                    conn.commit(); conn.close(); st.rerun()