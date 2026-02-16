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
        # Crea un database vuoto se non esiste
        return pd.DataFrame(columns=["Data", "Agente", "Cliente", "Tipo", "Località", "Provincia", "Note", "FollowUp", "Lat", "Lon", "ID"])

def salva_visita_locale():
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
            "Lat": s.get('lat_val', ''),
            "Lon": s.get('lon_val', ''),
            "ID": str(uuid.uuid4())
        }
        
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        
        # Reset campi
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        st.toast("✅ Salvato in locale!")
        st.rerun()
    else:
        st.error("⚠️ Compila Cliente e Note!")

def elimina_riga_locale(id_da_eliminare):
    df = carica_dati()
    df = df[df['ID'].astype(str) != str(id_da_eliminare)]
    df.to_csv(DB_FILE, index=False)
    st.rerun()

# --- 2. INTERFACCIA ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="wide")

# Logo e Titolo
col_logo, col_tit = st.columns([1, 6])
with col_logo:
    st.image("https://cdn-icons-png.flaticon.com/512/2912/2912761.png", width=80)
with col_tit:
    st.title("CRM Michelone - Versione Locale")

# --- MODULO INSERIMENTO ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Nome Cliente", key="cliente_key")
        st.radio("Tipo", ["Cliente", "Potenziale"], key="tipo_key", horizontal=True)
    with c2:
        st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
        st.date_input("Data", datetime.now(), key="data_key")

    st.markdown("---")
    l1, l2, l3 = st.columns([3, 1, 2])
    with l1: st.text_input("Località", key="localita_key")
    with l2: st.text_input("Prov.", key="prov_key", max_chars=2)
    with l3:
        st.write(" ")
        loc = get_geolocation()
        if st.button("📍 POSIZIONE GPS", use_container_width=True):
            if loc:
                lat = loc['coords']['latitude']
                lon = loc['coords']['longitude']
                st.session_state['lat_val'] = str(lat)
                st.session_state['lon_val'] = str(lon)
                try:
                    r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}").json()
                    citta = r.get('address', {}).get('city', r.get('address', {}).get('town', ''))
                    st.session_state.localita_key = citta.upper()
                except: pass
            else:
                st.warning("Permesso GPS negato dal browser.")

    st.text_area("Note", key="note_key", height=100)
    st.radio("Pianifica Ricontatto", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True)
    st.button("💾 SALVA VISITA", on_click=salva_visita_locale, use_container_width=True, type="primary")

st.divider()

# --- RICERCA E VISUALIZZAZIONE ---
st.subheader("🔍 Ricerca nell'Archivio")
df = carica_dati()

f1, f2 = st.columns(2)
with f1: cerca = st.text_input("Cerca nome o nota...")
with f2: ag_filtro = st.selectbox("Filtra Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if not df.empty:
    df_filt = df.copy()
    if cerca:
        df_filt = df_filt[df_filt.astype(str).apply(lambda x: cerca.lower() in x.str.lower().any(), axis=1)]
    if ag_filtro != "Tutti":
        df_filt = df_filt[df_filt['Agente'] == ag_filtro]

    # Alert Scadenze
    oggi = datetime.now().strftime("%Y-%m-%d")
    scadenze = df_filt[(df_filt['FollowUp'] != "") & (df_filt['FollowUp'] <= oggi)]
    if not scadenze.empty:
        st.error(f"⚠️ Hai {len(scadenze)} ricontatti da gestire!")

    # Elenco Schede
    for i, row in df_filt.iloc[::-1].iterrows():
        with st.expander(f"{row['Data']} - {row['Cliente']} ({row['Località']})"):
            st.write(f"**Agente:** {row['Agente']} | **Tipo:** {row['Tipo']}")
            st.info(f"**Note:** {row['Note']}")
            if row['FollowUp']: st.warning(f"📅 Follow-up: {row['FollowUp']}")
            if st.button("🗑️ Elimina", key=f"del_{row['ID']}"):
                elimina_riga_locale(row['ID'])
else:
    st.info("Archivio vuoto.")