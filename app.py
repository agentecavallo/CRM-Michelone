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
                  localita TEXT,
                  provincia TEXT,
                  tipo_cliente TEXT,
                  data TEXT, 
                  note TEXT,
                  data_followup TEXT,
                  data_ordine TEXT,
                  agente TEXT)''')
    
    # Aggiornamenti colonne per versioni precedenti
    try: c.execute("ALTER TABLE visite ADD COLUMN localita TEXT")
    except: pass
    try: c.execute("ALTER TABLE visite ADD COLUMN provincia TEXT")
    except: pass
    try: c.execute("ALTER TABLE visite ADD COLUMN tipo_cliente TEXT")
    except: pass
    try: c.execute("ALTER TABLE visite ADD COLUMN data_followup TEXT")
    except: pass
    try: c.execute("ALTER TABLE visite ADD COLUMN data_ordine TEXT")
    except: pass
    try: c.execute("ALTER TABLE visite ADD COLUMN agente TEXT")
    except: pass
    
    conn.commit()
    conn.close()

def salva_visita():
    cliente = st.session_state.cliente_key
    localita = st.session_state.localita_key.upper()
    provincia = st.session_state.prov_key.upper()
    tipo = st.session_state.tipo_key
    note = st.session_state.note_key
    agente = st.session_state.agente_key
    data_sel = st.session_state.data_key
    reminder = st.session_state.reminder_key

    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        data_f = data_sel.strftime("%d/%m/%Y")
        data_ordine = data_sel.strftime("%Y-%m-%d")
        data_fup_db = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d") if reminder else ""
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, data_followup, data_ordine, agente) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, localita, provincia, tipo, data_f, note, data_fup_db, data_ordine, agente))
        conn.commit()
        conn.close()
        
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.session_state.reminder_key = False
        st.toast("✅ Visita salvata!")
    else:
        st.error("⚠️ Inserisci Cliente e Note!")

def carica_visite(filtro_testo="", data_inizio=None, data_fine=None, filtro_agente="Seleziona...", solo_followup=False):
    conn = sqlite3.connect('crm_mobile.db')
    query = "SELECT cliente, localita, provincia, tipo_cliente, data as 'Data Visita', note as 'Note', agente as 'Agente', data_ordine, data_followup, id FROM visite WHERE 1=1"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    df['localita'] = df['localita'].fillna("-")
    df['provincia'] = df['provincia'].fillna("-")
    df['tipo_cliente'] = df['tipo_cliente'].fillna("Cliente")

    if solo_followup:
        oggi = datetime.now().strftime("%Y-%m-%d")
        df = df[(df['data_followup'] != "") & (df['data_followup'] <= oggi)]
        return df
    
    if filtro_testo.strip():
        df = df[
            df['cliente'].str.contains(filtro_testo, case=False) | 
            df['Note'].str.contains(filtro_testo, case=False) |
            df['localita'].str.contains(filtro_testo, case=False) |
            df['provincia'].str.contains(filtro_testo, case=False)
        ]
    
    if data_inizio and data_fine:
        df = df[(df['data_ordine'] >= data_inizio.strftime("%Y-%m-%d")) & (df['data_ordine'] <= data_fine.strftime("%Y-%m-%d"))]
    
    if filtro_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['Agente'] == filtro_agente]
    
    return df.sort_values(by='data_ordine', ascending=False)

def elimina_visita(id_visita):
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute("DELETE FROM visite WHERE id = ?", (int(id_visita),))
    conn.commit()
    conn.close()
    st.rerun()

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Agenti", page_icon="💼", layout="centered")
inizializza_db()

LISTA_AGENTI = ["HSE", "BIENNE", "PALAGI", "SARDEGNA"]

st.title("💼 CRM Visite Agenti")

# Inserimento
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    st.text_input("Nome Cliente", key="cliente_key")
    
    # Campo Tipo Cliente (Punto 4)
    st.radio("Stato Cliente", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.text_input("Località", key="localita_key")
    st.text_input("Provincia", key="prov_key", max_chars=2)
    
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", LISTA_AGENTI, key="agente_key")
    
    st.text_area("Note", key="note_key", height=200)
    st.checkbox("Pianifica Follow-up (7gg)", key="reminder_key")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# Follow-up
df_fu = carica_visite(solo_followup=True)
if not df_fu.empty:
    st.subheader("📅 DA RICONTATTARE")
    for _, row in df_fu.iterrows():
        icona = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
        with st.warning(f"{icona} {row['cliente']} - {row['localita']} ({row['provincia']})"):
            st.write(f"**Nota:** {row['Note']}")
            if st.button(f"✅ Fatto", key=f"fu_{row['id']}"): 
                conn = sqlite3.connect('crm_mobile.db')
                c = conn.cursor()
                c.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()
    st.divider()

# Archivio
st.subheader("🔍 Ricerca nell'Archivio")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca nome, nota, città o prov...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Visualizza Agente", ["Seleziona...", "Tutti"] + LISTA_AGENTI)

if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    d_ini, d_fin = (periodo[0], periodo[1]) if isinstance(periodo, list) and len(periodo) == 2 else (None, None)
    df_visite = carica_visite(t_ricerca, d_ini, d_fin, f_agente)
    
    if not df_visite.empty:
        output = BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_visite.drop(columns=['data_ordine', 'id', 'data_followup']).to_excel(writer, index=False, sheet_name='Visite')
            st.download_button(label="📊 SCARICA EXCEL", data=output.getvalue(), file_name="export_crm.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except: st.error("Errore Excel")

        for _, row in df_visite.iterrows():
            icona = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            titolo = f"{icona} {row['Agente']} | {row['Data Visita']} - {row['cliente']} ({row['localita']})"
            with st.expander(titolo):
                st.write(f"**Stato:** {row['tipo_cliente']}")
                st.write(f"**Note:** {row['Note']}")
                
                if st.button(f"🗑️ Elimina", key=f"pre_del_{row['id']}"):
                    st.session_state[f"confirm_{row['id']}"] = True
                if st.session_state.get(f"confirm_{row['id']}", False):
                    st.error("Confermi eliminazione?")
                    c_del, c_ann = st.columns(2)
                    with c_del: st.button("SI", key=f"real_del_{row['id']}", on_click=elimina_visita, args=(row['id'],), use_container_width=True)
                    with c_ann: 
                        if st.button("NO", key=f"cancel_{row['id']}", use_container_width=True):
                            st.session_state[f"confirm_{row['id']}"] = False
                            st.rerun()
    else: st.info("Nessun risultato.")
else: st.caption("Seleziona un agente o scrivi un nome/città per consultare l'archivio.")

# Footer
st.write("")
st.divider()
cf1, cf2 = st.columns([5, 1])
with cf2:
    try: st.image("logo.jpeg", use_container_width=True)
    except: pass