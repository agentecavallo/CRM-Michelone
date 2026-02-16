import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
import requests
from streamlit_js_eval import get_geolocation
import uuid

# --- 1. GESTIONE DATABASE LOCALE (CSV) ---
DB_FILE = "crm_visite.csv"

def carica_dati():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    else:
        # Crea le colonne se il file non esiste
        return pd.DataFrame(columns=["Data", "Agente", "Cliente", "Tipo", "Località", "Provincia", "Note", "FollowUp", "ID"])

def salva_visita():
    s = st.session_state
    if s.get('cliente_key', '').strip() != "" and s.get('note_key', '').strip() != "":
        df = carica_dati()
        
        data_oggi = s.data_key.strftime("%d/%m/%Y")
        scelta = s.get('fup_opt', 'No')
        data_fup = ""
        if scelta == "7 gg":
            data_fup = (s.data_key + timedelta(days=7)).strftime("%Y-%m-%d")
        elif scelta == "30 gg":
            data_fup = (s.data_key + timedelta(days=30)).strftime("%Y-%m-%d")

        nuova_riga = {
            "Data": data_oggi,
            "Agente": s.agente_key,
            "Cliente": s.cliente_key,
            "Tipo": s.tipo_key,
            "Località": s.localita_key.upper(),
            "Provincia": s.prov_key.upper(),
            "Note": s.note_key,
            "FollowUp": data_fup,
            "ID": str(uuid.uuid4())
        }
        
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        
        # Reset campi
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.toast("✅ Visita registrata con successo!")
        st.rerun()
    else:
        st.error("⚠️ Inserisci Nome Cliente e Note!")

def elimina_riga(id_da_eliminare):
    df = carica_dati()
    df = df[df['ID'].astype(str) != str(id_da_eliminare)]
    df.to_csv(DB_FILE, index=False)
    st.rerun()

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="wide")

# Logo e Titolo (Come l'originale)
col_logo, col_tit = st.columns([1, 6])
with col_logo:
    st.image("https://cdn-icons-png.flaticon.com/512/2912/2912761.png", width=80)
with col_tit:
    st.title("CRM Michelone Cloud")

# --- SEZIONE INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nome Cliente", key="cliente_key")
        st.radio("Tipo", ["Cliente", "Potenziale"], key="tipo_key", horizontal=True)
    with col2:
        st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
        st.date_input("Data Visita", datetime.now(), key="data_key")

    st.markdown("---")
    c_loc, c_prov, c_gps = st.columns([3, 1, 2])
    with c_loc: st.text_input("Località", key="localita_key")
    with c_prov: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    with c_gps:
        st.write(" ") # Allineamento
        loc = get_geolocation()
        if st.button("📍 POSIZIONE GPS", use_container_width=True):
            if loc:
                lat = loc['coords']['latitude']
                lon = loc['coords']['longitude']
                try:
                    res = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}").json()
                    citta = res.get('address', {}).get('city', res.get('address', {}).get('town', ''))
                    st.session_state.localita_key = citta.upper()
                    st.toast("📍 Città individuata!")
                except:
                    st.toast("📍 GPS acquisito")
            else:
                st.error("Controlla i permessi GPS del browser")

    st.text_area("Note del colloquio", key="note_key", height=100)
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True, type="primary")

st.divider()

# --- SEZIONE RICERCA E ARCHIVIO ---
st.subheader("🔍 Ricerca nell'Archivio")
df = carica_dati()

f_col1, f_col2 = st.columns(2)
with f_col1:
    cerca = st.text_input("Cerca per nome o parola chiave...")
with f_col2:
    agente_scelto = st.selectbox("Filtra per Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if not df.empty:
    # Applica i filtri
    df_filt = df.copy()
    if cerca:
        df_filt = df_filt[df_filt.astype(str).apply(lambda x: cerca.lower() in x.str.lower().any(), axis=1)]
    if agente_scelto != "Tutti":
        df_filt = df_filt[df_filt['Agente'] == agente_scelto]

    # Alert Scadenze
    oggi = datetime.now().strftime("%Y-%m-%d")
    scaduti = df_filt[(df_filt['FollowUp'] != "") & (df_filt['FollowUp'] <= oggi)]
    if not scaduti.empty:
        st.error(f"⚠️ Hai {len(scaduti)} ricontatti scaduti o previsti per oggi!")

    # Elenco visite
    for i, row in df_filt.iloc[::-1].iterrows():
        with st.expander(f"{row['Data']} - {row['Cliente']} ({row['Località']})"):
            st.write(f"**Agente:** {row['Agente']} | **Tipo:** {row['Tipo']}")
            st.info(f"**Note:** {row['Note']}")
            if row['FollowUp']:
                st.warning(f"📅 Scadenza ricontatto: {row['FollowUp']}")
            if st.button("🗑️ Elimina", key=f"del_{row['ID']}"):
                elimina_riga(row['ID'])
else:
    st.info("Archivio vuoto. Registra la prima visita sopra.")
