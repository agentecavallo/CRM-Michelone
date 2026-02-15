import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. FUNZIONI DEL DATABASE ---
def inizializza_db():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS visite 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cliente TEXT, 
                  data TEXT, 
                  note TEXT,
                  data_followup TEXT,
                  data_ordine TEXT,
                  agente TEXT)''')
    try:
        c.execute("ALTER TABLE visite ADD COLUMN data_followup TEXT")
    except: pass
    try:
        c.execute("ALTER TABLE visite ADD COLUMN data_ordine TEXT")
    except: pass
    try:
        c.execute("ALTER TABLE visite ADD COLUMN agente TEXT")
    except: pass
    conn.commit()
    conn.close()

def salva_visita(cliente, data_visita, nota, data_fup, data_ordine, agente):
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute("INSERT INTO visite (cliente, data, note, data_followup, data_ordine, agente) VALUES (?, ?, ?, ?, ?, ?)", 
              (cliente, data_visita, nota, data_fup, data_ordine, agente))
    conn.commit()
    conn.close()

def carica_visite(filtro_testo="", data_inizio=None, data_fine=None, filtro_agente="Tutti", solo_followup=False):
    conn = sqlite3.connect('crm_mobile.db')
    query = "SELECT cliente, data as 'Data Visita', note as 'Note', agente as 'Agente', data_ordine, data_followup, id FROM visite WHERE 1=1"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if solo_followup:
        oggi = datetime.now().strftime("%Y-%m-%d")
        df = df[df['data_followup'] != ""]
        df = df[df['data_followup'] <= oggi]
    
    if filtro_testo.strip():
        df = df[df['cliente'].str.contains(filtro_testo, case=False) | df['Note'].str.contains(filtro_testo, case=False)]
    if data_inizio and data_fine:
        df = df[(df['data_ordine'] >= data_inizio.strftime("%Y-%m-%d")) & (df['data_ordine'] <= data_fine.strftime("%Y-%m-%d"))]
    if filtro_agente != "Tutti":
        df = df[df['Agente'] == filtro_agente]
    
    return df.sort_values(by='data_ordine', ascending=False)

# --- 2. GESTIONE AZIONI ---
def gestisci_salvataggio():
    if st.session_state.cliente_key and st.session_state.note_key:
        data_f = st.session_state.data_key.strftime("%d/%m/%Y")
        data_ordine = st.session_state.data_key.strftime("%Y-%m-%d")
        # Se checkbox attivo, imposta followup a 7 giorni da oggi
        data_fup_db = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if st.session_state.reminder_key else ""
        
        salva_visita(st.session_state.cliente_key, data_f, st.session_state.note_key, data_fup_db, data_ordine, st.session_state.agente_key)
        
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.reminder_key = False
        st.toast("✅ Visita salvata!")
    else:
        st.error("⚠️ Compila i campi obbligatori!")

def risolvi_followup(id_visita):
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (id_visita,))
    conn.commit()
    conn.close()
    st.rerun()

# --- 3. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

LISTA_AGENTI = ["HSE", "BIENNE", "PALAGI", "SARDEGNA"]

st.title("💼 CRM Visite Agenti")

# Inserimento Nuova Visita
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", LISTA_AGENTI, key="agente_key")
    st.text_area("Note", key="note_key")
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=gestisci_salvataggio, use_container_width=True)

st.divider()

# --- SEZIONE FOLLOW-UP AUTOMATICA ---
df_fu = carica_visite(solo_followup=True)
if not df_fu.empty:
    st.subheader("📅 DA RICONTATTARE (FOLLOW-UP)")
    for _, row in df_fu.iterrows():
        with st.warning(f"📞 {row['cliente']} ({row['Agente']})"):
            st.write(f"**Nota originale:** {row['Note']}")
            st.write(f"**Data visita:** {row['Data Visita']}")
            if st.button(f"✅ Segna come fatto", key=f"fu_{row['id']}"):
                risolvi_followup(row['id'])
    st.divider()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Ricerca nell'Archivio")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca cliente o parola...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=30), datetime.now()])
with f3: f_agente = st.selectbox("Filtra Agente", ["Tutti"] + LISTA_AGENTI)

# Mostra risultati solo se c'è una ricerca attiva
if t_ricerca.strip() != "" or f_agente != "Tutti":
    d_ini, d_fin = (periodo[0], periodo[1]) if isinstance(periodo, list) and len(periodo) == 2 else (None, None)
    df_visite = carica_visite(t_ricerca, d_ini, d_fin, f_agente)
    
    if not df_visite.empty:
        # Export Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_visite.drop(columns=['data_ordine', 'id', 'data_followup']).to_excel(writer, index=False, sheet_name='Visite')
        
        st.download_button(label="📊 SCARICA EXCEL", data=output.getvalue(), file_name="export_crm.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        for _, row in df_visite.iterrows():
            with st.expander(f"👤 {row['Agente']} | {row['Data Visita']} - {row['cliente']}"):
                st.write(f"**Note:** {row['Note']}")
                if st.button(f"🗑️ Elimina", key=f"del_{row['id']}"):
                    conn = sqlite3.connect('crm_mobile.db')
                    c = conn.cursor()
                    c.execute("DELETE FROM visite WHERE id = ?", (int(row['id']),))
                    conn.commit()
                    conn.close()
                    st.rerun()
    else:
        st.info("Nessun risultato trovato.")

# Footer Logo
st.write("")
st.divider()
cf1, cf2 = st.columns([5, 1])
with cf2:
    try: st.image("logo.jpeg", use_container_width=True)
    except: pass