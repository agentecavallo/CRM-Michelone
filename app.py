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
if 'delete_mode_id' not in st.session_state: st.session_state.delete_mode_id = None

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

# --- 2. FUNZIONI DI SUPPORTO ---

def copia_negli_appunti(testo, id_bottone):
    """Componente HTML/JS per copiare il testo negli appunti dello smartphone"""
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
    cliente = s.get('cliente_key', '').strip()
    note = s.get('note_key', '').strip()
    
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
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_cliente_key, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
            conn.commit()
        
        # Reset campi
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.toast("✅ Visita registrata!", icon="💾")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True): 
    st.radio("Stato", ["🤝 Cliente", "🚀 Prospect"], horizontal=True, key="tipo_cliente_key")
    st.text_input("Nome Cliente", key="cliente_key")
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    # GPS
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
    with c1: st.date_input("Data Visita", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note Visita", key="note_key", height=120)
    st.radio("Pianifica Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True, type="primary")

st.divider()

# --- 4. ARCHIVIO E RICERCA ---
st.subheader("🔍 Archivio e Ricerca")
col_search, col_agente = st.columns([2, 1])
t_ricerca = col_search.text_input("Cerca cliente o città")
f_agente = col_agente.selectbox("Filtro Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 MOSTRA / AGGIORNA ARCHIVIO", use_container_width=True):
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
            db_id = row['id']
            # Gestione ID "nan" per sicurezza
            id_visibile = int(db_id) if pd.notnull(db_id) else "N.D."
            ukey = f"rec_{id_visibile}"
            
            with st.expander(f"🆔 {id_visibile} | {row['cliente']} ({row['data']})"):
                
                if st.session_state.edit_mode_id == ukey:
                    # MODALITÀ EDIT
                    new_c = st.text_input("Modifica Cliente", value=row['cliente'], key=f"ec_{ukey}")
                    new_n = st.text_area("Modifica Note", value=row['note'], key=f"en_{ukey}")
                    ce1, ce2 = st.columns(2)
                    if ce1.button("💾 AGGIORNA", key=f"up_{ukey}", type="primary", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("UPDATE visite SET cliente=?, note=? WHERE id=?", (new_c, new_n, db_id))
                        st.session_state.edit_mode_id = None
                        st.rerun()
                    if ce2.button("❌ ANNULLA", key=f"can_{ukey}", use_container_width=True):
                        st.session_state.edit_mode_id = None
                        st.rerun()
                else:
                    # MODALITÀ VISTA
                    st.write(f"**📍 Località:** {row['localita']} ({row['provincia']})")
                    st.write(f"**👤 Agente:** {row['agente']} | **Tipo:** {row['tipo_cliente']}")
                    st.info(f"**Note:** {row['note']}")
                    
                    # Tasto Copia
                    copia_negli_appunti(row['note'].replace("`", "'"), f"cp_{ukey}")
                    
                    st.divider()
                    cm, ce = st.columns(2)
                    if cm.button("✏️ Modifica", key=f"btn_ed_{ukey}", use_container_width=True):
                        st.session_state.edit_mode_id = ukey
                        st.rerun()
                    
                    if ce.button("🗑️ Elimina", key=f"btn_del_{ukey}", use_container_width=True):
                        st.session_state.delete_mode_id = ukey
                        st.rerun()
                    
                    # Conferma Eliminazione
                    if st.session_state.delete_mode_id == ukey:
                        st.warning("Sei sicuro?")
                        if st.button("SÌ, ELIMINA", key=f"conf_{ukey}", type="primary", use_container_width=True):
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("DELETE FROM visite WHERE id=?", (db_id,))
                            st.session_state.delete_mode_id = None
                            st.rerun()
    else:
        st.warning("Nessun record trovato.")

# --- 5. BACKUP E RESET ---
st.divider()
with st.expander("🛠️ STRUMENTI E BACKUP"):
    # Export Excel
    with sqlite3.connect('crm_mobile.db') as conn:
        df_all = pd.read_sql_query("SELECT * FROM visite", conn)
    if not df_all.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_all.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "archivio_crm.xlsx", use_container_width=True)
    
    st.markdown("---")
    # Reset Totale
    st.error("Zona Pericolosa")
    if st.button("🔥 RESET COMPLETO DATABASE"):
        with sqlite3.connect('crm_mobile.db') as conn:
            conn.execute("DROP TABLE IF EXISTS visite")
        st.rerun()

# Logo finale
try:
    st.image("logo.jpg", width=150)
    st.caption("CRM Michelone Approved")
except:
    st.markdown("<center>✅ <b>MICHELONE APPROVED</b></center>", unsafe_allow_html=True)
