import streamlit as st
import sqlite3
import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

DB_NAME = 'crm_mobile.db'

def inizializza_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS visite 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      cliente TEXT, localita TEXT, provincia TEXT,
                      tipo_cliente TEXT, data TEXT, note TEXT,
                      data_followup TEXT, data_ordine TEXT, agente TEXT,
                      latitudine TEXT, longitudine TEXT)''')
        conn.commit()

inizializza_db()

# Inizializzazione chiavi di stato
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None
if 'lat_val' not in st.session_state: st.session_state.lat_val = ""
if 'lon_val' not in st.session_state: st.session_state.lon_val = ""

# --- 2. FUNZIONI DI SUPPORTO ---

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
            alert("Note copiate!");
        }}, function(err) {{
            console.error('Errore:', err);
        }});
    }};
    </script>
    """
    components.html(html_code, height=45)

def salva_visita():
    s = st.session_state
    if s.get('cliente_key') and s.get('note_key'):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}.get(scelta, 0)
            if giorni > 0:
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (s.cliente_key, s.localita_key.upper(), s.prov_key.upper(), s.tipo_cliente_key, 
                       data_visita_fmt, s.note_key, data_fup, data_ord, s.agente_key, str(s.lat_val), str(s.lon_val)))
            conn.commit()
        
        # Reset campi
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.toast("✅ Salvato!", icon="💾")
        time.sleep(0.5)
        st.rerun()

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ NUOVA VISITA", expanded=True): 
    st.radio("Tipo", ["🤝 Cliente", "🚀 Prospect"], horizontal=True, key="tipo_cliente_key")
    st.text_input("Cliente", key="cliente_key")
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    # --- LOGICA GPS CORRETTA ---
    loc = get_geolocation() # Richiama il sensore GPS
    if st.button("📍 AGGIORNA POSIZIONE GPS", use_container_width=True):
        if loc and 'coords' in loc:
            lat = loc['coords']['latitude']
            lon = loc['coords']['longitude']
            st.session_state.lat_val = lat
            st.session_state.lon_val = lon
            
            # Tentativo di recuperare città e provincia via API (Gratuita)
            try:
                url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
                res = requests.get(url, headers={'User-Agent': 'CRM_Michelone_App'}).json()
                indirizzo = res.get('address', {})
                citta = indirizzo.get('city', indirizzo.get('town', indirizzo.get('village', '')))
                prov = indirizzo.get('county', '')[:2].upper()
                
                if citta: st.session_state.localita_key = citta.upper()
                if prov: st.session_state.prov_key = prov
                st.toast(f"📍 Posizione trovata: {citta}", icon="📍")
            except:
                st.toast("📍 Coordinate acquisite (Nome città non disponibile)", icon="⚠️")
        else:
            st.error("Assicurati di aver dato i permessi GPS al browser.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=100)
    st.radio("Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA", on_click=salva_visita, use_container_width=True, type="primary")

st.divider()

# --- 4. ARCHIVIO ---
st.subheader("🔍 Archivio")
if st.button("🔎 MOSTRA/AGGIORNA", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    
    for idx, row in df.iterrows():
        db_id = row['id']
        with st.expander(f"🆔 {db_id} | {row['cliente']} ({row['data']})"):
            if st.session_state.edit_mode_id == f"ed_{db_id}":
                new_c = st.text_input("Cliente", value=row['cliente'], key=f"c_{db_id}")
                new_n = st.text_area("Note", value=row['note'], key=f"n_{db_id}")
                if st.button("💾 AGGIORNA", key=f"up_{db_id}"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE visite SET cliente=?, note=? WHERE id=?", (new_c, new_n, db_id))
                    st.session_state.edit_mode_id = None
                    st.rerun()
            else:
                st.write(f"**Loc:** {row['localita']} | **Agente:** {row['agente']}")
                st.info(row['note'])
                copia_negli_appunti(row['note'].replace("`", "'"), f"cp_{db_id}")
                
                c1, c2 = st.columns(2)
                if c1.button("✏️ Modifica", key=f"btn_e_{db_id}"):
                    st.session_state.edit_mode_id = f"ed_{db_id}"
                    st.rerun()
                if c2.button("🗑️ Elimina", key=f"btn_d_{db_id}"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("DELETE FROM visite WHERE id=?", (db_id,))
                    st.rerun()

st.divider()

# --- 5. BACKUP & RIPRISTINO ---
with st.expander("📂 BACKUP E RIPRISTINO", expanded=False):
    st.write("### 📥 Esporta Dati")
    with sqlite3.connect(DB_NAME) as conn:
        df_back = pd.read_sql_query("SELECT * FROM visite", conn)
    
    if not df_back.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_back.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL (Download)", output.getvalue(), "crm_backup.xlsx", use_container_width=True)
        with open(DB_NAME, "rb") as f:
            st.download_button("💾 SCARICA FILE .DB (Per Ripristino)", f, "crm_mobile.db", use_container_width=True)

    st.write("---")
    st.write("### 📤 Ripristino Database")
    uploaded_file = st.file_uploader("Scegli un file crm_mobile.db", type="db")
    if uploaded_file is not None:
        if st.button("🔄 RIPRISTINA ORA", type="primary"):
            with open(DB_NAME, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success("Database ripristinato! Ricarica la pagina.")
            time.sleep(1)
            st.rerun()

st.markdown("<br><center>✅ MICHELONE APPROVED</center>", unsafe_allow_html=True)
