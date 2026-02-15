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
    # Recupero sicuro dei dati dalla sessione
    s = st.session_state
    cliente = s.get('cliente_key', '')
    note = s.get('note_key', '')
    
    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        
        data_visita = s.data_key.strftime("%d/%m/%Y")
        data_ord = s.data_key.strftime("%Y-%m-%d")
        data_fup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if s.reminder_key else ""
        lat = s.get('lat_val', "")
        lon = s.get('lon_val', "")
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, data_visita, note, data_fup, data_ord, s.agente_key, lat, lon))
        conn.commit()
        conn.close()
        
        # Reset totale dei campi
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        s.lat_val = ""; s.lon_val = ""; s.reminder_key = False
        if 'gps_temp' in s: del s['gps_temp'] # Pulisce dati temporanei GPS
        
        st.toast("✅ Visita salvata!")
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

st.title("💼 CRM Visite Agenti")

# --- SEZIONE INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.markdown("---")

    # 1. CAMPI MANUALI (CORRETTO ERRORE VARIABILI)
    # Impostiamo le colonne. Su PC sarà 75% e 25%. Su Mobile si impilano per leggibilità.
    col_l, col_p = st.columns([3, 1]) 
    
    with col_l:
        st.text_input("Località", key="localita_key")
    # Qui c'era l'errore: ora uso "col_p" che è definito sopra
    with col_p:
        st.text_input("Prov.", key="prov_key", max_chars=2)

    # 2. LOGICA GPS (Sotto i campi, con conferma)
    loc_data = get_geolocation()
    
    # Se il GPS rileva qualcosa, mostriamo il tasto
    if loc_data:
        lat = loc_data['coords']['latitude']
        lon = loc_data['coords']['longitude']
        
        if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
            try:
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'CRM_Michelone'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                
                # Gestione Provincia e Roma
                prov_full = a.get('county', a.get('state', ''))
                if "Roma" in prov_full or "Rome" in prov_full: prov_sigla = "RM"
                else: prov_sigla = prov_full[:2].upper()
                
                # Salviamo in memoria temporanea per chiedere conferma
                st.session_state['gps_temp'] = {
                    'citta': citta.upper() if citta else "",
                    'prov': prov_sigla,
                    'lat': str(lat),
                    'lon': str(lon)
                }
            except:
                st.warning("GPS attivo, ma indirizzo non trovato.")

        # Box di conferma (appare solo dopo aver cliccato il tasto sopra)
        if 'gps_temp' in st.session_state:
            dati = st.session_state['gps_temp']
            st.info(f"🛰️ Trovato: **{dati['citta']} ({dati['prov']})**")
            
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("✅ INSERISCI", use_container_width=True):
                    st.session_state.localita_key = dati['citta']
                    st.session_state.prov_key = dati['prov']
                    st.session_state.lat_val = dati['lat']
                    st.session_state.lon_val = dati['lon']
                    del st.session_state['gps_temp']
                    st.rerun()
            with c_no:
                if st.button("❌ ANNULLA", use_container_width=True):
                    del st.session_state['gps_temp']
                    st.rerun()
    else:
        st.caption("📡 Attendi segnale GPS...")
    
    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- RICERCA ---
st.subheader("🔍 Ricerca nell'Archivio")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca nome, città o nota...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Filtra Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    conn.close()

    if t_ricerca:
        df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    if isinstance(periodo, list) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]
    if f_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['agente'] == f_agente]

    if not df.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        st.download_button("📊 SCARICA EXCEL", output.getvalue(), "report.xlsx", use_container_width=True)

        st.caption(f"Trovate {len(df)} visite.")
        for _, row in df.iterrows():
            icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            with st.expander(f"{icon} {row['agente']} | {row['data']} - {row['cliente']}"):
                st.write(f"**📍 Città:** {row['localita']} ({row['provincia']})")
                st.write(f"**📝 Note:** {row['note']}")
                if row['latitudine']:
                    link = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.markdown(f"[📍 Vedi posizione su Mappa]({link})")
                if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                    c.execute("DELETE FROM visite WHERE id = ?", (row['id'],)); conn.commit(); conn.close()
                    st.rerun()
    else:
        st.info("Nessuna visita trovata.")
else:
    st.info("👆 Usa i filtri sopra per cercare.")