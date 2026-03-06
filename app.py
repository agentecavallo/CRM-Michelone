import streamlit as st
import sqlite3
import pandas as pd
import os
import time
import base64
import urllib.parse
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

# --- RUBRICA AGENTI WHATSAPP ---
# Sostituisci gli "0000000000" con i numeri veri dei tuoi agenti (lascia il +39)
NUMERI_AGENTI = {
    "HSE": "+393472503027",
    "BIENNE": "+39335458782",
    "PALAGI": "+393343524289",
    "SARDEGNA": "+393337392303"
}

# --- STILE CSS PERSONALIZZATO ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 2rem !important;
    }
    div[data-testid="stExpander"] div[role="button"] p, .stTabs button p {
        font-weight: bold !important;
        font-size: 1.05rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Inizializzazione chiavi di stato
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
                      latitudine TEXT, longitudine TEXT,
                      referente TEXT, telefono TEXT,
                      visita_autonoma INTEGER DEFAULT 0,
                      customer_net_gain INTEGER DEFAULT 0,
                      operazioni_cross_selling INTEGER DEFAULT 0)''')
        
        try: c.execute("ALTER TABLE visite ADD COLUMN copiato_crm INTEGER DEFAULT 0")
        except: pass 
        try: c.execute("ALTER TABLE visite ADD COLUMN referente TEXT DEFAULT ''")
        except: pass
        try: c.execute("ALTER TABLE visite ADD COLUMN telefono TEXT DEFAULT ''")
        except: pass
        try: c.execute("ALTER TABLE visite ADD COLUMN visita_autonoma INTEGER DEFAULT 0")
        except: pass
        try: c.execute("ALTER TABLE visite ADD COLUMN customer_net_gain INTEGER DEFAULT 0")
        except: pass
        try: c.execute("ALTER TABLE visite ADD COLUMN operazioni_cross_selling INTEGER DEFAULT 0")
        except: pass
        conn.commit()

inizializza_db()

# --- FUNZIONI DI SUPPORTO ---
def calcola_prossimo_giorno(data_partenza, giorno_obiettivo):
    giorni_mancanti = giorno_obiettivo - data_partenza.weekday()
    if giorni_mancanti <= 0:
        giorni_mancanti += 7
    return (data_partenza + timedelta(days=giorni_mancanti)).strftime("%Y-%m-%d")

def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup): os.makedirs(cartella_backup)
    now = datetime.now()
    if now.hour >= 7:
        today_str = now.strftime('%Y-%m-%d')
        backup_di_oggi_esiste = any(today_str in f for f in os.listdir(cartella_backup) if f.endswith('.xlsx'))
        if not backup_di_oggi_esiste:
            with sqlite3.connect('crm_mobile.db') as conn:
                try:
                    df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
                    if not df.empty:
                        for f in os.listdir(cartella_backup):
                            if f.endswith('.xlsx'): os.remove(os.path.join(cartella_backup, f))
                        df.to_excel(os.path.join(cartella_backup, f"Backup_Auto_{today_str}.xlsx"), index=False)
                        st.toast(f"🛡️ Backup Automatico Eseguito ({today_str})", icon="✅")
                except: pass

controllo_backup_automatico()

# --- FUNZIONE CREAZIONE LINK WHATSAPP (CORRETTA) ---
def genera_link_wa(agente, cliente, tipo, note):
    numero = NUMERI_AGENTI.get(agente, "")
    if not numero: return ""
    
    # Testo pulito, formattato, SENZA EMOJI per evitare troncamenti
    messaggio = f"*RESOCONTO VISITA*\n*Cliente:* {cliente} ({tipo})\n*Note:*\n{note}"
    
    # Codifica sicura in UTF-8
    messaggio_url = urllib.parse.quote(messaggio.encode('utf-8'))
    return f"https://wa.me/{numero}?text={messaggio_url}"

def salva_visita():
    s = st.session_state
    cliente = s.get('cliente_key', '').strip()
    note = s.get('note_key', '').strip()
    tipo = s.get('tipo_key', 'Prospect')
    referente = s.get('referente_key', '').strip()
    telefono = s.get('telefono_key', '').strip()
    autonomia = 1 if s.get('autonomia_key', False) else 0
    cng = 1 if s.get('cng_key', False) else 0
    cross = 1 if s.get('cross_key', False) else 0
    
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            
            if scelta in ["1 gg", "7 gg", "15 gg", "30 gg"]:
                data_fup = (s.data_key + timedelta(days=int(scelta.split()[0]))).strftime("%Y-%m-%d")
            elif scelta == "Alle 17:00":
                now = datetime.now()
                data_fup = ((now + timedelta(days=1)) if now.hour >= 17 else now).strftime("%Y-%m-%d") + " 17:00"
            elif scelta == "Prox. Lunedì": data_fup = calcola_prossimo_giorno(s.data_key, 0)
            elif scelta == "Prox. Venerdì": data_fup = calcola_prossimo_giorno(s.data_key, 4)
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                                 data_followup, data_ordine, agente, latitudine, longitudine, copiato_crm,
                                 referente, telefono, visita_autonoma, customer_net_gain, operazioni_cross_selling) 
                                 VALUES (?, '', '', ?, ?, ?, ?, ?, ?, '', '', 0, ?, ?, ?, ?, ?)""", 
                      (cliente, tipo, data_visita_fmt, note, data_fup, data_ord, s.agente_key, referente, telefono, autonomia, cng, cross))
            conn.commit()
        
        for k in ['cliente_key', 'note_key', 'referente_key', 'telefono_key']: st.session_state[k] = ""
        for k in ['autonomia_key', 'cng_key', 'cross_key']: st.session_state[k] = False
        st.session_state.fup_opt = "No"
        st.toast("✅ Visita salvata nel database!", icon="💾")
    else:
        st.error("⚠️ Attenzione: Cliente e Note sono obbligatori!")

def aggiorna_fup(id_val, query_mod, params):
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute(query_mod, params)
        conn.commit()

def posticipa_fup_diretto(id_val, giorni):
    nuova_data = (datetime.now() + timedelta(days=giorni)).strftime("%Y-%m-%d")
    aggiorna_fup(id_val, "UPDATE visite SET data_followup = ? WHERE id = ?", (nuova_data, id_val))

def set_fup_prox(id_val, gg): aggiorna_fup(id_val, "UPDATE visite SET data_followup = ? WHERE id = ?", (calcola_prossimo_giorno(datetime.now(), gg), id_val))
def set_fup_alle_1700(id_val): 
    now = datetime.now()
    aggiorna_fup(id_val, "UPDATE visite SET data_followup = ? WHERE id = ?", (((now + timedelta(days=1)) if now.hour >= 17 else now).strftime("%Y-%m-%d") + " 17:00", id_val))
def azzera_fup(id_val): aggiorna_fup(id_val, "UPDATE visite SET data_followup = '' WHERE id = ?", (id_val,))

def set_edit_mode(id_val): st.session_state.edit_mode_id = id_val
def cancel_edit(): st.session_state.edit_mode_id = None
def ask_delete(id_val): st.session_state[f"confirm_del_{id_val}"] = True
def cancel_delete(id_val): st.session_state[f"confirm_del_{id_val}"] = False
def toggle_crm_copy(id_val): aggiorna_fup(id_val, "UPDATE visite SET copiato_crm = ? WHERE id = ?", (1 if st.session_state.get(f"chk_crm_{id_val}", False) else 0, id_val))

def execute_save_modifica(id_val):
    s = st.session_state
    new_fup = s.get(f"e_dt_{id_val}").strftime("%Y-%m-%d") if s.get(f"e_chk_{id_val}", False) else ""
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("""UPDATE visite SET cliente=?, tipo_cliente=?, note=?, agente=?, data_followup=?, referente=?, telefono=?, visita_autonoma=?, customer_net_gain=?, operazioni_cross_selling=? WHERE id=?""",
                     (s.get(f"e_cli_{id_val}", ""), s.get(f"e_tp_{id_val}", "Prospect"), s.get(f"e_note_{id_val}", ""), s.get(f"e_ag_{id_val}", "HSE"), new_fup, s.get(f"e_ref_{id_val}", ""), s.get(f"e_tel_{id_val}", ""), 1 if s.get(f"e_aut_{id_val}", False) else 0, 1 if s.get(f"e_cng_{id_val}", False) else 0, 1 if s.get(f"e_cross_{id_val}", False) else 0, id_val))
        conn.commit()
    st.session_state.edit_mode_id = None

def execute_delete_visita(id_val):
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("DELETE FROM visite WHERE id = ?", (id_val,))
        conn.commit()
    st.session_state[f"confirm_del_{id_val}"] = False

with sqlite3.connect('crm_mobile.db') as conn:
    oggi_limite = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi_limite}' ORDER BY data_followup ASC", conn)
num_scadenze = len(df_scadenze)

# ==========================================
# INTESTAZIONE CON TITOLO E LOGO 
# ==========================================
try:
    with open("logo.jpg", "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()
    
    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: flex-start; gap: 15px; margin-bottom: 20px;">
        <h1 style="margin: 0; padding: 0; font-size: 2.2rem; display: inline;">💼 CRM Michelone</h1>
        <img src="data:image/jpeg;base64,{encoded_string}" style="width: 60px; height: auto; border-radius: 8px;">
    </div>
    """, unsafe_allow_html=True)
except Exception:
    st.title("💼 CRM Michelone") 

if num_scadenze > 0:
    st.error(f"⚠️ Attenzione Michelone! Hai **{num_scadenze}** ricontatti urgenti da gestire.")

st.write("") 

# --- TABS ---
tab_nuova, tab_scadenze, tab_archivio, tab_setup = st.tabs(["➕ Nuova", "⏰ Scadenze", "🔍 Archivio", "⚙️ Setup"])

# ==========================================
# TAB 1: NUOVA VISITA
# ==========================================
with tab_nuova:
    st.write("### Compila Dati Incontro")
    
    with st.container(border=True):
        st.text_input("Nome Cliente", key="cliente_key", placeholder="Scrivi Qui...")
        st.selectbox("Stato Cliente", ["Cliente", "Prospect"], key="tipo_key")
        
        c_ref, c_tel = st.columns(2)
        with c_ref: st.text_input("Referente", key="referente_key", placeholder="Scrivi Qui...")
        with c_tel: st.text_input("Mail / Tel", key="telefono_key", placeholder="Scrivi Qui...")
        
        st.markdown("---")
        c_dt, c_ag = st.columns(2)
        with c_dt: st.date_input("Data Visita", datetime.now(), format="DD/MM/YYYY", key="data_key")
        with c_ag: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
        
        st.markdown("**Dettagli Operativi:**")
        ck1, ck2, ck3 = st.columns(3)
        with ck1: st.checkbox("🚶‍♂️ Autonomia", key="autonomia_key")
        with ck2: st.checkbox("🚀 C. Net Gain", key="cng_key")
        with ck3: st.checkbox("🔄 Cross Selling", key="cross_key")
        
        # Le note
        st.text_area("Note / Resoconto", key="note_key", height=200, placeholder="Scrivi Qui...")
        
        # --- TASTO WHATSAPP IN INSERIMENTO ---
        # Avviso importante per l'utente per evitare che mandi un messaggio vuoto
        st.caption("*(💡 Scrivi le note, clicca fuori dal riquadro per confermarle e poi premi il tasto qui sotto per inviare)*")
        link_wa_nuovo = genera_link_wa(
            st.session_state.get('agente_key', 'HSE'),
            st.session_state.get('cliente_key', ''),
            st.session_state.get('tipo_key', 'Prospect'),
            st.session_state.get('note_key', '')
        )
        st.link_button("📲 INVIA RESOCONTO SU WHATSAPP", link_wa_nuovo, use_container_width=True)
        # -----------------------------------------------

        st.markdown("---")
        st.markdown("**📅 Pianifica Ricontatto:**")
        st.radio("Scadenza", ["No", "Alle 17:00", "1 gg", "7 gg", "15 gg", "30 gg", "Prox. Lunedì", "Prox. Venerdì"], key="fup_opt", horizontal=True, label_visibility="collapsed")
        
    st.write("")
    st.button("💾 SALVA NEL CRM MICHELONE", on_click=salva_visita, type="primary", use_container_width=True)

# ==========================================
# TAB 2: SCADENZE
# ==========================================
with tab_scadenze:
    if num_scadenze > 0:
        oggi = datetime.now().strftime("%Y-%m-%d")
        for _, row in df_scadenze.iterrows():
            try: row_id = int(float(row['id']))
            except: continue

            try:
                d_scad = datetime.strptime(row['data_followup'][:10], "%Y-%m-%d")
                giorni_ritardo = (datetime.strptime(oggi, "%Y-%m-%d") - d_scad).days
                msg_scadenza = "Oggi" if giorni_ritardo <= 0 else f"Da {giorni_ritardo} gg"
                if len(row['data_followup']) > 10: msg_scadenza += f" alle {row['data_followup'][11:]}"
            except: msg_scadenza = "Scaduto"

            with st.container(border=True):
                st.markdown(f"#### {row['cliente']} ({row['tipo_cliente']})")
                st.caption(f"⏰ **In Scadenza:** {msg_scadenza}")
                st.info(f"**Note Ultime:** {row['note']}")
                
                c1, c2, c3, c4 = st.columns([1, 1, 1, 1.3])
                with c1: st.button("+1 gg", key=f"p1_{row_id}", use_container_width=True, on_click=posticipa_fup_diretto, args=(row_id, 1))
                with c2: st.button("+7 gg", key=f"p7_{row_id}", use_container_width=True, on_click=posticipa_fup_diretto, args=(row_id, 7))
                with c3: st.button("+15 gg", key=f"p15_{row_id}", use_container_width=True, on_click=posticipa_fup_diretto, args=(row_id, 15))
                with c4: st.button("✅ Gestito", key=f"ok_{row_id}", type="primary", use_container_width=True, on_click=azzera_fup, args=(row_id,))
                        
                c5, c6, c7 = st.columns(3)
                with c5: st.button("🕔 17:00", key=f"o1700_{row_id}", use_container_width=True, on_click=set_fup_alle_1700, args=(row_id,))
                with c6: st.button("➡️ Lunedì", key=f"pl_{row_id}", use_container_width=True, on_click=set_fup_prox, args=(row_id, 0))
                with c7: st.button("➡️ Venerdì", key=f"pv_{row_id}", use_container_width=True, on_click=set_fup_prox, args=(row_id, 4))
    else:
        st.success("🎉 Grandioso! Nessun ricontatto in scadenza, tutto sotto controllo.")
        
        with sqlite3.connect('crm_mobile.db') as conn:
            df_future = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup > '{oggi_limite}' ORDER BY data_followup ASC", conn)
        
        if not df_future.empty:
            st.markdown("---")
            st.markdown("### 🔮 Prossime Scadenze in Arrivo")
            for _, row in df_future.iterrows():
                fup_str = row['data_followup']
                dt_fmt = datetime.strptime(fup_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y alle %H:%M") if ":" in fup_str else datetime.strptime(fup_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                
                with st.container(border=True):
                    st.markdown(f"**{row['cliente']}**")
                    st.caption(f"📅 **{dt_fmt}**")

# ==========================================
# TAB 3: ARCHIVIO E RICERCA
# ==========================================
with tab_archivio:
    st.write("### Consulta Database Visite")
    
    t_ricerca = st.text_input("Testo Libero (Cliente o Note)", placeholder="Scrivi Qui...") 
    periodo = st.date_input("Periodo Visita", [datetime.today().date() - timedelta(days=60), datetime.today().date()], format="DD/MM/YYYY")
    
    with st.expander("⚙️ Filtri Avanzati (Tocca per aprire)"):
        c_f1, c_f2 = st.columns(2)
        f_agente = c_f1.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])
        f_tipo = c_f2.selectbox("Stato Cliente", ["Tutti", "Prospect", "Cliente"])
        
        c_f3, c_f4 = st.columns(2)
        f_stato_crm = c_f3.selectbox("Salvato su CRM Aziendale", ["Tutti", "Da Caricare", "Caricati"])
        f_referente = c_f4.selectbox("Dati Contatto", ["Tutti", "Con Referente", "Senza"])
        
        f_autonomia = st.selectbox("Modalità Visita", ["Tutte", "In Autonomia", "In Affiancamento"])
        
        c_f6, c_f7 = st.columns(2)
        f_cng = c_f6.selectbox("🚀 Customer Net Gain", ["Tutti", "Sì", "No"])
        f_cross = c_f7.selectbox("🔄 Cross Selling", ["Tutti", "Sì", "No"])

    st.write("")
    if st.button("🔎 AVVIA RICERCA", use_container_width=True, type="primary"):
        st.session_state.ricerca_attiva = True
        st.session_state.edit_mode_id = None 

    if st.session_state.ricerca_attiva:
        st.divider()
        with sqlite3.connect('crm_mobile.db') as conn:
            df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
        
        if t_ricerca: df = df[df['cliente'].str.contains(t_ricerca, case=False, na=False) | df['note'].str.contains(t_ricerca, case=False, na=False)]
        if f_agente != "Tutti": df = df[df['agente'] == f_agente]
        if f_tipo != "Tutti": df = df[df['tipo_cliente'] == f_tipo]
        if f_stato_crm == "Da Caricare": df = df[(df['copiato_crm'] == 0) | (df['copiato_crm'].isnull())]
        elif f_stato_crm == "Caricati": df = df[df['copiato_crm'] == 1]
        if f_referente == "Con Referente": df = df[(df['referente'].notnull()) & (df['referente'].str.strip() != '')]
        elif f_referente == "Senza": df = df[(df['referente'].isnull()) | (df['referente'].str.strip() == '')]
        if f_autonomia == "In Autonomia": df = df[df['visita_autonoma'] == 1]
        elif f_autonomia == "In Affiancamento": df = df[(df['visita_autonoma'] == 0) | (df['visita_autonoma'].isnull())]
        if f_cng == "Sì": df = df[df['customer_net_gain'] == 1]
        elif f_cng == "No": df = df[(df['customer_net_gain'] == 0) | (df['customer_net_gain'].isnull())]
        if f_cross == "Sì": df = df[df['operazioni_cross_selling'] == 1]
        elif f_cross == "No": df = df[(df['operazioni_cross_selling'] == 0) | (df['operazioni_cross_selling'].isnull())]

        if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
             df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

        if not df.empty:
            c_res1, c_res2 = st.columns([2, 1])
            c_res1.success(f"Trovate {len(df)} visite corrispondenti.")
            if c_res2.button("Chiudi ❌", use_container_width=True):
                st.session_state.ricerca_attiva = False; st.rerun()

            for _, row in df.iterrows():
                try: row_id = int(float(row['id']))
                except: continue
                    
                icona_crm = "✅" if row.get('copiato_crm') == 1 else "⏳"
                badge_tipo = f"[{row['tipo_cliente']}]" if row['tipo_cliente'] else ""
                tendina_aperta = (st.session_state.edit_mode_id == row_id) or st.session_state.get(f"confirm_del_{row_id}", False)
                
                with st.expander(f"{icona_crm} {row['data']} - {row['cliente']} {badge_tipo}", expanded=tendina_aperta):
                    if st.session_state.edit_mode_id == row_id:
                        st.info("✏️ Modifica Dati Attiva")
                        st.text_input("Nome Cliente", value=str(row['cliente'] or ""), placeholder="Scrivi Qui...", key=f"e_cli_{row_id}")
                        st.selectbox("Stato", ["Prospect", "Cliente"], index=0 if row['tipo_cliente'] == "Prospect" else 1, key=f"e_tp_{row_id}")
                        
                        c_rt1, c_rt2 = st.columns(2)
                        with c_rt1: st.text_input("Referente", value=str(row.get('referente', '') or ""), placeholder="Scrivi Qui...", key=f"e_ref_{row_id}")
                        with c_rt2: st.text_input("Mail o Telefono", value=str(row.get('telefono', '') or ""), placeholder="Scrivi Qui...", key=f"e_tel_{row_id}")

                        st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], index=["HSE", "BIENNE", "PALAGI", "SARDEGNA"].index(row['agente']) if row['agente'] in ["HSE", "BIENNE", "PALAGI", "SARDEGNA"] else 0, key=f"e_ag_{row_id}")
                        
                        ca1, ca2, ca3 = st.columns(3)
                        with ca1: st.checkbox("🚶‍♂️ Autonomia", value=bool(row.get('visita_autonoma', 0)), key=f"e_aut_{row_id}")
                        with ca2: st.checkbox("🚀 C.N.G.", value=bool(row.get('customer_net_gain', 0)), key=f"e_cng_{row_id}")
                        with ca3: st.checkbox("🔄 Cross S.", value=bool(row.get('operazioni_cross_selling', 0)), key=f"e_cross_{row_id}")
                        
                        st.text_area("Note / Resoconto", value=str(row['note'] or ""), height=300, placeholder="Scrivi Qui...", key=f"e_note_{row_id}")
                        
                        fup_attuale = row['data_followup']
                        if st.checkbox("Pianifica Ricontatto", value=True if fup_attuale else False, key=f"e_chk_{row_id}"):
                            st.date_input("Data Ricontatto", value=datetime.strptime(fup_attuale[:10], "%Y-%m-%d").date() if fup_attuale else datetime.today().date(), format="DD/MM/YYYY", key=f"e_dt_{row_id}")

                        cs, cc = st.columns(2)
                        cs.button("💾 SALVA MODIFICHE", key=f"save_{row_id}", type="primary", use_container_width=True, on_click=execute_save_modifica, args=(row_id,))
                        cc.button("❌ ANNULLA", key=f"canc_{row_id}", use_container_width=True, on_click=cancel_edit)
                    
                    else:
                        st.write(f"**Agente:** {row['agente']} | **Stato Cliente:** {row['tipo_cliente']}")
                        
                        tags = []
                        if row.get('visita_autonoma') == 1: tags.append("🚶‍♂️ Autonomia")
                        if row.get('customer_net_gain') == 1: tags.append("🚀 C. Net Gain")
                        if row.get('operazioni_cross_selling') == 1: tags.append("🔄 Cross Selling")
                        if tags: st.caption("Etichette: " + " | ".join(tags))
                        
                        if row.get('referente') or row.get('telefono'):
                            st.write(f"👤 **{row.get('referente', '')}** 📞 {row.get('telefono', '')}")
                            
                        st.info(f"{row['note']}")
                        st.checkbox("✅ Salvato nel gestionale aziendale", value=(row.get('copiato_crm') == 1), key=f"chk_crm_{row_id}", on_change=toggle_crm_copy, args=(row_id,))

                        if row['data_followup']:
                            fup_str = row['data_followup']
                            dt_fmt = datetime.strptime(fup_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y alle %H:%M") if ":" in fup_str else datetime.strptime(fup_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                            st.markdown(f"**📅 Ricontatto pianificato il:** {dt_fmt}")
                        
                        st.write("")
                        
                        # --- TASTO WHATSAPP IN ARCHIVIO ---
                        cb_m, cb_w, cb_d = st.columns([1, 1, 1])
                        
                        cb_m.button("✏️ Modifica", key=f"btn_mod_{row_id}", use_container_width=True, on_click=set_edit_mode, args=(row_id,))
                        
                        link_wa_archivio = genera_link_wa(row['agente'], row['cliente'], row['tipo_cliente'], row['note'])
                        cb_w.link_button("📲 Invia WA", link_wa_archivio, use_container_width=True)
                        
                        cb_d.button("🗑️ Elimina", key=f"btn_del_{row_id}", use_container_width=True, on_click=ask_delete, args=(row_id,))
                        # -----------------------------------------------------------
                        
                        if st.session_state.get(f"confirm_del_{row_id}", False):
                            st.warning("⚠️ Confermi l'eliminazione definitiva?")
                            cy, cn = st.columns(2)
                            cy.button("SÌ, ELIMINA", key=f"yes_{row_id}", type="primary", use_container_width=True, on_click=execute_delete_visita, args=(row_id,))
                            cn.button("NO", key=f"no_{row_id}", use_container_width=True, on_click=cancel_delete, args=(row_id,))
        else:
            st.warning("Nessun risultato trovato con questi filtri.")

# ==========================================
# TAB 4: SETUP E BACKUP
# ==========================================
with tab_setup:
    st.write("### Centro Sicurezza e Backup Dati")
    st.info("Utilizza questa sezione per scaricare i backup sul tuo telefono o ripristinarli se cambi dispositivo.")
    
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_full.to_excel(writer, index=False)
    
    st.download_button("📥 ESPORTA TUTTO IL DB (EXCEL)", output.getvalue(), "backup_crm_michelone_completo.xlsx", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.write("📤 **RIPRISTINO DATI (Sovrascrittura Completa)**")
    st.caption("⚠️ ATTENZIONE: i dati attuali nel telefono verranno cancellati e sostituiti da quelli del file Excel.")
    file_caricato = st.file_uploader("Seleziona file Excel di backup", type=["xlsx"], key="restore_uploader")
    if file_caricato is not None:
        if st.button("⚠️ AVVIA RIPRISTINO (AZIONE IRREVERSIBILE)", type="primary", use_container_width=True):
            try:
                df_ripristino = pd.read_excel(file_caricato)
                if 'cliente' in df_ripristino.columns and 'note' in df_ripristino.columns:
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("DROP TABLE IF EXISTS visite")
                        conn.execute('''CREATE TABLE visite 
                                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                      cliente TEXT, localita TEXT, provincia TEXT,
                                      tipo_cliente TEXT, data TEXT, note TEXT,
                                      data_followup TEXT, data_ordine TEXT, agente TEXT,
                                      latitudine TEXT, longitudine TEXT, copiato_crm INTEGER DEFAULT 0,
                                      referente TEXT, telefono TEXT, visita_autonoma INTEGER DEFAULT 0,
                                      customer_net_gain INTEGER DEFAULT 0, operazioni_cross_selling INTEGER DEFAULT 0)''')
                        df_ripristino.to_sql('visite', conn, if_exists='append', index=False)
                    st.success("✅ Database ripristinato con successo! Aggiornamento App in corso...")
                    time.sleep(2)
                    st.rerun()
                else: st.error("❌ Il file non sembra un backup valido del CRM.")
            except Exception as e: st.error(f"Errore durante il ripristino: {e}")
                
    st.markdown("---")
    st.write("📂 **STORICO BACKUP GIORNALIERI (Dal Server)**")
    cartella_backup = "BACKUPS_AUTOMATICI"
    if os.path.exists(cartella_backup):
        files_backup = sorted([f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')], reverse=True)
        if files_backup:
            file_selezionato = st.selectbox("Seleziona il backup giornaliero da scaricare:", files_backup)
            with open(os.path.join(cartella_backup, file_selezionato), "rb") as f:
                st.download_button(label=f"⬇️ SCARICA {file_selezionato}", data=f, file_name=file_selezionato, use_container_width=True)
            
            st.write("") 
            ultimo_backup = files_backup[0]
            st.warning(f"🔄 **Ripristino di Emergenza (Ultimo salvataggio: {ultimo_backup})**")
            
            if st.button("⚠️ RIPRISTINA ORA ALL'ULTIMO BACKUP AUTOMATICO", type="primary", use_container_width=True):
                try:
                    df_ripristino = pd.read_excel(os.path.join(cartella_backup, ultimo_backup))
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("DROP TABLE IF EXISTS visite")
                        conn.execute('''CREATE TABLE visite 
                                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                      cliente TEXT, localita TEXT, provincia TEXT,
                                      tipo_cliente TEXT, data TEXT, note TEXT,
                                      data_followup TEXT, data_ordine TEXT, agente TEXT,
                                      latitudine TEXT, longitudine TEXT, copiato_crm INTEGER DEFAULT 0,
                                      referente TEXT, telefono TEXT, visita_autonoma INTEGER DEFAULT 0,
                                      customer_net_gain INTEGER DEFAULT 0, operazioni_cross_selling INTEGER DEFAULT 0)''')
                        df_ripristino.to_sql('visite', conn, if_exists='append', index=False)
                    st.success(f"✅ Dati ripristinati da {ultimo_backup}! Riavvio app in corso...")
                    time.sleep(2)
                    st.rerun()
                except Exception as e: 
                    st.error(f"Errore durante il ripristino: {e}")

        else: 
            st.caption("Ancora nessun backup giornaliero automatico generato finora.")
    else: 
        st.caption("La cartella dei backup automatici verrà creata al primo salvataggio giornaliero.")

# Footer Minimal
st.write("") 
st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em; font-weight: bold;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)

