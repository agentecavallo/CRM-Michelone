import streamlit as st
import sqlite3
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

# --- STILE CSS PERSONALIZZATO (Il "Brio") ---
st.markdown("""
<style>
    /* Nasconde il menu in alto e il footer di Streamlit per fare spazio */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Rende l'app più "ariosa" sui bordi del telefono */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
    }
    
    /* Arrotonda un po' le card per un look moderno */
    div[data-testid="stExpander"] div[role="button"] p {
        font-weight: bold !important;
        font-size: 1.1rem !important;
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
        
        # Migrazioni
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
                        st.toast(f"🛡️ Backup Eseguito ({today_str})", icon="✅")
                except: pass

controllo_backup_automatico()

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
        st.toast("✅ Visita salvata con successo!", icon="💾")
    else:
        st.error("⚠️ Attenzione: Cliente e Note sono obbligatori!")

# --- CALLBACKS SCADENZE ---
def aggiorna_fup(id_val, query_mod, params):
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute(query_mod, params)
        conn.commit()

def posticipa_fup(id_val): aggiorna_fup(id_val, "UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=st.session_state.get('temp_giorni', 0))).strftime("%Y-%m-%d"), id_val))
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

# --- PRE-CALCOLO SCADENZE PER LE TABS ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi_limite = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi_limite}' ORDER BY data_followup ASC", conn)

num_scadenze = len(df_scadenze)
badge_scadenze = f"⏰ Scadenze ({num_scadenze})" if num_scadenze > 0 else "✅ Nessuna Scadenza"


# --- COSTRUZIONE TABS ---
st.title("💼 CRM Michelone")

tab_nuova, tab_scadenze, tab_archivio, tab_setup = st.tabs(["➕ Nuova Visita", badge_scadenze, "🔍 Archivio", "⚙️ Setup"])

# ==========================================
# TAB 1: NUOVA VISITA
# ==========================================
with tab_nuova:
    st.write("### Compila Dati Visita")
    
    # Box per evidenziare visivamente l'inserimento
    with st.container(border=True):
        st.text_input("Nome Cliente", key="cliente_key", placeholder="Scrivi Qui...")
        st.selectbox("Stato Cliente", ["Cliente", "Prospect"], key="tipo_key")
        
        c_ref, c_tel = st.columns(2)
        with c_ref: st.text_input("Referente", key="referente_key", placeholder="Scrivi Qui...")
        with c_tel: st.text_input("Mail / Tel", key="telefono_key", placeholder="Scrivi Qui...")
        
        c_dt, c_ag = st.columns(2)
        with c_dt: st.date_input("Data Visita", datetime.now(), format="DD/MM/YYYY", key="data_key")
        with c_ag: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
        
        st.markdown("**Dettagli Operativi:**")
        ck1, ck2, ck3 = st.columns(3)
        with ck1: st.checkbox("🚶‍♂️ Autonomia", key="autonomia_key")
        with ck2: st.checkbox("🚀 C. Net Gain", key="cng_key")
        with ck3: st.checkbox("🔄 Cross Selling", key="cross_key")
        
        st.text_area("Note / Resoconto", key="note_key", height=150, placeholder="Scrivi Qui...")
        
        st.markdown("**📅 Pianifica Ricontatto:**")
        st.radio("Scadenza", ["No", "Alle 17:00", "1 gg", "7 gg", "15 gg", "30 gg", "Prox. Lunedì", "Prox. Venerdì"], key="fup_opt", horizontal=True, label_visibility="collapsed")
        
    # Tasto gigante e prominente
    st.write("")
    st.button("💾 SALVA NEL CRM", on_click=salva_visita, type="primary", use_container_width=True)

# ==========================================
# TAB 2: SCADENZE
# ==========================================
with tab_scadenze:
    if num_scadenze > 0:
        st.error(f"Hai **{num_scadenze}** clienti che attendono un tuo contatto.")
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
                st.caption(f"⏰ **Scadenza:** {msg_scadenza}")
                st.info(f"**Note:** {row['note']}")
                
                # Bottoni posticipo compatti
                c1, c2, c3, c4 = st.columns(4)
                with c1: 
                    if st.button("+1 gg", key=f"p1_{row_id}", use_container_width=True): st.session_state.temp_giorni = 1; posticipa_fup(row_id); st.rerun()
                with c2: 
                    if st.button("+7 gg", key=f"p7_{row_id}", use_container_width=True): st.session_state.temp_giorni = 7; posticipa_fup(row_id); st.rerun()
                with c3: 
                    if st.button("+15 gg", key=f"p15_{row_id}", use_container_width=True): st.session_state.temp_giorni = 15; posticipa_fup(row_id); st.rerun()
                with c4: st.button("✅ Fatto", key=f"ok_{row_id}", type="primary", use_container_width=True, on_click=azzera_fup, args=(row_id,))
                        
                c5, c6, c7 = st.columns(3)
                with c5: st.button("🕔 17:00", key=f"o1700_{row_id}", use_container_width=True, on_click=set_fup_alle_1700, args=(row_id,))
                with c6: st.button("➡️ Lunedì", key=f"pl_{row_id}", use_container_width=True, on_click=set_fup_prox, args=(row_id, 0))
                with c7: st.button("➡️ Venerdì", key=f"pv_{row_id}", use_container_width=True, on_click=set_fup_prox, args=(row_id, 4))
    else:
        st.success("🎉 Grandioso! Non hai nessuna scadenza in arretrato.")

# ==========================================
# TAB 3: ARCHIVIO E RICERCA
# ==========================================
with tab_archivio:
    st.write("### Cerca nel Database")
    
    t_ricerca = st.text_input("Testo Libero (Cliente o Note)", placeholder="Scrivi Qui...") 
    periodo = st.date_input("Seleziona Periodo", [datetime.today().date() - timedelta(days=60), datetime.today().date()], format="DD/MM/YYYY")
    
    with st.expander("⚙️ Filtri Dettagliati (Tocca per aprire)"):
        c_f1, c_f2 = st.columns(2)
        f_agente = c_f1.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])
        f_tipo = c_f2.selectbox("Stato", ["Tutti", "Prospect", "Cliente"])
        
        c_f3, c_f4 = st.columns(2)
        f_stato_crm = c_f3.selectbox("Salvataggio CRM", ["Tutti", "Da Caricare", "Caricati"])
        f_referente = c_f4.selectbox("Referente", ["Tutti", "Con Referente", "Senza"])
        
        f_autonomia = st.selectbox("Modalità Visita", ["Tutte", "In Autonomia", "In Affiancamento"])
        
        c_f6, c_f7 = st.columns(2)
        f_cng = c_f6.selectbox("C. Net Gain", ["Tutti", "Sì", "No"])
        f_cross = c_f7.selectbox("Cross Selling", ["Tutti", "Sì", "No"])

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
            c_res1.success(f"Trovate {len(df)} visite.")
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
                        st.info("✏️ Modifica Modalità Attiva")
                        st.text_input("Cliente", value=str(row['cliente'] or ""), key=f"e_cli_{row_id}")
                        st.selectbox("Stato", ["Prospect", "Cliente"], index=0 if row['tipo_cliente'] == "Prospect" else 1, key=f"e_tp_{row_id}")
                        
                        c_rt1, c_rt2 = st.columns(2)
                        with c_rt1: st.text_input("Referente", value=str(row.get('referente', '') or ""), key=f"e_ref_{row_id}")
                        with c_rt2: st.text_input("Mail o Telefono", value=str(row.get('telefono', '') or ""), key=f"e_tel_{row_id}")

                        st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], index=["HSE", "BIENNE", "PALAGI", "SARDEGNA"].index(row['agente']) if row['agente'] in ["HSE", "BIENNE", "PALAGI", "SARDEGNA"] else 0, key=f"e_ag_{row_id}")
                        
                        ca1, ca2, ca3 = st.columns(3)
                        with ca1: st.checkbox("🚶‍♂️ Autonomia", value=bool(row.get('visita_autonoma', 0)), key=f"e_aut_{row_id}")
                        with ca2: st.checkbox("🚀 C.N.G.", value=bool(row.get('customer_net_gain', 0)), key=f"e_cng_{row_id}")
                        with ca3: st.checkbox("🔄 Cross S.", value=bool(row.get('operazioni_cross_selling', 0)), key=f"e_cross_{row_id}")
                        
                        st.text_area("Note", value=str(row['note'] or ""), height=150, key=f"e_note_{row_id}")
                        
                        fup_attuale = row['data_followup']
                        if st.checkbox("Imposta Ricontatto", value=True if fup_attuale else False, key=f"e_chk_{row_id}"):
                            st.date_input("Data Ricontatto", value=datetime.strptime(fup_attuale[:10], "%Y-%m-%d").date() if fup_attuale else datetime.today().date(), format="DD/MM/YYYY", key=f"e_dt_{row_id}")

                        cs, cc = st.columns(2)
                        cs.button("💾 SALVA", key=f"save_{row_id}", type="primary", use_container_width=True, on_click=execute_save_modifica, args=(row_id,))
                        cc.button("❌ ANNULLA", key=f"canc_{row_id}", use_container_width=True, on_click=cancel_edit)
                    
                    else:
                        st.write(f"**Agente:** {row['agente']} | **Stato:** {row['tipo_cliente']}")
                        
                        tags = []
                        if row.get('visita_autonoma') == 1: tags.append("🚶‍♂️ Autonomia")
                        if row.get('customer_net_gain') == 1: tags.append("🚀 Net Gain")
                        if row.get('operazioni_cross_selling') == 1: tags.append("🔄 Cross Selling")
                        if tags: st.caption(" | ".join(tags))
                        
                        if row.get('referente') or row.get('telefono'):
                            st.write(f"👤 **{row.get('referente', '')}** 📞 {row.get('telefono', '')}")
                            
                        st.info(f"{row['note']}")
                        st.checkbox("✅ Salvato nel gestionale aziendale", value=(row.get('copiato_crm') == 1), key=f"chk_crm_{row_id}", on_change=toggle_crm_copy, args=(row_id,))

                        if row['data_followup']:
                            fup_str = row['data_followup']
                            dt_fmt = datetime.strptime(fup_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y alle %H:%M") if ":" in fup_str else datetime.strptime(fup_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                            st.write(f"📅 **Ricontattare il:** {dt_fmt}")
                        
                        st.write("")
                        cb_m, cb_d = st.columns(2)
                        cb_m.button("✏️ Modifica", key=f"btn_mod_{row_id}", use_container_width=True, on_click=set_edit_mode, args=(row_id,))
                        cb_d.button("🗑️ Elimina", key=f"btn_del_{row_id}", use_container_width=True, on_click=ask_delete, args=(row_id,))
                        
                        if st.session_state.get(f"confirm_del_{row_id}", False):
                            st.warning("⚠️ Confermi l'eliminazione?")
                            cy, cn = st.columns(2)
                            cy.button("SÌ", key=f"yes_{row_id}", type="primary", use_container_width=True, on_click=execute_delete_visita, args=(row_id,))
                            cn.button("NO", key=f"no_{row_id}", use_container_width=True, on_click=cancel_delete, args=(row_id,))
        else:
            st.warning("Nessun risultato trovato con questi filtri.")

# ==========================================
# TAB 4: SETUP E BACKUP
# ==========================================
with tab_setup:
    st.write("### Sicurezza Dati")
    st.info("Questa sezione serve per scaricare i backup sul tuo telefono o ripristinarli se cambi dispositivo.")
    
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_full.to_excel(writer, index=False)
    st.download_button("📥 ESPORTA TUTTO IN EXCEL", output.getvalue(), "backup_crm_completo.xlsx", type="primary", use_container_width=True)
    
    st.divider()
    st.write("📤 **RIPRISTINA DA UN BACKUP**")
    file_caricato = st.file_uploader("Seleziona file Excel", type=["xlsx"])
    if file_caricato is not None:
        if st.button("⚠️ SOVRASCRIVI TUTTO", type="primary", use_container_width=True):
            try:
                df_ripristino = pd.read_excel(file_caricato)
                if 'cliente' in df_ripristino.columns:
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
                    st.success("✅ Ripristino completato! Aggiornamento in corso...")
                    time.sleep(2)
                    st.rerun()
                else: st.error("❌ File non valido.")
            except Exception as e: st.error(f"Errore: {e}")
                
    st.divider()
    st.write("📂 **STORICO BACKUP AUTOMATICI**")
    cartella_backup = "BACKUPS_AUTOMATICI"
    if os.path.exists(cartella_backup):
        files_backup = sorted([f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')], reverse=True)
        if files_backup:
            file_selezionato = st.selectbox("Seleziona backup giornaliero:", files_backup)
            with open(os.path.join(cartella_backup, file_selezionato), "rb") as f:
                st.download_button(label=f"⬇️ SCARICA", data=f, file_name=file_selezionato, use_container_width=True)
        else: st.caption("Ancora nessun backup automatico.")
    else: st.caption("Cartella backup in attesa del primo salvataggio.")

# Footer Estetico
st.write("") 
st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em; font-weight: bold;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
