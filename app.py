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

def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup):
        os.makedirs(cartella_backup)
    
    files = [f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')]
    fare_backup = not files
    
    if files:
        percorsi_completi = [os.path.join(cartella_backup, f) for f in files]
        file_piu_recente = max(percorsi_completi, key=os.path.getctime)
        if datetime.now() - datetime.fromtimestamp(os.path.getctime(file_piu_recente)) > timedelta(days=7):
            fare_backup = True
            
    if fare_backup:
        with sqlite3.connect('crm_mobile.db') as conn:
            try:
                df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
                if not df.empty:
                    nome_file = f"Backup_Auto_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
                    df.to_excel(os.path.join(cartella_backup, nome_file), index=False)
                    st.toast("🛡️ Backup Settimanale Eseguito!", icon="✅")
            except: pass 

controllo_backup_automatico()

def applica_dati_gps():
    if 'gps_temp' in st.session_state:
        dati = st.session_state['gps_temp']
        st.session_state.localita_key = dati['citta']
        st.session_state.prov_key = dati['prov']
        st.session_state.lat_val = dati['lat']
        st.session_state.lon_val = dati['lon']
        del st.session_state['gps_temp']

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
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}.get(scelta, 0)
            if giorni > 0:
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), tipo_cli, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
            conn.commit()
        
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.session_state.lat_val = ""
        st.session_state.lon_val = ""
        st.session_state.fup_opt = "No"
        st.session_state.ricerca_attiva = False
        st.toast("✅ Visita salvata!", icon="💾")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.radio("Seleziona Tipo", ["🤝 Cliente", "🚀 Prospect"], horizontal=True, key="tipo_cliente_key")
    st.text_input("Nome Cliente", key="cliente_key")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'CRM'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov = a.get('county', '')
                prov_sigla = "RM" if "Roma" in prov or "Rome" in prov else prov[:2].upper()
                st.session_state['gps_temp'] = {'citta': citta.upper(), 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Errore geocodifica.")
    
    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: {d['citta']} ({d['prov']})")
        if st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True): st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scad = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)

if not df_scad.empty:
    st.error(f"⚠️ **DA RICONTATTARE: {len(df_scad)}**")
    for idx, row in df_scad.iterrows():
        ukey = f"scad_{row['id']}_{idx}"
        with st.container(border=True):
            st.markdown(f"**{row['cliente']}** - {row['localita']}")
            st.caption(f"Note: {row['note']}")
            c1, c2, c3 = st.columns(3)
            if c1.button("+1 ☀️", key=f"p1_{ukey}", use_container_width=True):
                nuova = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup=? WHERE id=?", (nuova, row['id']))
                st.rerun()
            if c2.button("+7 📅", key=f"p7_{ukey}", use_container_width=True):
                nuova = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup=? WHERE id=?", (nuova, row['id']))
                st.rerun()
            if c3.button("✅ OK", key=f"fatto_{ukey}", type="primary", use_container_width=True):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup='' WHERE id=?", (row['id'],))
                st.rerun()

# --- RICERCA ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
periodo = f2.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
f_agente = f3.selectbox("Filtra Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 CERCA VISITE", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    
    if t_ricerca: df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        for idx, row in df.iterrows():
            ukey = f"arch_{row['id']}_{idx}"
            with st.expander(f"{row['tipo_cliente']} {row['data']} - {row['cliente']}"):
                if st.session_state.edit_mode_id == ukey:
                    # --- FORM MODIFICA ---
                    new_c = st.text_input("Cliente", value=row['cliente'], key=f"edit_c_{ukey}")
                    new_l = st.text_input("Località", value=row['localita'], key=f"edit_l_{ukey}")
                    new_n = st.text_area("Note", value=row['note'], key=f"edit_n_{ukey}")
                    new_a = st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], index=["HSE", "BIENNE", "PALAGI", "SARDEGNA"].index(row['agente']), key=f"edit_a_{ukey}")
                    col1, col2 = st.columns(2)
                    if col1.button("💾 SALVA", key=f"save_{ukey}", type="primary", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("UPDATE visite SET cliente=?, localita=?, note=?, agente=? WHERE id=?", (new_c, new_l.upper(), new_n, new_a, row['id']))
                        st.session_state.edit_mode_id = None
                        st.rerun()
                    if col2.button("❌ ANNULLA", key=f"canc_{ukey}", use_container_width=True):
                        st.session_state.edit_mode_id = None
                        st.rerun()
                else:
                    # --- VISUALIZZAZIONE ---
                    st.write(f"**Agente:** {row['agente']} | **Località:** {row['localita']} ({row['provincia']})")
                    st.info(row['note'])
                    copia_negli_appunti(row['note'].replace("`", "'"), f"cp_{ukey}")
                    if row['latitudine']: st.markdown(f"[📍 Mappa](http://maps.google.com/?q={row['latitudine']},{row['longitudine']})")
                    
                    c_m, c_e = st.columns(2)
                    if c_m.button("✏️ Modifica", key=f"m_{ukey}", use_container_width=True):
                        st.session_state.edit_mode_id = ukey
                        st.rerun()
                    if c_e.button("🗑️ Elimina", key=f"e_{ukey}", use_container_width=True):
                        st.session_state.delete_mode_id = ukey
                        st.rerun()
                    
                    if st.session_state.delete_mode_id == ukey:
                        if st.button("CONFERMA ELIMINAZIONE", key=f"conf_{ukey}", type="primary", use_container_width=True):
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("DELETE FROM visite WHERE id=?", (row['id'],))
                            st.session_state.delete_mode_id = None
                            st.rerun()

# --- AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE E BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA EXCEL", output.getvalue(), "backup_crm.xlsx", use_container_width=True)
    
    file_caricato = st.file_uploader("Ripristina da Excel", type=["xlsx"])
    if file_caricato and st.button("⚠️ AVVIA RIPRISTINO", type="primary", use_container_width=True):
        df_rip = pd.read_excel(file_caricato)
        with sqlite3.connect('crm_mobile.db') as conn:
            df_rip.to_sql('visite', conn, if_exists='replace', index=False)
        st.success("✅ Ripristinato!")
        st.rerun()

# --- LOGO ---
st.divider()
col_f1, col_f2, col_f3 = st.columns([1, 2, 1]) 
with col_f2:
    try:
        st.image("logo.jpg", use_container_width=True)
        st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
    except: st.info("✅ Michelone Approved")
