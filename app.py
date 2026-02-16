import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

# Inizializzazione chiavi di stato per evitare errori di widget duplicati o mancanti
if 'lat_val' not in st.session_state: st.session_state.lat_val = ""
if 'lon_val' not in st.session_state: st.session_state.lon_val = ""
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None
if 'delete_mode_id' not in st.session_state: st.session_state.delete_mode_id = None

def inizializza_db():
    with sqlite3.connect('crm_mobile.db') as conn:
        c = conn.cursor()
        # id INTEGER PRIMARY KEY AUTOINCREMENT assicura che ogni nuovo contatto riceva un numero univoco
        c.execute('''CREATE TABLE IF NOT EXISTS visite 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       cliente TEXT, localita TEXT, provincia TEXT,
                       tipo_cliente TEXT, data TEXT, note TEXT,
                       data_followup TEXT, data_ordine TEXT, agente TEXT,
                       latitudine TEXT, longitudine TEXT)''')
        conn.commit()

inizializza_db()

# --- FUNZIONE JAVASCRIPT PER COPIARE ---
def copia_negli_appunti(testo, id_bottone):
    html_code = f"""
    <button id="btn_{id_bottone}" style="
        background-color: #f0f2f6; border: 1px solid #dcdfe3; border-radius: 5px; 
        padding: 5px 10px; cursor: pointer; width: 100%; font-weight: bold; color: #31333F;">
        📋 COPIA NOTE
    </button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        const text = `{testo}`;
        navigator.clipboard.writeText(text).then(function() {{
            alert("Note copiate negli appunti!");
        }}, function(err) {{
            console.error('Errore nel copia:', err);
        }});
    }};
    </script>
    """
    components.html(html_code, height=45)

# --- 2. FUNZIONI DI SUPPORTO ---

def salva_visita():
    s = st.session_state
    cliente = s.get('cliente_key', '').strip()
    note = s.get('note_key', '').strip()
    tipo_cli = s.get('tipo_cliente_key', '🤝 Cliente')
    
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            
            # Calcolo Follow-up
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}.get(scelta, 0)
            if giorni > 0:
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            
            # Inserimento record: l'ID viene creato qui automaticamente dal DB
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), tipo_cli, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
            conn.commit()
        
        # Reset dei campi dopo il salvataggio
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.ricerca_attiva = False # Forza la ricarica dell'archivio
        
        st.toast("✅ Visita registrata con ID assegnato!", icon="💾")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

# REGISTRAZIONE NUOVA VISITA
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.radio("Seleziona Tipo", ["🤝 Cliente", "🚀 Prospect"], horizontal=True, key="tipo_cliente_key")
    st.text_input("Nome Cliente", key="cliente_key")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 USA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'CRM'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov = a.get('county', '')[:2].upper()
                st.session_state.localita_key = citta.upper()
                st.session_state.prov_key = prov
                st.session_state.lat_val, st.session_state.lon_val = str(lat), str(lon)
                st.toast("📍 Posizione acquisita!")
            except: st.warning("Errore GPS.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=120)
    st.radio("Pianifica Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ARCHIVIO E RICERCA (Dove gestiamo gli ID) ---
st.subheader("🔍 Archivio e Gestione")
col_search, col_agente = st.columns([2, 1])
t_ricerca = col_search.text_input("Cerca per nome o città")
f_agente = col_agente.selectbox("Filtro Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 VISUALIZZA / CERCA", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]

    if not df.empty:
        for idx, row in df.iterrows():
            # CHIAVE UNICA: Usiamo l'ID reale del database per non sbagliare mai riga
            db_id = row['id']
            ukey = f"rec_{db_id}_{idx}"
            
            with st.expander(f"{row['tipo_cliente']} - {row['cliente']} ({row['data']})"):
                
                if st.session_state.edit_mode_id == ukey:
                    # MODO MODIFICA
                    new_c = st.text_input("Cliente", value=row['cliente'], key=f"ec_{ukey}")
                    new_n = st.text_area("Note", value=row['note'], key=f"en_{ukey}")
                    col1, col2 = st.columns(2)
                    if col1.button("💾 AGGIORNA", key=f"up_{ukey}", type="primary", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("UPDATE visite SET cliente=?, note=? WHERE id=?", (new_c, new_n, db_id))
                        st.session_state.edit_mode_id = None
                        st.rerun()
                    if col2.button("❌ ANNULLA", key=f"can_{ukey}", use_container_width=True):
                        st.session_state.edit_mode_id = None
                        st.rerun()
                else:
                    # MODO VISUALIZZAZIONE
                    st.write(f"**📍 Località:** {row['localita']} ({row['provincia']})")
                    st.info(f"**Note:** {row['note']}")
                    copia_negli_appunti(row['note'].replace("`", "'"), f"cp_{ukey}")
                    
                    st.divider()
                    cm, ce = st.columns(2)
                    if cm.button("✏️ Modifica", key=f"medit_{ukey}", use_container_width=True):
                        st.session_state.edit_mode_id = ukey
                        st.rerun()
                    if ce.button("🗑️ Elimina", key=f"mdel_{ukey}", use_container_width=True):
                        st.session_state.delete_mode_id = ukey
                        st.rerun()
                    
                    if st.session_state.delete_mode_id == ukey:
                        st.error("Confermi l'eliminazione definitiva?")
                        if st.button("SÌ, ELIMINA ORA", key=f"confdel_{ukey}", type="primary", use_container_width=True):
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("DELETE FROM visite WHERE id=?", (db_id,))
                            st.session_state.delete_mode_id = None
                            st.rerun()
    else:
        st.warning("Nessun contatto trovato.")

# --- BACKUP E AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ BACKUP E LOGO"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_all = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_all.to_excel(writer, index=False)
    st.download_button("📥 SCARICA TUTTO IN EXCEL", output.getvalue(), "crm_michelone.xlsx", use_container_width=True)

# LOGO FINALE
col_f1, col_f2, col_f3 = st.columns([1, 2, 1]) 
with col_f2:
    try:
        st.image("logo.jpg", use_container_width=True)
        st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
    except: st.info("✅ Michelone Approved")
