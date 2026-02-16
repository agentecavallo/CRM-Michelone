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

if 'lat_val' not in st.session_state: st.session_state.lat_val = ""
if 'lon_val' not in st.session_state: st.session_state.lon_val = ""
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None
if 'confirm_reset' not in st.session_state: st.session_state.confirm_reset = False

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

def salva_visita():
    """Funzione per salvare i dati nel database senza generare errori di rerun."""
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
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, 
                       s.lat_val, s.lon_val))
            conn.commit()
        
        # Reset dei campi nello stato della sessione
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.session_state.lat_val = ""
        st.session_state.lon_val = ""
        st.session_state.fup_opt = "No"
        st.toast("✅ Visita salvata con successo!", icon="💾")
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

def applica_dati_gps():
    if 'gps_temp' in st.session_state:
        dati = st.session_state['gps_temp']
        st.session_state.localita_key = dati['citta']
        st.session_state.prov_key = dati['prov']
        st.session_state.lat_val = dati['lat']
        st.session_state.lon_val = dati['lon']
        del st.session_state['gps_temp']

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    # GPS Logic
    loc_data = get_geolocation()
    if st.button("📍 USA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_Michelone_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', '')
                prov_sigla = "RM" if "Roma" in prov_full or "Rome" in prov_full else (prov_full[:2].upper() if prov_full else "??")
                st.session_state['gps_temp'] = {'citta': citta.upper(), 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Errore GPS.")
    
    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: **{d['citta']} ({d['prov']})**")
        if st.button("✅ CONFERMA POSIZIONE", on_click=applica_dati_gps): st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=100)
    st.radio("Pianifica Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True)
    
    # Bottone Salva - Rimosso on_click per evitare l'errore giallo di rerun
    if st.button("💾 SALVA VISITA", use_container_width=True, type="primary"):
        salva_visita()
        time.sleep(1)
        st.rerun()

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}'", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **DA RICONTATTARE: {len(df_scadenze)}**")
    for _, row in df_scadenze.iterrows():
        with st.container(border=True):
            st.write(f"**{row['cliente']}** ({row['localita']})")
            if st.button("✅ Fatto", key=f"ok_{row['id']}"):
                with sqlite3.connect('crm_mobile.db') as conn:
                    conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                st.rerun()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente")
f_agente = f3.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 AVVIA RICERCA", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]

    for _, row in df.iterrows():
        # FIX: ID pulito (senza .0) e gestione nan
        id_int = int(row['id']) if pd.notnull(row['id']) else "???"
        
        with st.expander(f"🆔 {id_int} | {row['data']} - {row['cliente']}"):
            if st.session_state.edit_mode_id == row['id']:
                # Modalità Modifica
                new_note = st.text_area("Modifica Note", value=row['note'], key=f"ed_{row['id']}")
                if st.button("💾 AGGIORNA", key=f"up_{row['id']}"):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET note=? WHERE id=?", (new_note, row['id']))
                    st.session_state.edit_mode_id = None
                    st.rerun()
            else:
                st.write(f"**Agente:** {row['agente']} | **Località:** {row['localita']}")
                st.write(f"**Note:** {row['note']}")
                c1, c2 = st.columns(2)
                if c1.button("✏️ Modifica", key=f"eb_{row['id']}"):
                    st.session_state.edit_mode_id = row['id']
                    st.rerun()
                if c2.button("🗑️ Elimina", key=f"db_{row['id']}"):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("DELETE FROM visite WHERE id=?", (row['id'],))
                    st.rerun()

# --- AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ GESTIONE DATI E RIPRISTINO"):
    # Ripristino migliorato
    file_caricato = st.file_uploader("Carica Excel di Backup", type=["xlsx"])
    if file_caricato and st.button("📥 IMPORTA DATI"):
        df_ripr = pd.read_excel(file_caricato)
        with sqlite3.connect('crm_mobile.db') as conn:
            conn.execute("DELETE FROM visite")
            # Assicuriamoci che l'ID non crei conflitti durante l'import
            df_ripr.to_sql('visite', conn, if_exists='append', index=False)
        st.success("Dati ripristinati correttamente!")
        time.sleep(1)
        st.rerun()

    if st.button("🗑️ RESET TOTALE DATABASE", type="secondary"):
        with sqlite3.connect('crm_mobile.db') as conn:
            conn.execute("DROP TABLE IF EXISTS visite")
        st.warning("Database eliminato. Ricarica la pagina per ricrearlo pulito.")
        st.rerun()
