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

# Inizializzazione chiavi di stato
if 'lat_val' not in st.session_state: st.session_state.lat_val = ""
if 'lon_val' not in st.session_state: st.session_state.lon_val = ""
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None

def inizializza_db():
    with sqlite3.connect('crm_mobile.db') as conn:
        c = conn.cursor()
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
    clean_text = testo.replace("`", "'").replace("\n", " ")
    html_code = f"""
    <button id="btn_{id_bottone}" style="
        background-color: #f0f2f6; border: 1px solid #dcdfe3; 
        border-radius: 5px; padding: 5px 10px; cursor: pointer;
        width: 100%; font-weight: bold; color: #31333F;">
        📋 COPIA NOTE
    </button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        navigator.clipboard.writeText(`{clean_text}`).then(function() {{
            alert("Note copiate!");
        }});
    }};
    </script>
    """
    components.html(html_code, height=45)

# --- 2. FUNZIONI DI SUPPORTO ---

def salva_visita():
    s = st.session_state
    if s.cliente_key and s.note_key:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
            if s.fup_opt in giorni:
                data_fup = (s.data_key + timedelta(days=giorni[s.fup_opt])).strftime("%Y-%m-%d")
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (s.cliente_key, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                       data_visita_fmt, s.note_key, data_fup, data_ord, s.agente_key, 
                       s.lat_val, s.lon_val))
            conn.commit()
        st.toast("✅ Visita salvata!", icon="💾")
        # Reset campi
        for k in ['cliente_key', 'localita_key', 'prov_key', 'note_key', 'lat_val', 'lon_val']: st.session_state[k] = ""
    else:
        st.error("⚠️ Compila Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

# --- REGISTRAZIONE ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False):
    st.text_input("Nome Cliente", key="cliente_key")
    st.selectbox("Tipo Cliente", ["Prospect", "Cliente"], key="tipo_key")
    c_loc, c_pr = st.columns([3, 1])
    with c_loc: st.text_input("Località", key="localita_key")
    with c_pr: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    loc_data = get_geolocation()
    if st.button("📍 POSIZIONE GPS", use_container_width=True):
        if loc_data:
            lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
            try:
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'CRM'}).json()
                a = r.get('address', {})
                st.session_state.localita_key = a.get('city', a.get('town', '')).upper()
                st.session_state.prov_key = a.get('county', '')[:2].upper()
                st.session_state.lat_val, st.session_state.lon_val = str(lat), str(lon)
                st.success("📍 Posizione acquisita!")
            except: st.error("Errore GPS")

    st.date_input("Data", datetime.now(), key="data_key")
    st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key")
    st.radio("Pianifica Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE (IN ROSSO) ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scad = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}'", conn)

if not df_scad.empty:
    st.subheader("🚨 SCADENZE DA RICONTATTARE")
    for _, row in df_scad.iterrows():
        with st.error(): # Riquadro Rosso
            st.markdown(f"### ⚠️ {row['cliente']}")
            st.write(f"📍 {row['localita']} | 📅 Scadenza: {row['data_followup']}")
            st.caption(f"Note: {row['note']}")
            c1, c2, c3 = st.columns(3)
            with c1: 
                if st.button("+1gg", key=f"s1_{row['id']}"):
                    nuova = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                    with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup=? WHERE id=?", (nuova, row['id']))
                    st.rerun()
            with c2:
                if st.button("+7gg", key=f"s7_{row['id']}"):
                    nuova = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup=? WHERE id=?", (nuova, row['id']))
                    st.rerun()
            with c3:
                if st.button("OK ✅", key=f"sk_{row['id']}", type="primary"):
                    with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup='' WHERE id=?", (row['id'],))
                    st.rerun()

# --- RICERCA (CHIUSA DI DEFAULT) ---
with st.expander("🔍 RICERCA E ARCHIVIO", expanded=False):
    f_testo = st.text_input("Cerca Cliente o Città")
    f_agente = st.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])
    if st.button("🔎 AVVIA RICERCA", use_container_width=True):
        st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    if f_testo: df = df[df['cliente'].str.contains(f_testo, case=False) | df['localita'].str.contains(f_testo, case=False)]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]
    
    st.write(f"Trovati: {len(df)}")
    if st.button("❌ Chiudi"): 
        st.session_state.ricerca_attiva = False
        st.rerun()
        
    for _, row in df.iterrows():
        with st.expander(f"{row['data']} - {row['cliente']}"):
            st.write(f"**Località:** {row['localita']} | **Agente:** {row['agente']}")
            st.info(row['note'])
            copia_negli_appunti(row['note'], row['id'])
            if row['latitudine']:
                st.markdown(f"[📍 Apri in Maps](https://www.google.com/maps?q={row['latitudine']},{row['longitudine']})")
            if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("DELETE FROM visite WHERE id=?", (row['id'],))
                st.rerun()

# --- AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA EXCEL", output.getvalue(), "backup.xlsx")

st.markdown("<p style='text-align: center; color: grey;'>CRM Michelone Approved ✅</p>", unsafe_allow_html=True)
