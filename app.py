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
if 'id_in_modifica' not in st.session_state: st.session_state.id_in_modifica = None
if 'id_in_eliminazione' not in st.session_state: st.session_state.id_in_eliminazione = None

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
    safe_text = testo.replace("`", "'").replace('"', '\\"')
    html_code = f"""
    <button id="btn_{id_bottone}" style="
        background-color: #f0f2f6; border: 1px solid #dcdfe3; border-radius: 5px; 
        padding: 5px 10px; cursor: pointer; width: 100%; font-weight: bold; color: #31333F;">
        📋 COPIA NOTE
    </button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        navigator.clipboard.writeText("{safe_text}").then(function() {{
            alert("Note copiate!");
        }});
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
        file_piu_recente = max([os.path.join(cartella_backup, f) for f in files], key=os.path.getctime)
        if datetime.now() - datetime.fromtimestamp(os.path.getctime(file_piu_recente)) > timedelta(days=7):
            fare_backup = True
    if fare_backup:
        with sqlite3.connect('crm_mobile.db') as conn:
            df = pd.read_sql_query("SELECT * FROM visite", conn)
            if not df.empty:
                df.to_excel(os.path.join(cartella_backup, f"Backup_Auto_{datetime.now().strftime('%Y-%m-%d')}.xlsx"), index=False)

controllo_backup_automatico()

def salva_visita():
    s = st.session_state
    if s.cliente_key and s.note_key:
        with sqlite3.connect('crm_mobile.db') as conn:
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}.get(s.fup_opt, 0)
            if giorni > 0:
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            
            conn.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                            data_followup, data_ordine, agente, latitudine, longitudine) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                         (s.cliente_key, s.localita_key.upper(), s.prov_key.upper(), s.tipo_cliente_key, 
                          data_visita_fmt, s.note_key, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
        st.toast("✅ Visita salvata!")
        time.sleep(0.5)
        st.rerun()

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.radio("Seleziona Tipo", ["🤝 Cliente", "🚀 Prospect"], horizontal=True, key="tipo_cliente_key")
    st.text_input("Nome Cliente", key="cliente_key")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        loc_data = get_geolocation()
        if loc_data:
            lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
            r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={'User-Agent': 'CRM'}).json()
            a = r.get('address', {})
            st.session_state.localita_key = a.get('city', a.get('town', a.get('village', ''))).upper()
            prov = a.get('county', '')
            st.session_state.prov_key = "RM" if "Roma" in prov else prov[:2].upper()
            st.session_state.lat_val, st.session_state.lon_val = str(lat), str(lon)
            st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    st.radio("Scadenza Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True, type="primary")

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}'", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} RICONTATTI SCADUTI!**")
    for idx_s, row_s in df_scadenze.iterrows():
        with st.container(border=True):
            st.write(f"**{row_s['cliente']}** ({row_s['localita']})")
            c1, c2, c3 = st.columns(3)
            uid_s = f"scad_{row_s['id']}_{idx_s}"
            if c1.button("+1 gg", key=f"p1_{uid_s}"):
                nuova = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup=? WHERE id=?", (nuova, row_s['id']))
                st.rerun()
            if c2.button("+7 gg", key=f"p7_{uid_s}"):
                nuova = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup=? WHERE id=?", (nuova, row_s['id']))
                st.rerun()
            if c3.button("✅ Fatto", key=f"ok_{uid_s}", type="primary"):
                with sqlite3.connect('crm_mobile.db') as conn: conn.execute("UPDATE visite SET data_followup='' WHERE id=?", (row_s['id'],))
                st.rerun()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
periodo = f2.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
f_agente = f3.selectbox("Filtra Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

with sqlite3.connect('crm_mobile.db') as conn:
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]
    if len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

if not df.empty:
    for i, row in df.iterrows():
        uid = f"{row['id']}_{i}"
        with st.expander(f"{row['tipo_cliente']} {row['data']} - {row['cliente']}"):
            
            if st.session_state.id_in_modifica == row['id']:
                # --- MODIFICA ---
                new_cli = st.text_input("Cliente", row['cliente'], key=f"e_c_{uid}")
                c_edit1, c_edit2 = st.columns(2)
                with c_edit1:
                    d_vis_curr = datetime.strptime(row['data'], "%d/%m/%Y").date()
                    new_d_vis = st.date_input("Data Visita", d_vis_curr, key=f"e_dv_{uid}")
                with c_edit2:
                    fup_curr = row['data_followup']
                    has_fup = bool(fup_curr)
                    enable_fup = st.checkbox("Pianifica Ricontatto", value=has_fup, key=f"e_ch_{uid}")
                    new_d_fup = None
                    if enable_fup:
                        try: d_fup_curr = datetime.strptime(fup_curr, "%Y-%m-%d").date()
                        except: d_fup_curr = datetime.now().date() + timedelta(days=7)
                        new_d_fup = st.date_input("Data Ricontatto", d_fup_curr, key=f"e_df_{uid}")
                new_note = st.text_area("Note", row['note'], key=f"e_n_{uid}")
                
                cs, cc = st.columns(2)
                if cs.button("💾 SALVA", key=f"save_{uid}", type="primary", use_container_width=True):
                    s_fmt, s_ord = new_d_vis.strftime("%d/%m/%Y"), new_d_vis.strftime("%Y-%m-%d")
                    s_fup = new_d_fup.strftime("%Y-%m-%d") if enable_fup and new_d_fup else ""
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("""UPDATE visite SET cliente=?, note=?, data=?, data_ordine=?, data_followup=? WHERE id=?""",
                                     (new_cli, new_note, s_fmt, s_ord, s_fup, row['id']))
                    st.session_state.id_in_modifica = None
                    st.rerun()
                if cc.button("❌ ANNULLA", key=f"canc_{uid}", use_container_width=True):
                    st.session_state.id_in_modifica = None
                    st.rerun()

            elif st.session_state.id_in_eliminazione == row['id']:
                # --- ELIMINAZIONE ---
                st.warning("Vuoi eliminare definitivamente questa visita?")
                cy, cn = st.columns(2)
                if cy.button("SÌ, ELIMINA", key=f"y_{uid}", type="primary"):
                    with sqlite3.connect('crm_mobile.db') as conn: conn.execute("DELETE FROM visite WHERE id=?", (row['id'],))
                    st.session_state.id_in_eliminazione = None
                    st.rerun()
                if cn.button("NO", key=f"n_{uid}"):
                    st.session_state.id_in_eliminazione = None
                    st.rerun()

            else:
                st.write(f"**Località:** {row['localita']} ({row['provincia']})")
                st.info(row['note'])
                if row['data_followup']:
                    st.write(f"📅 **Ricontatto:** {datetime.strptime(row['data_followup'], '%Y-%m-%d').strftime('%d/%m/%Y')}")
                copia_negli_appunti(row['note'], uid)
                c_b1, c_b2 = st.columns(2)
                if c_b1.button("✏️ Modifica", key=f"b_m_{uid}"):
                    st.session_state.id_in_modifica = row['id']
                    st.rerun()
                if c_b2.button("🗑️ Elimina", key=f"b_d_{uid}"):
                    st.session_state.id_in_eliminazione = row['id']
                    st.rerun()

# --- AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE E BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA EXCEL", output.getvalue(), "crm_backup.xlsx", use_container_width=True)
    st.markdown("---")
    file_rip = st.file_uploader("📤 RIPRISTINA DA EXCEL", type=["xlsx"])
    if file_rip and st.button("⚠️ AVVIA RIPRISTINO", type="primary"):
        df_rip = pd.read_excel(file_rip)
        with sqlite3.connect('crm_mobile.db') as conn:
            df_rip.to_sql('visite', conn, if_exists='replace', index=False)
        st.success("✅ Database ripristinato!")
        time.sleep(1)
        st.rerun()

# --- LOGO E FIRMA FINALE ---
st.write("") 
st.divider() 

col_f1, col_f2, col_f3 = st.columns([1, 2, 1]) 

with col_f2:
    try:
        # Carichiamo il logo.jpg
        st.image("logo.jpg", use_container_width=True)
        st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em; font-weight: bold;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
    except Exception:
        # Se il file logo.jpg non esiste
        st.info("✅ Michelone Approved")
