import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
import time
import base64
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation
import streamlit.components.v1 as components

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

# --- LOGICA PER IL LOGO IN BASSO A DESTRA ---
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def inserisci_logo(file_path):
    if os.path.exists(file_path):
        bin_str = get_base64_of_bin_file(file_path)
        st.markdown(
            f"""
            <style>
            .footer-logo {{
                position: fixed;
                bottom: 10px;
                right: 10px;
                width: 100px; /* Puoi regolare la larghezza qui */
                z-index: 100;
            }}
            </style>
            <img src="data:image/jpg;base64,{bin_str}" class="footer-logo">
            """,
            unsafe_allow_stdio=True,
            unsafe_allow_html=True
        )

# Richiamiamo il logo (apparirà in sovrimpressione in basso a destra)
inserisci_logo("logo.jpg")

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
    html_code = f"""
    <button id="btn_{id_bottone}" style="
        background-color: #f0f2f6; 
        border: 1px solid #dcdfe3; 
        border-radius: 5px; 
        padding: 5px 10px; 
        cursor: pointer;
        width: 100%;
        font-weight: bold;
        color: #31333F;">
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
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
            giorni_da_aggiungere = giorni.get(scelta, 0)
            if giorni_da_aggiungere > 0:
                data_fup = (s.data_key + timedelta(days=giorni_da_aggiungere)).strftime("%Y-%m-%d")
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), "", 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, 
                       s.lat_val, s.lon_val))
            conn.commit()
        st.session_state.cliente_key = ""; st.session_state.localita_key = ""; st.session_state.prov_key = ""
        st.session_state.note_key = ""; st.session_state.lat_val = ""; st.session_state.lon_val = ""
        st.session_state.fup_opt = "No"
        st.toast("✅ Visita salvata!", icon="💾")
        time.sleep(1); st.rerun()
    else: st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.text_input("Nome Cliente", key="cliente_key")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)
    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'CRM_Michelone/1.0'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', '')
                prov_sigla = "RM" if prov_full and ("Roma" in prov_full or "Rome" in prov_full) else (prov_full[:2].upper() if prov_full else "??")
                st.session_state['gps_temp'] = {'citta': citta.upper() if citta else "", 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Impossibile recuperare i dettagli dell'indirizzo.")
        else: st.warning("⚠️ Consenti la geolocalizzazione nel browser.")

    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: **{d['citta']} ({d['prov']})**")
        c_yes, c_no = st.columns(2)
        with c_yes: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
        with c_no: 
            if st.button("❌ ANNULLA", use_container_width=True): 
                del st.session_state['gps_temp']; st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        try:
            d_scad = datetime.strptime(row['data_followup'], "%Y-%m-%d")
            giorni_ritardo = (datetime.strptime(oggi, "%Y-%m-%d") - d_scad).days
            msg_scadenza = "Scade OGGI" if giorni_ritardo == 0 else f"Scaduto da {giorni_ritardo} gg"
        except: msg_scadenza = "Scaduto"
        with st.container(border=True):
            st.markdown(f"**{row['cliente']}** - {row['localita']}")
            st.caption(f"📅 {msg_scadenza} | Note: {row['note']}")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if st.button("+1 ☀️", key=f"p1_{row['id']}", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), row['id']))
                    st.rerun()
            with c2:
                if st.button("+7 📅", key=f"p7_{row['id']}", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), row['id']))
                    st.rerun()
            with c3:
                if st.button("✅ Fatto", key=f"ok_{row['id']}", type="primary", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    st.rerun()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
periodo = f2.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
f_agente = f3.selectbox("Filtra Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 CERCA VISITE", use_container_width=True):
    st.session_state.ricerca_attiva = True; st.session_state.edit_mode_id = None 

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
         df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        if st.button("❌ Chiudi Ricerca"):
            st.session_state.ricerca_attiva = False; st.rerun()

        for _, row in df.iterrows():
            with st.expander(f"{row['data']} - {row['cliente']} ({row['agente']})"):
                if st.session_state.edit_mode_id == row['id']:
                    new_cliente = st.text_input("Cliente", value=row['cliente'], key=f"e_cli_{row['id']}")
                    lista_agenti = ["HSE", "BIENNE", "PALAGI", "SARDEGNA"]
                    try: idx_ag = lista_agenti.index(row['agente'])
                    except: idx_ag = 0
                    new_agente = st.selectbox("Agente", lista_agenti, index=idx_ag, key=f"e_ag_{row['id']}")
                    new_loc = st.text_input("Località", value=row['localita'], key=f"e_loc_{row['id']}")
                    new_prov = st.text_input("Prov.", value=row['provincia'], max_chars=2, key=f"e_prov_{row['id']}")
                    new_note = st.text_area("Note", value=row['note'], height=100, key=f"e_note_{row['id']}")
                    cs, cc = st.columns(2)
                    if cs.button("💾 SALVA", key=f"save_{row['id']}", type="primary"):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("""UPDATE visite SET cliente=?, localita=?, provincia=?, note=?, agente=? WHERE id=?""",
                                         (new_cliente, new_loc.upper(), new_prov.upper(), new_note, new_agente, row['id']))
                        st.session_state.edit_mode_id = None; st.rerun()
                    if cc.button("❌ ANNULLA", key=f"canc_{row['id']}"):
                        st.session_state.edit_mode_id = None; st.rerun()
                else:
                    st.write(f"**Località:** {row['localita']} ({row['provincia']})")
                    st.write("**Note:**")
                    col_note, col_copia = st.columns([2, 1])
                    with col_note: st.info(row['note'])
                    with col_copia: copia_negli_appunti(row['note'].replace("`", "'"), row['id'])
                    if row['data_followup']:
                        try: st.write(f"📅 **Ricontatto:** {datetime.strptime(row['data_followup'], '%Y-%m-%d').strftime('%d/%m/%Y')}")
                        except: pass
                    if row['latitudine'] and row['longitudine']:
                        st.markdown(f"[📍 Mappa](http://googleusercontent.com/maps.google.com/maps?q={row['latitudine']},{row['longitudine']})")
                    cb_m, cb_d = st.columns([1, 1])
                    if cb_m.button("✏️ Modifica", key=f"btn_mod_{row['id']}"):
                        st.session_state.edit_mode_id = row['id']; st.rerun()
                    key_conf = f"confirm_del_{row['id']}"
                    if cb_d.button("🗑️ Elimina", key=f"btn_del_{row['id']}"):
                        st.session_state[key_conf] = True; st.rerun()
                    if st.session_state.get(key_conf, False):
                        st.warning("⚠️ Sicuro?"); cy, cn = st.columns(2)
                        if cy.button("SÌ", key=f"yes_{row['id']}", type="primary"):
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                            st.rerun()
                        if cn.button("NO", key=f"no_{row['id']}"):
                            del st.session_state[key_conf]; st.rerun()
    else: st.warning("Nessun risultato trovato.")

# --- GESTIONE DATI ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE E BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA DATABASE (EXCEL)", output.getvalue(), "backup_crm.xlsx", use_container_width=True)
    st.markdown("---"); st.write("📤 **RIPRISTINO DATI**")
    file_caricato = st.file_uploader("Seleziona il file Excel di backup", type=["xlsx"])
    if file_caricato is not None:
        if st.button("⚠️ AVVIA RIPRISTINO (Sovrascrive tutto)", type="primary", use_container_width=True):
            try:
                df_ripristino = pd.read_excel(file_caricato)
                if 'cliente' in df_ripristino.columns:
                    with sqlite3.connect('crm_mobile.db') as conn:
                        df_ripristino.to_sql('visite', conn, if_exists='replace', index=False)
                    st.success("✅ Database ripristinato!"); time.sleep(2); st.rerun()
                else: st.error("❌ File non valido.")
            except Exception as e: st.error(f"Errore: {e}")
