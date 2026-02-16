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

# Inizializzazione variabili di stato per evitare errori
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None

# --- 2. LOGICA DI SALVATAGGIO ---
def salva_dati(dati_form):
    """Salva i dati nel DB senza toccare direttamente lo session_state dei widget"""
    if dati_form['cliente'] and dati_form['note']:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (dati_form['cliente'], dati_form['localita'].upper(), dati_form['prov'].upper(), 
                       dati_form['tipo'], dati_form['data_visita'], dati_form['note'], 
                       dati_form['data_fup'], dati_form['data_ord'], dati_form['agente'], 
                       dati_form['lat'], dati_form['lon']))
            conn.commit()
        return True
    return False

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    # Usiamo un form per evitare crash di session_state
    with st.form("form_visita", clear_on_submit=True):
        cliente = st.text_input("Nome Cliente")
        tipo = st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], horizontal=True)
        
        col_l, col_p = st.columns([3, 1])
        localita = col_l.text_input("Località")
        provincia = col_p.text_input("Prov.", max_chars=2)
        
        c1, c2 = st.columns(2)
        data_sel = c1.date_input("Data Visita", datetime.now())
        agente = c2.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"])
        
        note = st.text_area("Note Visita")
        fup = st.radio("Pianifica Ricontatto", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], horizontal=True)
        
        submit = st.form_submit_button("💾 SALVA VISITA", use_container_width=True)
        
        if submit:
            # Calcolo date
            data_visita_str = data_sel.strftime("%d/%m/%Y")
            data_ord_str = data_sel.strftime("%Y-%m-%d")
            data_fup_str = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
            if fup != "No":
                data_fup_str = (data_sel + timedelta(days=giorni[fup])).strftime("%Y-%m-%d")
            
            successo = salva_dati({
                'cliente': cliente, 'localita': localita, 'prov': provincia,
                'tipo': tipo, 'data_visita': data_visita_str, 'note': note,
                'data_fup': data_fup_str, 'data_ord': data_ord_str, 'agente': agente,
                'lat': "", 'lon': ""
            })
            
            if successo:
                st.balloons()
                st.success("Visita registrata! L'ID verrà assegnato automaticamente.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("⚠️ Inserisci almeno Cliente e Note!")

st.divider()

# --- 4. ARCHIVIO E VISUALIZZAZIONE ID ---
st.subheader("🔍 Archivio Visite")
if st.button("🔎 MOSTRA/AGGIORNA ARCHIVIO", use_container_width=True):
    st.session_state.ricerca_attiva = True

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        # Recuperiamo i dati assicurandoci che l'ID sia un intero
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    
    if not df.empty:
        for _, row in df.iterrows():
            # Pulizia ID: se è NaN mettiamo "Nuovo", altrimenti numero intero
            id_pulito = int(row['id']) if pd.notnull(row['id']) else "N.D."
            
            with st.expander(f"🆔 ID: {id_pulito} | {row['data']} - {row['cliente']}"):
                st.write(f"**Località:** {row['localita']} ({row['provincia']}) | **Agente:** {row['agente']}")
                st.info(f"**Note:** {row['note']}")
                if st.button("🗑️ Elimina", key=f"del_{row['id']}"):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("DELETE FROM visite WHERE id=?", (row['id'],))
                    st.rerun()
    else:
        st.warning("Nessuna visita in archivio.")

# --- 5. RESET TOTALE (PER PULIRE I "NAN") ---
with st.expander("🛠️ ZONA PERICOLOSA"):
    st.warning("Se vedi ancora degli ID 'nan', usa questo tasto per resettare il database e ripartire pulito.")
    if st.button("🔥 RESET TOTALE DATABASE"):
        with sqlite3.connect('crm_mobile.db') as conn:
            conn.execute("DROP TABLE IF EXISTS visite")
        st.success("Database eliminato! Ricarica la pagina.")
        time.sleep(1)
        st.rerun()
