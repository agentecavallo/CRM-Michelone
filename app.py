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

def carica_visite(filtro_testo="", data_inizio=None, data_fine=None, filtro_agente="Tutti"):
    conn = sqlite3.connect('crm_mobile.db')
    query = "SELECT cliente, data as 'Data Visita', note as 'Note', agente as 'Agente', data_ordine, id FROM visite WHERE 1=1"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if filtro_testo.strip():
        df = df[df['cliente'].str.contains(filtro_testo, case=False) | df['Note'].str.contains(filtro_testo, case=False)]
    if data_inizio and data_fine:
        df = df[(df['data_ordine'] >= data_inizio.strftime("%Y-%m-%d")) & (df['data_ordine'] <= data_fine.strftime("%Y-%m-%d"))]
    if filtro_agente != "Tutti":
        df = df[df['Agente'] == filtro_agente]
    
    return df.sort_values(by='data_ordine', ascending=False)

def carica_scadenze_oggi():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    oggi = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT cliente, data_followup, agente FROM visite WHERE data_followup <= ? AND data_followup != ''", (oggi,))
    dati = c.fetchall()
    conn.close()
    return dati

# --- 2. GESTIONE SALVATAGGIO ---
def gestisci_salvataggio():
    if st.session_state.cliente_key and st.session_state.note_key:
        data_f = st.session_state.data_key.strftime("%d/%m/%Y")
        data_ordine = st.session_state.data_key.strftime("%Y-%m-%d")
        data_fup_db = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if st.session_state.reminder_key else ""
        
        salva_visita(st.session_state.cliente_key, data_f, st.session_state.note_key, data_fup_db, data_ordine, st.session_state.agente_key)
        
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.reminder_key = False
        st.toast("✅ Visita salvata!")
    else:
        st.error("⚠️ Compila i campi obbligatori!")

# --- 3. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

LISTA_AGENTI = ["HSE", "BIENNE", "PALAGI", "SARDEGNA"]

st.title("💼 CRM Visite Agenti")

# Scadenze
scadenze = carica_scadenze_oggi()
if scadenze:
    with st.error("🔔 FOLLOW-UP DA FARE:"):
        for s in scadenze: st.write(f"📞 **{s[0]}** ({s[2]})")

# Inserimento
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", LISTA_AGENTI, key="agente_key")
    st.text_area("Note", key="note_key")
    st.checkbox("Follow-up tra 7gg", key="reminder_key")
    st.button("💾 SALVA", on_click=gestisci_salvataggio, use_container_width=True)

st.divider()

# Archivio e Filtri
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca cliente o nota...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=30), datetime.now()])
with f3: f_agente = st.selectbox("Filtra Agente", ["Tutti"] + LISTA_AGENTI)

d_ini, d_fin = (periodo[0], periodo[1]) if isinstance(periodo, list) and len(periodo) == 2 else (None, None)
df_visite = carica_visite(t_ricerca, d_ini, d_fin, f_agente)

# LOGICA MOSTRA/NASCONDI: Mostra solo se l'utente ha interagito con i filtri
if t_ricerca.strip() != "" or f_agente != "Tutti":
    if not df_visite.empty:
        # Tasto Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_visite.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        
        st.download_button(
            label="📊 SCARICA QUESTI RISULTATI (EXCEL)",
            data=output.getvalue(),
            file_name=f"export_crm_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        st.caption(f"Trovate {len(df_visite)} visite:")
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
        st.info("Nessuna visita corrispondente alla ricerca.")
else:
    st.info("👆 Usa la barra di ricerca o seleziona un agente per visualizzare lo storico.")

# Footer Logo
st.write("")
st.divider()
cf1, cf2 = st.columns([5, 1])
with cf2:
    try: st.image("logo.jpeg", use_container_width=True)
    except: pass