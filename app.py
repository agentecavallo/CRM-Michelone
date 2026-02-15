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
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        s.lat_val = ""; s.lon_val = ""; s.reminder_key = False
        st.toast("✅ Visita salvata!")
    else: st.error("⚠️ Compila i campi obbligatori!")

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

st.title("💼 CRM Visite Agenti")

# --- SEZIONE INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.markdown("---")
    # Geolocalizzazione
    loc_data = get_geolocation()
    if loc_data:
        lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
        st.session_state.lat_val, st.session_state.lon_val = str(lat), str(lon)
        
        if st.button("📍 RECUPERA CITTÀ E PROVINCIA", use_container_width=True):
            try:
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'CRM_Michelone'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                # Logica per sigla provincia
                prov = a.get('ISO3166-2-lvl4', '').split('-')[-1] # Prova a prendere RM, LT, ecc.
                if not prov or len(prov) > 2:
                    prov = a.get('county', '')
                
                if citta: st.session_state.localita_key = citta.upper()
                # Correzione manuale per Roma se il sistema sbaglia
                if "ROMA" in prov.upper(): st.session_state.prov_key = "RM"
                else: st.session_state.prov_key = prov[:2].upper()
                st.success(f"📍 Rilevato: {citta} ({st.session_state.prov_key})")
            except: st.warning("GPS OK, ma nomi non trovati. Scrivi a mano.")
    
    col_l, col_p = st.columns([4, 1])
    with col_l: st.text_input("Località", key="localita_key")
    with col_prov: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- SEZIONE RICERCA (RIPRISTINATA) ---
st.subheader("🔍 Ricerca nell'Archivio")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca nome, città o nota...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Filtra Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

# Caricamento dati per la ricerca
if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite", conn)
    conn.close()

    # Applichiamo i filtri
    if t_ricerca:
        df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    
    if isinstance(periodo, list) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]
    
    if f_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['agente'] == f_agente]

    if not df.empty:
        # Tasto Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        st.download_button("📊 SCARICA EXCEL", output.getvalue(), "report.xlsx", use_container_width=True)

        for _, row in df.sort_values(by='id', ascending=False).iterrows():
            icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            with st.expander(f"{icon} {row['agente']} | {row['data']} - {row['cliente']}"):
                st.write(f"**📍 Città:** {row['localita']} ({row['provincia']})")
                st.write(f"**📝 Note:** {row['note']}")
                if row['latitudine']:
                    link = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.markdown(f"[📍 Apri su Google Maps]({link})")
                if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                    c.execute("DELETE FROM visite WHERE id = ?", (row['id'],)); conn.commit(); conn.close()
                    st.rerun()
    else:
        st.info("Nessun risultato trovato.")
else:
    st.caption("Usa i filtri sopra per visualizzare lo storico.")