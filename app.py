import streamlit as st
import sqlite3
from datetime import datetime, timedelta

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

def carica_visite(filtro_testo="", data_inizio=None, data_fine=None, filtro_agente="Tutti"):
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    query = "SELECT cliente, data, note, id, agente FROM visite WHERE 1=1"
    params = []
    
    if filtro_testo.strip():
        query += " AND (cliente LIKE ? OR note LIKE ?)"
        params.extend([f"%{filtro_testo}%", f"%{filtro_testo}%"])
    
    if data_inizio and data_fine:
        query += " AND data_ordine BETWEEN ? AND ?"
        params.extend([data_inizio.strftime("%Y-%m-%d"), data_fine.strftime("%Y-%m-%d")])
    
    if filtro_agente != "Tutti":
        query += " AND agente = ?"
        params.append(filtro_agente)
        
    query += " ORDER BY data_ordine DESC, id DESC"
    c.execute(query, params)
    dati = c.fetchall()
    conn.close()
    return dati

def carica_scadenze_oggi():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    oggi = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT cliente, data_followup, agente FROM visite WHERE data_followup <= ? AND data_followup != ''", (oggi,))
    dati = c.fetchall()
    conn.close()
    return dati

# --- 2. GESTIONE SALVATAGGIO E PULIZIA ---
def gestisci_salvataggio():
    cliente = st.session_state.cliente_key
    note = st.session_state.note_key
    agente = st.session_state.agente_key
    data_sel = st.session_state.data_key
    reminder = st.session_state.reminder_key

    if cliente and note:
        data_f = data_sel.strftime("%d/%m/%Y")
        data_ordine = data_sel.strftime("%Y-%m-%d")
        data_fup_db = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if reminder else ""
        
        salva_visita(cliente, data_f, note, data_fup_db, data_ordine, agente)
        
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.reminder_key = False
        st.toast(f"✅ Visita salvata per {agente}!")
    else:
        st.error("⚠️ Inserisci Nome Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

LISTA_AGENTI = ["HSE", "BIENNE", "PALAGI", "SARDEGNA"]

# Titolo pulito in alto
st.title("💼 CRM Visite Agenti")

# Sezione Scadenze
scadenze = carica_scadenze_oggi()
if scadenze:
    with st.container():
        st.error("🔔 FOLLOW-UP DA FARE OGGI:")
        for s in scadenze:
            st.write(f"📞 **{s[0]}** (Agente: {s[2]})")
    st.divider()

# Inserimento Nuova Visita
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente / Azienda", key="cliente_key")
    
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Data visita", datetime.now(), key="data_key")
    with c2:
        st.selectbox("Seleziona Agente", LISTA_AGENTI, key="agente_key")
    
    st.text_area("Note del colloquio", key="note_key")
    st.checkbox("Pianifica Follow-up tra 7gg", key="reminder_key")
    
    st.button("💾 SALVA E PULISCI", on_click=gestisci_salvataggio, use_container_width=True)

st.divider()

# Ricerca e Filtri
st.subheader("🔍 Filtra Archivio")
f1, f2, f3 = st.columns([1.5, 1, 1])

with f1:
    testo_ricerca = st.text_input("Cerca nome o parola...")
with f2:
    periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=30), datetime.now()])
with f3:
    filtro_agente_sel = st.selectbox("Filtra Agente", ["Tutti"] + LISTA_AGENTI)

d_inizio, d_fine = None, None
if isinstance(periodo, list) and len(periodo) == 2:
    d_inizio, d_fine = periodo

elenco_visite = carica_visite(testo_ricerca, d_inizio, d_fine, filtro_agente_sel)

if not elenco_visite:
    st.info("Nessuna visita trovata.")
else:
    st.caption(f"Visite trovate: {len(elenco_visite)}")
    for v in elenco_visite:
        with st.expander(f"👤 {v[4]} | {v[1]} - {v[0]}"):
            st.write(f"**Note:** {v[2]}")
            if st.button(f"🗑️ Elimina", key=f"del_{v[3]}"):
                conn = sqlite3.connect('crm_mobile.db')
                c = conn.cursor()
                c.execute("DELETE FROM visite WHERE id = ?", (v[3],))
                conn.commit()
                conn.close()
                st.rerun()

# --- LOGO IN BASSO A DESTRA (Footer) ---
st.write("") 
st.divider()

# Creiamo due colonne: la prima (vuota) occupa l'85% dello spazio, la seconda il 15%
col_spazio, col_logo_final = st.columns([5, 1])

with col_logo_final:
    try:
        st.image("logo.jpeg", use_container_width=True)
    except:
        pass