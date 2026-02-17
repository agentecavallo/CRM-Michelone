import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation
import streamlit.components.v1 as components

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

# --- FUNZIONE JAVASCRIPT PER COPIARE ---
def copia_negli_appunti(testo, id_bottone):
    # Pulizia testo per JavaScript
    testo_safe = testo.replace("`", "'").replace("\n", " ")
    html_code = f"""
    <button id="btn_{id_bottone}" style="
        background-color: #f0f2f6; 
        border: 1px solid #dcdfe3; 
        border-radius: 8px; 
        padding: 8px; 
        cursor: pointer;
        width: 100%;
        font-weight: bold;
        color: #31333F;">
        📋 COPIA NOTE
    </button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        const text = `{testo_safe}`;
        navigator.clipboard.writeText(text).then(function() {{
            alert("Note copiate!");
        }}, function(err) {{
            console.error('Errore:', err);
        }});
    }};
    </script>
    """
    components.html(html_code, height=50)

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
    tipo = s.get('tipo_key', 'Prospect')
    
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            
            giorni_da_aggiungere = 0
            if scelta == "1 gg": giorni_da_aggiungere = 1
            elif scelta == "7 gg": giorni_da_aggiungere = 7
            elif scelta == "15 gg": giorni_da_aggiungere = 15
            elif scelta == "30 gg": giorni_da_aggiungere = 30
            
            if giorni_da_aggiungere > 0:
                data_fup = (s.data_key + timedelta(days=giorni_da_aggiungere)).strftime("%Y-%m-%d")
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), tipo, 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, 
                       s.lat_val, s.lon_val))
            conn.commit()
        
        st.session_state.cliente_key = ""
        st.session_state.localita_key = ""
        st.session_state.prov_key = ""
        st.session_state.note_key = ""
        st.session_state.lat_val = ""
        st.session_state.lon_val = ""
        st.session_state.fup_opt = "No"
        st.toast("✅ Visita salvata con successo!", icon="💾")
    else:
        st.error("⚠️ Errore: Inserisci almeno Nome Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=not st.session_state.ricerca_attiva): 
    st.text_input("Nome Cliente", key="cliente_key", placeholder="Es: Mario Rossi Srl")
    
    # MODIFICA: Radio button al posto della selectbox per velocità mobile
    st.radio("Tipo Cliente", ["Prospect", "Cliente"], 
             key="tipo_key", 
             horizontal=True, 
             format_func=lambda x: "🚀 Prospect" if x == "Prospect" else "🤝 Cliente")
    
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    loc_data = get_geolocation()
    if st.button("📍 USA POSIZIONE ATTUALE", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_Michelone_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                
                prov_full = a.get('county', '')
                if prov_full and ("Roma" in prov_full or "Rome" in prov_full):
                    prov_sigla = "RM"
                else:
                    prov_sigla = prov_full[:2].upper() if prov_full else "??"
                
                st.session_state['gps_temp'] = {'citta': citta.upper() if citta else "", 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Errore nel recupero indirizzo. GPS attivo?")
        else: st.warning("⚠️ Attiva il GPS sul telefono.")

    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Rilevato: **{d['citta']} ({d['prov']})**")
        c_yes, c_no = st.columns(2)
        with c_yes: st.button("✅ CONFERMA", on_click=applica_dati_gps, use_container_width=True)
        with c_no: 
            if st.button("❌ ANNULLA", use_container_width=True): 
                del st.session_state['gps_temp']
                st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data Visita", datetime.now(), key="data_key")
    with c2: st.selectbox("Tuo Nome (Agente)", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Cosa vi siete detti? (Note)", key="note_key", height=150)
    st.write("📅 **Pianifica un ricontatto tra:**")
    st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    st.button("💾 SALVA VISITA NEL CRM", on_click=salva_visita, use_container_width=True, type="primary")

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **{len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        with st.container(border=True):
            tipo_icon = "🚀" if row['tipo_cliente'] == "Prospect" else "🤝"
            st.markdown(f"**{tipo_icon} {row['cliente']}** - {row['localita']}")
            st.caption(f"Note prec: {row['note']}")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("+1 gg", key=f"p1_{row['id']}", use_container_width=True):
                    nuova = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova, row['id']))
                    st.rerun()
            with c2:
                if st.button("+7 gg", key=f"p7_{row['id']}", use_container_width=True):
                    nuova = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova, row['id']))
                    st.rerun()
            with c3:
                if st.button("Fatto ✅", key=f"ok_{row['id']}", type="primary", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    st.rerun()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Ricerca Visite")
f1, f2 = st.columns([2, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
f_agente = f2.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if st.button("🔎 AVVIA RICERCA", use_container_width=True):
    st.session_state.ricerca_attiva = True
    st.session_state.edit_mode_id = None 

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]

    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        if st.button("❌ CHIUDI RICERCA"):
            st.session_state.ricerca_attiva = False
            st.rerun()

        for _, row in df.iterrows():
            label_titolo = f"{row['data']} - {row['cliente']}"
            with st.expander(label_titolo):
                if st.session_state.edit_mode_id == row['id']:
                    st.info("✏️ Modifica Dati")
                    new_cliente = st.text_input("Cliente", value=row['cliente'], key=f"e_cli_{row['id']}")
                    
                    # Anche qui selettore rapido 
                    new_tipo = st.radio("Stato", ["Prospect", "Cliente"], 
                                      index=0 if row['tipo_cliente'] == "Prospect" else 1,
                                      horizontal=True,
                                      format_func=lambda x: "🚀 Prospect" if x == "Prospect" else "🤝 Cliente",
                                      key=f"e_tp_{row['id']}")

                    new_loc = st.text_input("Località", value=row['localita'], key=f"e_loc_{row['id']}")
                    new_note = st.text_area("Note", value=row['note'], height=100, key=f"e_note_{row['id']}")
                    
                    cs, cc = st.columns(2)
                    if cs.button("💾 AGGIORNA", key=f"save_{row['id']}", type="primary", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("""UPDATE visite SET cliente=?, tipo_cliente=?, localita=?, note=? WHERE id=?""",
                                         (new_cliente, new_tipo, new_loc.upper(), new_note, row['id']))
                        st.session_state.edit_mode_id = None
                        st.rerun()
                    if cc.button("❌ ANNULLA", key=f"canc_{row['id']}", use_container_width=True):
                        st.session_state.edit_mode_id = None
                        st.rerun()
                else:
                    icona = "🚀" if row['tipo_cliente'] == "Prospect" else "🤝"
                    st.write(f"**Stato:** {icona} {row['tipo_cliente']} | **Agente:** {row['agente']}")
                    st.write(f"📍 **Dove:** {row['localita']} ({row['provincia']})")
                    
                    st.info(row['note'])
                    copia_negli_appunti(row['note'], row['id'])
                    
                    if row['latitudine']:
                        map_link = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                        st.markdown(f"[📍 Apri Navigatore Google Maps]({map_link})")
                    
                    c_mod, c_del = st.columns(2)
                    if c_mod.button("✏️ Modifica", key=f"btn_mod_{row['id']}", use_container_width=True):
                        st.session_state.edit_mode_id = row['id']
                        st.rerun()
                    if c_del.button("🗑️ Elimina", key=f"btn_del_{row['id']}", use_container_width=True):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                        st.rerun()
    else:
        st.warning("Nessun risultato.")

# --- GESTIONE DATI ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    
    st.download_button("📥 SCARICA TUTTO IN EXCEL", output.getvalue(), "backup_crm.xlsx", use_container_width=True)
    
    st.markdown("---")
    file_caricato = st.file_uploader("Ripristina da Excel", type=["xlsx"])
    if file_caricato and st.button("⚠️ SOVRASCRIVI DATABASE", type="primary"):
        df_ripristino = pd.read_excel(file_caricato)
        with sqlite3.connect('crm_mobile.db') as conn:
            df_ripristino.to_sql('visite', conn, if_exists='replace', index=False)
        st.success("✅ Fatto! Ricarica la pagina.")

st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em;'>CRM MICHELONE APPROVED ✅</p>", unsafe_allow_html=True)

# --- LOGO FINALE 'MICHELONE APPROVED' ---
st.write("") 
st.divider() 

col_f1, col_f2, col_f3 = st.columns([1, 2, 1]) 

with col_f2:
    try:
        # Carica il logo se presente nella cartella
        st.image("logo.jpg", use_container_width=True)
        st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em; font-weight: bold;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
    except Exception:
        # Se il file logo.jpg manca, mostra un badge testuale carino
        st.markdown("""
            <div style='text-align: center; border: 2px solid #4CAF50; border-radius: 10px; padding: 10px;'>
                <span style='color: #4CAF50; font-weight: bold; font-size: 1.2em;'>✅ MICHELONE APPROVED</span>
            </div>
        """, unsafe_allow_html=True)
