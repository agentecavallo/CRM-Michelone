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

inizializza_db()

# --- 2. FUNZIONI DI SUPPORTO ---

def elimina_visita_db(id_visita):
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute("DELETE FROM visite WHERE id=?", (id_visita,))
    conn.commit()
    conn.close()

def salva_visita_db(dati, id_visita=None):
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    if id_visita:
        c.execute("""UPDATE visite SET cliente=?, localita=?, provincia=?, tipo_cliente=?, 
                     data=?, note=?, data_followup=?, data_ordine=?, agente=? 
                     WHERE id=?""", (*dati, id_visita))
    else:
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", dati)
    conn.commit()
    conn.close()

def genera_excel_backup():
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Database_Completo')
    return output.getvalue()

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

# --- SEZIONE INSERIMENTO / MODIFICA ---
titolo_form = "✏️ MODIFICA VISITA" if st.session_state.editing_id else "➕ REGISTRA NUOVA VISITA"
with st.expander(titolo_form, expanded=st.session_state.editing_id is not None):
    val_cliente = ""; val_note = ""; val_loc = ""; val_prov = ""; val_agente = "HSE"
    
    if st.session_state.editing_id:
        conn = sqlite3.connect('crm_mobile.db')
        curr = conn.execute("SELECT * FROM visite WHERE id=?", (st.session_state.editing_id,)).fetchone()
        conn.close()
        if curr:
            val_cliente = curr[1]; val_loc = curr[2]; val_prov = curr[3]; val_note = curr[6]; val_agente = curr[9]

    c_nome = st.text_input("Nome Cliente", value=val_cliente, key="in_cliente")
    c_tipo = st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], horizontal=True, key="in_tipo")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: c_loc = st.text_input("Località", value=val_loc, key="in_localita")
    with col_p: c_prov = st.text_input("Prov.", value=val_prov, max_chars=2, key="in_prov")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: c_data = st.date_input("Data", datetime.now(), key="in_data")
    with c2: c_agente = st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], index=0)
    
    c_note = st.text_area("Note", value=val_note, height=100, key="in_note")
    st.write("📅 **Ricontatto:**")
    c_fup = st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], horizontal=True, key="in_fup")

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("💾 SALVA", use_container_width=True):
            data_fup = ""
            mappa = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
            if c_fup in mappa: data_fup = (c_data + timedelta(days=mappa[c_fup])).strftime("%Y-%m-%d")
            dati_tuple = (c_nome, c_loc.upper(), c_prov.upper(), c_tipo, c_data.strftime("%d/%m/%Y"), c_note, data_fup, c_data.strftime("%Y-%m-%d"), c_agente)
            if st.session_state.editing_id:
                salva_vis_ita_db(dati_tuple, st.session_state.editing_id)
                st.session_state.editing_id = None
            else:
                salva_visita_db((*dati_tuple, "", ""), None)
            st.rerun()
    with col_cancel:
        if st.session_state.editing_id and st.button("❌ ANNULLA", use_container_width=True):
            st.session_state.editing_id = None
            st.rerun()

st.divider()

# --- 4. ALERT SCADENZE ---
conn = sqlite3.connect('crm_mobile.db')
oggi = datetime.now().strftime("%Y-%m-%d")
df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}'", conn)
conn.close()

if not df_scadenze.empty:
    st.error(f"⚠️ **DA RICONTATTARE: {len(df_scadenze)}**")
    for _, row in df_scadenze.iterrows():
        col_t, col_b = st.columns([4, 1])
        col_t.write(f"**{row['cliente']}** - {row['localita']}")
        if col_b.button("✅", key=f"fup_{row['id']}"):
            conn = sqlite3.connect('crm_mobile.db'); conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],)); conn.commit(); conn.close()
            st.rerun()

# --- 5. ARCHIVIO E RICERCA ---
st.subheader("🔍 Archivio Visite")
t_ricerca = st.text_input("Cerca Cliente...")

if t_ricerca or st.button("MOSTRA TUTTE"):
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query(f"SELECT * FROM visite WHERE cliente LIKE '%{t_ricerca}%' ORDER BY data_ordine DESC", conn)
    conn.close()

    for _, row in df.iterrows():
        with st.expander(f"{row['data']} - {row['cliente']} ({row['agente']})"):
            st.write(f"**Località:** {row['localita']} ({row['provincia']})")
            st.write(f"**Note:** {row['note']}")
            
            # --- PULSANTI AZIONE ---
            c_mod, c_del = st.columns(2)
            
            if c_mod.button("✏️ Modifica", key=f"edit_{row['id']}", use_container_width=True):
                st.session_state.editing_id = row['id']
                st.rerun()
            
            # NUOVO PULSANTE CANCELLA
            if c_del.button("🗑️ Elimina", key=f"del_{row['id']}", use_container_width=True):
                elimina_visita_db(row['id'])
                st.toast(f"Visita di {row['cliente']} eliminata!")
                time.sleep(1)
                st.rerun()

# --- 6. GESTIONE DATI ---
st.subheader("🛠️ Gestione Dati")
st.download_button("📦 BACKUP EXCEL", genera_excel_backup(), f"Backup_CRM.xlsx", use_container_width=True)
