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
    # Recuperiamo i dati in modo sicuro
    s = st.session_state
    cliente = s.get('cliente_key', '')
    note = s.get('note_key', '')
    
    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        
        # Gestione date e dati
        data_visita = s.data_key.strftime("%d/%m/%Y")
        data_ord = s.data_key.strftime("%Y-%m-%d")
        data_fup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if s.reminder_key else ""
        lat = s.get('lat_val', "")
        lon = s.get('lon_val', "")
        loc = s.localita_key.upper()
        prov = s.prov_key.upper()
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, loc, prov, s.tipo_key, data_visita, note, data_fup, data_ord, s.agente_key, lat, lon))
        conn.commit()
        conn.close()
        
        # Reset dei campi
        s.cliente_key = ""
        s.localita_key = ""
        s.prov_key = ""
        s.note_key = ""
        s.lat_val = ""
        s.lon_val = ""
        s.reminder_key = False
        st.toast("✅ Visita salvata correttameente!")
    else:
        st.error("⚠️ Errore: Inserisci almeno Cliente e Note.")

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

st.title("💼 CRM Visite Agenti")

# --- SEZIONE INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.markdown("---")
    
    # --- LOGICA GPS ---
    loc_data = get_geolocation()
    if loc_data:
        lat = loc_data['coords']['latitude']
        lon = loc_data['coords']['longitude']
        st.session_state.lat_val = str(lat)
        st.session_state.lon_val = str(lon)
        
        if st.button("📍 RECUPERA INDIRIZZO", use_container_width=True):
            try:
                # Chiediamo i dati a OpenStreetMap
                url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
                r = requests.get(url, headers={'User-Agent': 'CRM_Agenti_App'}).json()
                addr = r.get('address', {})
                
                # 1. Trova la Città (prova vari campi perché ogni comune è diverso)
                citta = addr.get('city', addr.get('town', addr.get('village', addr.get('municipality', ''))))
                
                # 2. Trova la Provincia (e fissa il problema ROMA)
                provincia_full = addr.get('county', addr.get('state', ''))
                
                if "Roma" in provincia_full or "Rome" in provincia_full:
                    sigla_prov = "RM"
                else:
                    # Prende le prime 2 lettere se non è Roma
                    sigla_prov = provincia_full[:2].upper()

                # Riempie i campi
                if citta: st.session_state.localita_key = citta.upper()
                st.session_state.prov_key = sigla_prov
                
                st.success(f"Trovato: {citta} ({sigla_prov})")
            except Exception as e:
                st.warning("Coordinate OK, ma indirizzo non trovato. Inseriscilo a mano.")

    # --- CAMPI LOCALITA E PROVINCIA (Corretto NameError) ---
    col_l, col_p = st.columns([4, 1])
    with col_l:
        st.text_input("Località", key="localita_key")
    with col_p:
        st.text_input("Prov.", key="prov_key", max_chars=2)
    
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- SEZIONE RICERCA (Ripristinata e Corretta) ---
st.subheader("🔍 Ricerca nell'Archivio")

# 1. Filtri
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca nome, città o nota...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Filtra Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

# 2. Logica di caricamento (si attiva se tocchi i filtri)
if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    conn = sqlite3.connect('crm_mobile.db')
    # Carica TUTTO prima, poi filtra in Python (più sicuro)
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    conn.close()

    # Applica Filtro Testo
    if t_ricerca:
        df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    
    # Applica Filtro Data
    if isinstance(periodo, list) and len(periodo) == 2:
        start_date = periodo[0].strftime("%Y-%m-%d")
        end_date = periodo[1].strftime("%Y-%m-%d")
        df = df[(df['data_ordine'] >= start_date) & (df['data_ordine'] <= end_date)]
    
    # Applica Filtro Agente
    if f_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['agente'] == f_agente]

    if not df.empty:
        # Tasto Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        st.download_button("📊 SCARICA EXCEL", output.getvalue(), "report_visite.xlsx", use_container_width=True)

        # Mostra risultati
        st.caption(f"Trovate {len(df)} visite.")
        for _, row in df.iterrows():
            icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            titolo = f"{icon} {row['agente']} | {row['data']} - {row['cliente']}"
            with st.expander(titolo):
                st.write(f"**📍 Città:** {row['localita']} ({row['provincia']})")
                st.write(f"**📝 Note:** {row['note']}")
                
                # Link Mappa se c'è GPS
                if row['latitudine']:
                    # Link universale Google Maps
                    link = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.markdown(f"[📍 Vedi posizione su Mappa]({link})")
                
                if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db')
                    c = conn.cursor()
                    c.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.rerun()
    else:
        st.info("Nessuna visita trovata con questi filtri.")
else:
    st.info("👆 Usa i filtri sopra per cercare nell'archivio.")