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

def inizializza_db():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS visite 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cliente TEXT, localita TEXT, provincia TEXT,
                  tipo_cliente TEXT, data TEXT, note TEXT,
                  data_followup TEXT, data_ordine TEXT, agente TEXT,
                  latitudine TEXT, longitudine TEXT)''')
    conn.commit()
    conn.close()

# Avvio DB
inizializza_db()

# --- 2. FUNZIONI DI SUPPORTO ---

# --- BACKUP AUTOMATICO SETTIMANALE ---
def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup):
        os.makedirs(cartella_backup)
    
    files = [f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')]
    fare_backup = False
    
    if not files:
        fare_backup = True
    else:
        percorsi_completi = [os.path.join(cartella_backup, f) for f in files]
        file_piu_recente = max(percorsi_completi, key=os.path.getctime)
        if datetime.now() - datetime.fromtimestamp(os.path.getctime(file_piu_recente)) > timedelta(days=7):
            fare_backup = True
            
    if fare_backup:
        conn = sqlite3.connect('crm_mobile.db')
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
        conn.close()
        if not df.empty:
            nome_file = f"Backup_Auto_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            df.to_excel(os.path.join(cartella_backup, nome_file), index=False)
            st.toast(f"🛡️ Backup Settimanale Eseguito!", icon="✅")

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
    cliente = s.get('cliente_key', '')
    note = s.get('note_key', '')
    
    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        
        data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
        data_ord = s.data_key.strftime("%Y-%m-%d")
        
        scelta = s.get('fup_opt', 'No')
        data_fup = ""
        if scelta == "7 gg":
            data_fup = (s.data_key + timedelta(days=7)).strftime("%Y-%m-%d")
        elif scelta == "30 gg":
            data_fup = (s.data_key + timedelta(days=30)).strftime("%Y-%m-%d")
        
        lat = s.get('lat_val', "")
        lon = s.get('lon_val', "")
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, data_visita_fmt, note, data_fup, data_ord, s.agente_key, lat, lon))
        conn.commit()
        conn.close()
        
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        s.lat_val = ""; s.lon_val = ""; s.fup_opt = "No" 
        if 'gps_temp' in s: del s['gps_temp']
        
        st.toast("✅ Visita salvata!", icon="💾")
        st.rerun() 
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

def genera_excel_backup():
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Database_Completo')
    return output.getvalue()

def ripristina_database(file_excel):
    try:
        df_new = pd.read_excel(file_excel)
        colonne_necessarie = ['cliente', 'localita', 'provincia', 'tipo_cliente', 'note', 'agente']
        if not all(col in df_new.columns for col in colonne_necessarie):
            st.error("❌ Il file non sembra un backup valido del CRM Michelone.")
            return

        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        c.execute("DELETE FROM visite")
        c.execute("DELETE FROM sqlite_sequence WHERE name='visite'") 
        
        for _, row in df_new.iterrows():
            d_fup = row['data_followup'] if pd.notna(row['data_followup']) else ""
            lat = row['latitudine'] if pd.notna(row['latitudine']) else ""
            lon = row['longitudine'] if pd.notna(row['longitudine']) else ""
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (row['cliente'], row['localita'], row['provincia'], row['tipo_cliente'], 
                       row['data'], row['note'], d_fup, row['data_ordine'], 
                       row['agente'], lat, lon))
        
        conn.commit()
        conn.close()
        st.success("✅ Database ripristinato con successo! Ricarica la pagina.")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"Errore durante il ripristino: {e}")

# --- 3. INTERFACCIA UTENTE ---

st.title("💼 CRM Michelone")

# --- MODULO INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    st.markdown("---")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat = loc_data['coords']['latitude']
                lon = loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_Michelone_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', a.get('state', ''))
                prov_sigla = "RM" if prov_full and ("Roma" in prov_full or "Rome" in prov_full) else (prov_full[:2].upper() if prov_full else "??")
                st.session_state['gps_temp'] = {'citta': citta.upper() if citta else "", 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except Exception as e: st.warning(f"Errore: {e}")
        else: st.warning("⚠️ Consenti la geolocalizzazione.")

    if 'gps_temp' in st.session_state:
        dati = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: **{dati['citta']} ({dati['prov']})**")
        c_yes, c_no = st.columns(2)
        with c_yes: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
        with c_no: 
            if st.button("❌ ANNULLA", use_container_width=True): del st.session_state['gps_temp']; st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE ---
conn = sqlite3.connect('crm_mobile.db')
oggi = datetime.now().strftime("%Y-%m-%d")
df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)
conn.close()

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
        msg_ritardo = "Scaduto"
        try:
            giorni_ritardo = (datetime.strptime(oggi, "%Y-%m-%d") - datetime.strptime(row['data_followup'], "%Y-%m-%d")).days
            msg_ritardo = "Scaduto OGGI" if giorni_ritardo == 0 else f"Scaduto da {giorni_ritardo} gg"
        except: pass
        with st.container():
            col_txt, col_btn = st.columns([4, 1])
            with col_txt:
                st.markdown(f"**{icon} {row['cliente']}** - {row['localita']}")
                st.caption(f"📅 **{msg_ritardo}** | Note: {row['note']}")
            with col_btn:
                if st.button("✅", key=f"fatto_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db')
                    c = conn.cursor()
                    c.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.rerun()
    st.divider()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")

if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca (Cliente/Città)...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 CERCA VISITE", use_container_width=True): st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    conn.close()
    if t_ricerca: df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]
    if f_agente not in ["Tutti", "Seleziona..."]: df = df[df['agente'] == f_agente]

    st.markdown("---")
    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        output_filter = BytesIO()
        with pd.ExcelWriter(output_filter, engine='xlsxwriter') as writer: df.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        st.download_button("📊 SCARICA RICERCA (Excel)", output_filter.getvalue(), "ricerca_filtrata.xlsx", use_container_width=True)
        
        for _, row in df.iterrows():
            icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            with st.expander(f"{icon} {row['agente']} | {row['data']} - {row['cliente']}"):
                st.write(f"**📍 Città:** {row['localita']} ({row['provincia']})")
                st.write(f"**📝 Note:** {row['note']}")
                if row['latitudine']: st.markdown(f"[📍 Mappa](https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']})")
                col_del_btn, col_del_confirm = st.columns([1, 4])
                if st.button("🗑️ Elimina", key=f"pre_del_{row['id']}"): st.session_state[f"confirm_del_{row['id']}"] = True
                if st.session_state.get(f"confirm_del_{row['id']}", False):
                    st.error("⚠️ Confermi eliminazione?")
                    c_yes, c_no = st.columns(2)
                    with c_yes:
                        if st.button("SÌ", key=f"yes_del_{row['id']}", use_container_width=True):
                            conn = sqlite3.connect('crm_mobile.db'); c = conn.cursor()
                            c.execute("DELETE FROM visite WHERE id = ?", (row['id'],)); conn.commit(); conn.close()
                            del st.session_state[f"confirm_del_{row['id']}"]; st.rerun()
                    with c_no:
                        if st.button("NO", key=f"no_del_{row['id']}", use_container_width=True): st.session_state[f"confirm_del_{row['id']}"] = False; st.rerun()
    else: st.warning("Nessuna visita trovata.")
else: st.info("👆 Premi 'CERCA VISITE' per vedere l'archivio.")

# --- AREA GESTIONE DATI (NUOVA POSIZIONE) ---
st.write(""); st.write("")
st.subheader("🛠️ Gestione Dati")
with st.expander("💾 BACKUP E RIPRISTINO", expanded=False):
    st.write("### 1. Salva i tuoi dati (Backup)")
    st.caption("Scarica una copia di sicurezza di tutto il CRM.")
    data_backup = genera_excel_backup()
    st.download_button("📦 SCARICA BACKUP COMPLETO", data_backup, f"Backup_CRM_Michelone_{datetime.now().strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    
    st.markdown("---")
    
    st.write("### 2. Ripristina i dati (Restore)")
    st.error("⚠️ ATTENZIONE: Caricando un file qui sotto, CANCELLERAI tutti i dati attuali e li sostituirai con quelli del backup.")
    file_restore = st.file_uploader("Carica il file Excel di Backup", type=["xlsx"])
    
    if file_restore is not None:
        st.warning("Sei sicuro? I dati attuali andranno persi.")
        if st.button("🚨 SOVRASCRIVI E RIPRISTINA", use_container_width=True):
            ripristina_database(file_restore)

# --- LOGO/FIRMA ---
st.write(""); st.write("") 
col_spazio, col_logo = st.columns([3, 1])
with col_logo:
    if os.path.exists("logo.jpg"): st.image("logo.jpg", use_container_width=True)
    else: st.caption("Firma mancante")
