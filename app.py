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

# Inizializzazione stati
if 'lat_val' not in st.session_state: st.session_state.lat_val = ""
if 'lon_val' not in st.session_state: st.session_state.lon_val = ""
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None
if 'delete_mode_id' not in st.session_state: st.session_state.delete_mode_id = None

def inizializza_db():
    with sqlite3.connect('crm_mobile.db') as conn:
        c = conn.cursor()
        # Assicuriamoci che l'ID sia INTEGER PRIMARY KEY AUTOINCREMENT
        c.execute('''CREATE TABLE IF NOT EXISTS visite 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       cliente TEXT, localita TEXT, provincia TEXT,
                       tipo_cliente TEXT, data TEXT, note TEXT,
                       data_followup TEXT, data_ordine TEXT, agente TEXT,
                       latitudine TEXT, longitudine TEXT)''')
        conn.commit()

inizializza_db()

# --- FUNZIONE COPIA ---
def copia_negli_appunti(testo, id_bottone):
    html_code = f"""
    <button id="btn_{id_bottone}" style="background-color: #f0f2f6; border: 1px solid #dcdfe3; border-radius: 5px; padding: 5px 10px; cursor: pointer; width: 100%; font-weight: bold;">📋 COPIA NOTE</button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        navigator.clipboard.writeText(`{testo}`).then(function() {{ alert("Copiato!"); }});
    }};
    </script>
    """
    components.html(html_code, height=45)

# --- 2. SALVATAGGIO ---
def salva_visita():
    s = st.session_state
    cliente = s.get('cliente_key', '').strip()
    note = s.get('note_key', '').strip()
    
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}.get(scelta, 0)
            if giorni > 0:
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            
            # NOTA: Non inseriamo l'ID, lasciamo che SQLite lo crei
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_cliente_key, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
            conn.commit()
            
        # Reset campi
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.ricerca_attiva = False
        st.toast("✅ Contatto Salvato con successo!")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error("⚠️ Inserisci Cliente e Note!")

# --- 3. INTERFACCIA ---
st.title("💼 CRM Michelone")

with st.expander("➕ NUOVA VISITA", expanded=False): 
    st.radio("Tipo", ["🤝 Cliente", "🚀 Prospect"], key="tipo_cliente_key", horizontal=True)
    st.text_input("Nome Cliente", key="cliente_key")
    col_l, col_p = st.columns([3, 1])
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    if st.button("📍 GPS", use_container_width=True):
        loc = get_geolocation()
        if loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            st.session_state.lat_val, st.session_state.lon_val = str(lat), str(lon)
            st.success("Posizione acquisita!")

    st.date_input("Data", datetime.now(), key="data_key")
    st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key")
    st.radio("Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ARCHIVIO ---
st.subheader("🔍 Ricerca")
t_ricerca = st.text_input("Cerca nome...")

if st.button("🔎 CERCA", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False)]

    for idx, row in df.iterrows():
        # CONTROLLO CRITICO: Se l'ID è None, mostriamo un avviso
        db_id = row['id']
        if db_id is None:
            st.error(f"⚠️ Errore: Il contatto '{row['cliente']}' non ha ID. Elimina il file crm_mobile.db.")
            continue
            
        ukey = f"id_{db_id}" # Chiave basata SOLO sull'ID del database
        
        with st.expander(f"ID: {db_id} | {row['cliente']} ({row['data']})"):
            if st.session_state.edit_mode_id == ukey:
                new_c = st.text_input("Modifica Nome", value=row['cliente'], key=f"edit_c_{ukey}")
                new_n = st.text_area("Modifica Note", value=row['note'], key=f"edit_n_{ukey}")
                if st.button("💾 AGGIORNA", key=f"up_{ukey}", type="primary"):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET cliente=?, note=? WHERE id=?", (new_c, new_n, db_id))
                    st.session_state.edit_mode_id = None
                    st.rerun()
                if st.button("ANNULLA", key=f"can_{ukey}"):
                    st.session_state.edit_mode_id = None
                    st.rerun()
            else:
                st.write(f"**Città:** {row['localita']}")
                st.info(row['note'])
                copia_negli_appunti(row['note'].replace("`", "'"), f"cp_{ukey}")
                
                c1, c2 = st.columns(2)
                if c1.button("✏️ Modifica", key=f"ed_{ukey}", use_container_width=True):
                    st.session_state.edit_mode_id = ukey
                    st.rerun()
                if c2.button("🗑️ Elimina", key=f"del_{ukey}", use_container_width=True):
                    st.session_state.delete_mode_id = ukey
                    st.rerun()
                
                if st.session_state.delete_mode_id == ukey:
                    if st.button("CONFERMA ELIMINAZIONE", key=f"conf_{ukey}", type="primary", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("DELETE FROM visite WHERE id=?", (db_id,))
                        st.session_state.delete_mode_id = None
                        st.rerun()

# --- BACKUP ---
with st.expander("🛠️ AMMINISTRAZIONE"):
    if st.button("🗑️ CANCELLA DATABASE E RICREALO (Usa in caso di errori ID)"):
        if os.path.exists('crm_mobile.db'):
            os.remove('crm_mobile.db')
            st.success("Database rimosso. Ricarica la pagina!")
            time.sleep(1)
            st.rerun()
