import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation

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
        try:
            c.execute("ALTER TABLE visite ADD COLUMN copiato_crm INTEGER DEFAULT 0")
        except:
            pass 
        conn.commit()

inizializza_db()

# --- 2. FUNZIONI DI SUPPORTO ---
def calcola_prossimo_giorno(data_partenza, giorno_obiettivo):
    giorni_mancanti = giorno_obiettivo - data_partenza.weekday()
    if giorni_mancanti <= 0:
        giorni_mancanti += 7
    return (data_partenza + timedelta(days=giorni_mancanti)).strftime("%Y-%m-%d")

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
    tipo = s.get('tipo_key', 'Prospect')
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            if scelta in ["1 gg", "7 gg", "15 gg", "30 gg"]:
                giorni = int(scelta.split()[0])
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            elif scelta == "Prox. Lunedì":
                data_fup = calcola_prossimo_giorno(s.data_key, 0)
            elif scelta == "Prox. Venerdì":
                data_fup = calcola_prossimo_giorno(s.data_key, 4)
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine, copiato_crm) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), tipo, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, 
                       s.lat_val, s.lon_val))
            conn.commit()
        st.session_state.cliente_key = ""; st.session_state.localita_key = ""
        st.session_state.prov_key = ""; st.session_state.note_key = ""
        st.session_state.lat_val = ""; st.session_state.lon_val = ""
        st.session_state.fup_opt = "No"
        st.toast("✅ Visita salvata!", icon="💾")
    else: st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.text_input("Nome Cliente", key="cliente_key")
    st.selectbox("Tipo Cliente", ["Cliente", "Prospect"], key="tipo_key")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_Michelone_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', '')
                prov_sigla = "RM" if "Roma" in prov_full or "Rome" in prov_full else (prov_full[:2].upper() if prov_full else "??")
                st.session_state['gps_temp'] = {'citta': citta.upper() if citta else "", 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Impossibile recuperare i dettagli.")
        else: st.warning("⚠️ Consenti la geolocalizzazione.")

    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: **{d['citta']} ({d['prov']})**")
        c_yes, c_no = st.columns(2)
        with c_yes: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
        with c_no: 
            if st.button("❌ ANNULLA", use_container_width=True): 
                del st.session_state['gps_temp']
                st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg", "Prox. Lunedì", "Prox. Venerdì"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- 4. ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['cliente']}** ({row['tipo_cliente']}) - {row['localita']}")
            st.caption(f"📅 Scadenza: {row['data_followup']} | Note: {row['note']}")
            c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
            if c1.button("+1", key=f"p1_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), row['id']))
                st.rerun()
            if c2.button("+7", key=f"p7_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), row['id']))
                st.rerun()
            if c3.button("LUN", key=f"pl_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (calcola_prossimo_giorno(datetime.now(), 0), row['id']))
                st.rerun()
            if c4.button("VEN", key=f"pv_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (calcola_prossimo_giorno(datetime.now(), 4), row['id']))
                st.rerun()
            if c5.button("OK", key=f"ok_{row['id']}", type="primary"):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                st.rerun()

# --- 5. RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3, f4, f5 = st.columns([1.5, 1, 1, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
periodo = f2.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
f_agente = f3.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])
f_tipo = f4.selectbox("Tipo", ["Tutti", "Prospect", "Cliente"])
f_stato_crm = f5.selectbox("Stato CRM", ["Tutti", "Da Caricare", "Caricati"])

if st.button("🔎 CERCA VISITE", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    
    if t_ricerca: df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]
    if f_tipo != "Tutti": df = df[df['tipo_cliente'] == f_tipo]
    if f_stato_crm == "Da Caricare": df = df[(df['copiato_crm'] == 0) | (df['copiato_crm'].isnull())]
    elif f_stato_crm == "Caricati": df = df[df['copiato_crm'] == 1]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        for _, row in df.iterrows():
            badge = f"[{row['tipo_cliente']}]" if row['tipo_cliente'] else ""
            icona = "✅" if row.get('copiato_crm') == 1 else "🕒"
            with st.expander(f"{icona} {row['data']} - {row['cliente']} {badge}"):
                
                if st.session_state.edit_mode_id == row['id']:
                    # --- MODALITÀ MODIFICA (La tua originale) ---
                    new_cliente = st.text_input("Cliente", value=row['cliente'], key=f"e_cli_{row['id']}")
                    new_note = st.text_area("Note", value=row['note'], height=100, key=f"e_note_{row['id']}")
                    c_save, c_canc = st.columns(2)
                    if c_save.button("💾 SALVA", key=f"sv_{row['id']}", type="primary"):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("UPDATE visite SET cliente=?, note=? WHERE id=?", (new_cliente, new_note, row['id']))
                        st.session_state.edit_mode_id = None
                        st.rerun()
                    if c_canc.button("❌ ANNULLA", key=f"cn_{row['id']}"):
                        st.session_state.edit_mode_id = None
                        st.rerun()
                else:
                    # --- MODALITÀ VISUALIZZAZIONE (Con Soluzione Copia 2) ---
                    st.write(f"**Località:** {row['localita']} ({row['provincia']}) | **Agente:** {row['agente']}")
                    
                    st.write("📝 **Note:** (Clicca l'icona in alto a destra nel box per copiare)")
                    st.code(row['note'], language=None) # <-- ECCO LA SOLUZIONE 2
                    
                    is_copied = True if row.get('copiato_crm') == 1 else False
                    if st.checkbox("Salvato su CRM Ufficiale", value=is_copied, key=f"chk_crm_{row['id']}"):
                        if not is_copied:
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("UPDATE visite SET copiato_crm = 1 WHERE id = ?", (row['id'],))
                            st.rerun()
                    else:
                        if is_copied:
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("UPDATE visite SET copiato_crm = 0 WHERE id = ?", (row['id'],))
                            st.rerun()

                    c_mod, c_del = st.columns(2)
                    if c_mod.button("✏️ Modifica", key=f"m_{row['id']}", use_container_width=True):
                        st.session_state.edit_mode_id = row['id']
                        st.rerun()
                    if c_del.button("🗑️ Elimina", key=f"d_{row['id']}", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                        st.rerun()
    else: st.warning("Nessun risultato.")

# --- 6. AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE E BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA EXCEL", output.getvalue(), "backup_crm.xlsx", use_container_width=True)
    
    st.markdown("---")
    file_caricato = st.file_uploader("📤 RIPRISTINA DA EXCEL", type=["xlsx"])
    if file_caricato and st.button("⚠️ AVVIA RIPRISTINO", type="primary"):
        try:
            df_ripr = pd.read_excel(file_caricato)
            with sqlite3.connect('crm_mobile.db') as conn:
                df_ripr.to_sql('visite', conn, if_exists='replace', index=False)
            st.success("✅ Ripristino completato!")
            time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Errore: {e}")

st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
