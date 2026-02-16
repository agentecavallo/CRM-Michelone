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
        conn.commit()

inizializza_db()

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
            except:
                pass 

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
            
            # --- LOGICA RICONTATTO ---
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            
            giorni_da_aggiungere = 0
            if scelta == "1 gg":
                giorni_da_aggiungere = 1
            elif scelta == "7 gg":
                giorni_da_aggiungere = 7
            elif scelta == "15 gg":
                giorni_da_aggiungere = 15
            elif scelta == "30 gg":
                giorni_da_aggiungere = 30
            
            if giorni_da_aggiungere > 0:
                data_fup = (s.data_key + timedelta(days=giorni_da_aggiungere)).strftime("%Y-%m-%d")
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, 
                       s.lat_val, s.lon_val))
            conn.commit()
        
        # Reset campi
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.session_state.lat_val = ""
        st.session_state.lon_val = ""
        st.session_state.fup_opt = "No"
        
        st.toast("✅ Visita salvata!", icon="💾")
        time.sleep(1)
        st.rerun()
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

# --- MODULO VISITA (CHIUSO DI DEFAULT) ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    # GPS
    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_Michelone_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                
                # --- FIX PROVINCIA ROMA ---
                prov_full = a.get('county', '')
                if prov_full and ("Roma" in prov_full or "Rome" in prov_full):
                    prov_sigla = "RM"
                else:
                    prov_sigla = prov_full[:2].upper() if prov_full else "??"
                
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
                del st.session_state['gps_temp']
                st.rerun()

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
            d_oggi = datetime.strptime(oggi, "%Y-%m-%d")
            giorni_ritardo = (d_oggi - d_scad).days
            msg_scadenza = "Scade OGGI" if giorni_ritardo == 0 else f"Scaduto da {giorni_ritardo} gg"
        except:
            msg_scadenza = "Scaduto"

        with st.container(border=True):
            st.markdown(f"**{row['cliente']}** - {row['localita']}")
            st.caption(f"📅 {msg_scadenza} | Note: {row['note']}")
            st.write("") 
            
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if st.button("+1 ☀️", key=f"p1_{row['id']}", help="Domani", use_container_width=True):
                    nuova_data = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova_data, row['id']))
                    st.rerun()
            with c2:
                if st.button("+7 📅", key=f"p7_{row['id']}", help="Settimana prox", use_container_width=True):
                    nuova_data = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova_data, row['id']))
                    st.rerun()
            with c3:
                if st.button("✅ Fatto", key=f"ok_{row['id']}", type="primary", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    st.rerun()

# --- RICERCA E ARCHIVIO (CON MODIFICA AGENTE) ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
periodo = f2.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
f_agente = f3.selectbox("Filtra Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 CERCA VISITE", use_container_width=True):
    st.session_state.ricerca_attiva = True
    st.session_state.edit_mode_id = None 

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
         df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

    st.markdown("---")
    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        if st.button("❌ Chiudi Ricerca"):
            st.session_state.ricerca_attiva = False
            st.session_state.edit_mode_id = None
            st.rerun()

        for _, row in df.iterrows():
            with st.expander(f"{row['data']} - {row['cliente']} ({row['agente']})"):
                
                # --- MODALITÀ MODIFICA ---
                if st.session_state.edit_mode_id == row['id']:
                    st.info("✏️ Modifica Dati")
                    
                    # 1. Cliente e Agente
                    c_edit_1, c_edit_2 = st.columns([2, 1])
                    with c_edit_1:
                        new_cliente = st.text_input("Cliente", value=row['cliente'], key=f"e_cli_{row['id']}")
                    with c_edit_2:
                        lista_agenti = ["HSE", "BIENNE", "PALAGI", "SARDEGNA"]
                        # Trova l'indice dell'agente attuale per impostare il default
                        try:
                            idx_ag = lista_agenti.index(row['agente'])
                        except:
                            idx_ag = 0
                        new_agente = st.selectbox("Agente", lista_agenti, index=idx_ag, key=f"e_ag_{row['id']}")

                    # 2. Località e Provincia
                    c_edit_3, c_edit_4 = st.columns([3, 1])
                    with c_edit_3:
                        new_loc = st.text_input("Località", value=row['localita'], key=f"e_loc_{row['id']}")
                    with c_edit_4:
                        new_prov = st.text_input("Prov.", value=row['provincia'], max_chars=2, key=f"e_prov_{row['id']}")
                    
                    # 3. Note
                    new_note = st.text_area("Note", value=row['note'], height=100, key=f"e_note_{row['id']}")
                    
                    # Pulsanti Salva / Annulla
                    c_save, c_canc = st.columns(2)
                    if c_save.button("💾 SALVA", key=f"save_{row['id']}", type="primary", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            # QUERY AGGIORNATA CON AGENTE
                            conn.execute("""UPDATE visite SET cliente=?, localita=?, provincia=?, note=?, agente=? WHERE id=?""",
                                         (new_cliente, new_loc.upper(), new_prov.upper(), new_note, new_agente, row['id']))
                        st.session_state.edit_mode_id = None
                        st.toast("Modifica salvata!")
                        time.sleep(1)
                        st.rerun()
                    
                    if c_canc.button("❌ ANNULLA", key=f"canc_{row['id']}", use_container_width=True):
                        st.session_state.edit_mode_id = None
                        st.rerun()
                        
                else:
                    # --- MODALITÀ VISUALIZZAZIONE ---
                    st.write(f"**Località:** {row['localita']} ({row['provincia']})")
                    st.write(f"**Note:** {row['note']}")
                    if row['latitudine'] and row['longitudine']:
                        st.markdown(f"[📍 Mappa](http://googleusercontent.com/maps.google.com/maps?q={row['latitudine']},{row['longitudine']})")
                    
                    col_btn_mod, col_btn_del = st.columns([1, 1])
                    
                    if col_btn_mod.button("✏️ Modifica", key=f"btn_mod_{row['id']}"):
                        st.session_state.edit_mode_id = row['id']
                        st.rerun()
                    
                    key_confirm = f"confirm_del_{row['id']}"
                    if col_btn_del.button("🗑️ Elimina", key=f"btn_del_{row['id']}"):
                        st.session_state[key_confirm] = True
                        st.rerun()
                    
                    if st.session_state.get(key_confirm, False):
                        st.warning("⚠️ Sei sicuro?")
                        c_yes, c_no = st.columns(2)
                        if c_yes.button("SÌ", key=f"yes_{row['id']}", type="primary", use_container_width=True):
                            with sqlite3.connect('crm_mobile.db') as conn:
                                conn.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                            del st.session_state[key_confirm]
                            st.rerun()
                        
                        if c_no.button("NO", key=f"no_{row['id']}", use_container_width=True):
                            del st.session_state[key_confirm]
                            st.rerun()
    else:
        st.warning("Nessun risultato trovato.")

# --- GESTIONE DATI ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE E BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA DATABASE (EXCEL)", output.getvalue(), "backup_crm.xlsx", use_container_width=True)
