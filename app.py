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

def copia_negli_appunti(testo, id_bottone):
    html_code = f"""
    <button id="btn_{id_bottone}" style="background-color: #f0f2f6; border: 1px solid #dcdfe3; border-radius: 5px; padding: 5px 10px; cursor: pointer; width: 100%; font-weight: bold; color: #31333F;">
        📋 COPIA NOTE
    </button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        const text = `{testo}`;
        navigator.clipboard.writeText(text).then(function() {{ alert("Note copiate!"); }}, function(err) {{ console.error('Errore:', err); }});
    }};
    </script>
    """
    components.html(html_code, height=45)

# --- 2. FUNZIONI DI SUPPORTO ---
def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup): os.makedirs(cartella_backup)
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
                    df.to_excel(os.path.join(cartella_backup, f"Backup_Auto_{datetime.now().strftime('%Y-%m-%d')}.xlsx"), index=False)
                    st.toast("🛡️ Backup Settimanale Eseguito!", icon="✅")
            except: pass 

controllo_backup_automatico()

def salva_visita():
    s = st.session_state
    cliente = s.get('cliente_key', '').strip()
    note = s.get('note_key', '').strip()
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
            if scelta in giorni:
                data_fup = (s.data_key + timedelta(days=giorni[scelta])).strftime("%Y-%m-%d")
            
            conn.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
            conn.commit()
        for k in ['cliente_key', 'localita_key', 'prov_key', 'note_key', 'lat_val', 'lon_val']: st.session_state[k] = ""
        st.toast("✅ Visita salvata!", icon="💾")
        time.sleep(1)
        st.rerun()
    else: st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.text_input("Nome Cliente", key="cliente_key")
    st.selectbox("Stato", ["Prospect", "Cliente"], key="tipo_key")
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'CRM_App'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov = a.get('county', '')[:2].upper()
                st.session_state['gps_temp'] = {'citta': citta.upper(), 'prov': prov, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Errore GPS.")
    
    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: {d['citta']}")
        if st.button("✅ INSERISCI DATI GPS"):
            st.session_state.localita_key, st.session_state.prov_key = d['citta'], d['prov']
            st.session_state.lat_val, st.session_state.lon_val = d['lat'], d['lon']
            del st.session_state['gps_temp']
            st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=100)
    st.radio("Pianifica Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}'", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **RICONTATTARE {len(df_scadenze)} CLIENTI!**")
    for _, row in df_scadenze.iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['cliente']}** ({row['tipo_cliente']}) - {row['localita']}")
            c1, c2, c3 = st.columns(3)
            if c1.button("+1 gg", key=f"p1_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup=? WHERE id=?", ((datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d"), row['id']))
                st.rerun()
            if c2.button("+7 gg", key=f"p7_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup=? WHERE id=?", ((datetime.now()+timedelta(days=7)).strftime("%Y-%m-%d"), row['id']))
                st.rerun()
            if c3.button("✅ OK", key=f"ok_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup='' WHERE id=?", (row['id'],))
                st.rerun()

# --- ARCHIVIO ---
st.subheader("🔍 Archivio")
f1, f2, f3, f4 = st.columns([1.5, 1, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente/Città")
f_agente = f2.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])
f_tipo = f3.selectbox("Tipo", ["Tutti", "Prospect", "Cliente"])
periodo = f4.date_input("Dal/Al", [datetime.now()-timedelta(days=90), datetime.now()])

if st.button("🔎 AVVIA RICERCA", use_container_width=True): st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    if t_ricerca: df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]
    if f_tipo != "Tutti": df = df[df['tipo_cliente'] == f_tipo]
    
    for _, row in df.iterrows():
        tipo_label = f"[{row['tipo_cliente'].upper()}]" if row['tipo_cliente'] else ""
        with st.expander(f"{row['data']} - {row['cliente']} {tipo_label}"):
            if st.session_state.edit_mode_id == row['id']:
                new_cli = st.text_input("Cliente", row['cliente'], key=f"ec_{row['id']}")
                new_tp = st.selectbox("Stato", ["Prospect", "Cliente"], index=0 if row['tipo_cliente'] == "Prospect" else 1, key=f"et_{row['id']}")
                new_note = st.text_area("Note", row['note'], key=f"en_{row['id']}")
                
                fup_val = datetime.strptime(row['data_followup'], "%Y-%m-%d") if row['data_followup'] else datetime.now()
                attiva_fup = st.checkbox("Imposta Ricontatto", value=True if row['data_followup'] else False, key=f"efu_{row['id']}")
                new_fup = (st.date_input("Data", fup_val, key=f"ed_{row['id']}")).strftime("%Y-%m-%d") if attiva_fup else ""
                
                if st.button("💾 SALVA", key=f"s_{row['id']}", type="primary"):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET cliente=?, tipo_cliente=?, note=?, data_followup=? WHERE id=?", (new_cli, new_tp, new_note, new_fup, row['id']))
                    st.session_state.edit_mode_id = None
                    st.rerun()
            else:
                st.write(f"**Agente:** {row['agente']} | **Città:** {row['localita']}")
                st.info(row['note'])
                if row['data_followup']: st.warning(f"📅 Ricontatto: {row['data_followup']}")
                if st.button("✏️ Modifica", key=f"be_{row['id']}"):
                    st.session_state.edit_mode_id = row['id']
                    st.rerun()

# --- AMMINISTRAZIONE ---
with st.expander("🛠️ BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn: df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA EXCEL", output.getvalue(), "crm_michelone.xlsx")

st.divider()
col_f1, col_f2, col_f3 = st.columns([1, 2, 1]) 
with col_f2:
    try: st.image("logo.jpg", use_container_width=True)
    except: st.info("✅ Michelone Approved")
