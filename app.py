import streamlit as st
import sqlite3
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from io import BytesIO

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")

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
        
        # --- MIGRAZIONI AUTOMATICHE PER VECCHI DATABASE ---
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

# --- FUNZIONE CALCOLO GIORNI ---
def calcola_prossimo_giorno(data_partenza, giorno_obiettivo):
    # 0 = Lunedì, 4 = Venerdì
    giorni_mancanti = giorno_obiettivo - data_partenza.weekday()
    if giorni_mancanti <= 0:
        giorni_mancanti += 7
    return (data_partenza + timedelta(days=giorni_mancanti)).strftime("%Y-%m-%d")

# --- 2. FUNZIONI DI SUPPORTO E CALLBACKS ---
def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup):
        os.makedirs(cartella_backup)
    
    now = datetime.now()
    if now.hour >= 7:
        today_str = now.strftime('%Y-%m-%d')
        backup_di_oggi_esiste = False
        
        for file in os.listdir(cartella_backup):
            if file.endswith('.xlsx') and today_str in file:
                backup_di_oggi_esiste = True
                break
                
        if not backup_di_oggi_esiste:
            with sqlite3.connect('crm_mobile.db') as conn:
                try:
                    df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
                    if not df.empty:
                        for file in os.listdir(cartella_backup):
                            if file.endswith('.xlsx'):
                                os.remove(os.path.join(cartella_backup, file))
                                
                        nome_file = f"Backup_Auto_{today_str}.xlsx"
                        df.to_excel(os.path.join(cartella_backup, nome_file), index=False)
                        st.toast(f"🛡️ Backup Giornaliero ({today_str}) Eseguito!", icon="✅")
                except:
                    pass

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
                giorni = int(scelta.split()[0])
                data_fup = (s.data_key + timedelta(days=giorni)).strftime("%Y-%m-%d")
            elif scelta == "Alle 17:00":
                now = datetime.now()
                if now.hour >= 17:
                    data_fup = (now + timedelta(days=1)).strftime("%Y-%m-%d") + " 17:00"
                else:
                    data_fup = now.strftime("%Y-%m-%d") + " 17:00"
            elif scelta == "Prox. Lunedì":
                data_fup = calcola_prossimo_giorno(s.data_key, 0)
            elif scelta == "Prox. Venerdì":
                data_fup = calcola_prossimo_giorno(s.data_key, 4)
            
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                                 data_followup, data_ordine, agente, latitudine, longitudine, copiato_crm,
                                 referente, telefono, visita_autonoma, customer_net_gain, operazioni_cross_selling) 
                                 VALUES (?, '', '', ?, ?, ?, ?, ?, ?, '', '', 0, ?, ?, ?, ?, ?)""", 
                      (cliente, tipo, data_visita_fmt, note, data_fup, data_ord, 
                       s.agente_key, referente, telefono, autonomia, cng, cross))
            conn.commit()
        
        # Reset dei campi
        st.session_state.cliente_key = ""
        st.session_state.note_key = ""
        st.session_state.referente_key = ""
        st.session_state.telefono_key = ""
        st.session_state.fup_opt = "No"
        st.session_state.autonomia_key = False
        st.session_state.cng_key = False
        st.session_state.cross_key = False
        
        st.toast("✅ Visita salvata!", icon="💾")
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- CALLBACKS PER I PULSANTI IN ARCHIVIO E SCADENZE ---
def posticipa_fup(id_val):
    giorni = st.session_state.get('temp_giorni', 0)
    nuova_data = (datetime.now() + timedelta(days=giorni)).strftime("%Y-%m-%d")
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova_data, id_val))
        conn.commit()

def set_fup_prox(id_val, giorno_settimana):
    nuova_data = calcola_prossimo_giorno(datetime.now(), giorno_settimana)
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova_data, id_val))
        conn.commit()

def set_fup_alle_1700(id_val):
    now = datetime.now()
    if now.hour >= 17:
        nuova_data = (now + timedelta(days=1)).strftime("%Y-%m-%d") + " 17:00"
    else:
        nuova_data = now.strftime("%Y-%m-%d") + " 17:00"
        
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", (nuova_data, id_val))
        conn.commit()

def azzera_fup(id_val):
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (id_val,))
        conn.commit()

def set_edit_mode(id_val): st.session_state.edit_mode_id = id_val
def cancel_edit(): st.session_state.edit_mode_id = None
def ask_delete(id_val): st.session_state[f"confirm_del_{id_val}"] = True
def cancel_delete(id_val): st.session_state[f"confirm_del_{id_val}"] = False

def execute_save_modifica(id_val):
    s = st.session_state
    new_cli = s.get(f"e_cli_{id_val}", "")
    new_tipo = s.get(f"e_tp_{id_val}", "Prospect")
    new_note = s.get(f"e_note_{id_val}", "")
    new_ag = s.get(f"e_ag_{id_val}", "HSE")
    new_ref = s.get(f"e_ref_{id_val}", "")
    new_tel = s.get(f"e_tel_{id_val}", "")
    new_aut = 1 if s.get(f"e_aut_{id_val}", False) else 0
    new_cng = 1 if s.get(f"e_cng_{id_val}", False) else 0
    new_cross = 1 if s.get(f"e_cross_{id_val}", False) else 0
    
    new_fup = ""
    if s.get(f"e_chk_{id_val}", False):
        dt = s.get(f"e_dt_{id_val}")
        if dt: new_fup = dt.strftime("%Y-%m-%d")
        
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("""UPDATE visite SET cliente=?, tipo_cliente=?, note=?, agente=?, data_followup=?, referente=?, telefono=?, visita_autonoma=?, customer_net_gain=?, operazioni_cross_selling=? WHERE id=?""",
                     (new_cli, new_tipo, new_note, new_ag, new_fup, new_ref, new_tel, new_aut, new_cng, new_cross, id_val))
        conn.commit()
    st.session_state.edit_mode_id = None

def execute_delete_visita(id_val):
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("DELETE FROM visite WHERE id = ?", (id_val,))
        conn.commit()
    st.session_state[f"confirm_del_{id_val}"] = False

def toggle_crm_copy(id_val):
    new_val = 1 if st.session_state.get(f"chk_crm_{id_val}", False) else 0
    with sqlite3.connect('crm_mobile.db') as conn:
        conn.execute("UPDATE visite SET copiato_crm = ? WHERE id = ?", (new_val, id_val))
        conn.commit()


# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelone")

with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False): 
    st.text_input("Nome Cliente", key="cliente_key")
    st.selectbox("Tipo Cliente", ["Cliente", "Prospect"], key="tipo_key")
    
    col_ref, col_tel = st.columns(2)
    with col_ref: st.text_input("Referente", key="referente_key")
    with col_tel: st.text_input("Mail o Telefono", key="telefono_key")
    
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    # Aggiunto format="DD/MM/YYYY" per la visualizzazione italiana
    with c1: st.date_input("Data", datetime.now(), format="DD/MM/YYYY", key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.write("")
    ck1, ck2, ck3 = st.columns(3)
    with ck1: st.checkbox("🚶‍♂️ In Autonomia", key="autonomia_key")
    with ck2: st.checkbox("🚀 C. Net Gain", key="cng_key")
    with ck3: st.checkbox("🔄 Cross Selling", key="cross_key")
    
    st.text_area("Note", key="note_key", height=250)
    
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "Alle 17:00", "1 gg", "7 gg", "15 gg", "30 gg", "Prox. Lunedì", "Prox. Venerdì"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    oggi_limite = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi_limite}' ORDER BY data_followup ASC", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        try:
            row_id = int(float(row['id']))
        except (ValueError, TypeError):
            continue

        try:
            d_scad = datetime.strptime(row['data_followup'][:10], "%Y-%m-%d")
            d_oggi = datetime.strptime(oggi, "%Y-%m-%d")
            giorni_ritardo = (d_oggi - d_scad).days
            msg_scadenza = "Scade OGGI" if giorni_ritardo <= 0 else f"Scaduto da {giorni_ritardo} gg"
            
            if len(row['data_followup']) > 10:
                orario_presente = row['data_followup'][11:]
                msg_scadenza += f" alle {orario_presente}"
        except: msg_scadenza = "Scaduto"

        with st.container(border=True):
            tipo_label = f"({row['tipo_cliente']})" if row['tipo_cliente'] else ""
            st.markdown(f"**{row['cliente']}** {tipo_label}")
            st.caption(f"📅 {msg_scadenza} | Note: {row['note']}")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("+1 ☀️", key=f"p1_{row_id}", use_container_width=True):
                    st.session_state.temp_giorni = 1
                    posticipa_fup(row_id)
                    st.rerun()
            with c2:
                if st.button("+7 📅", key=f"p7_{row_id}", use_container_width=True):
                    st.session_state.temp_giorni = 7
                    posticipa_fup(row_id)
                    st.rerun()
            with c3:
                if st.button("+15 📅", key=f"p15_{row_id}", use_container_width=True):
                    st.session_state.temp_giorni = 15
                    posticipa_fup(row_id)
                    st.rerun()
            with c4:
                st.button("✅ Fatto", key=f"ok_{row_id}", type="primary", use_container_width=True, on_click=azzera_fup, args=(row_id,))
                    
            c5, c6, c7 = st.columns(3)
            with c5:
                st.button("🕔 Alle 17:00", key=f"o1700_{row_id}", use_container_width=True, on_click=set_fup_alle_1700, args=(row_id,))
            with c6:
                st.button("➡️ P. Lunedì", key=f"pl_{row_id}", use_container_width=True, on_click=set_fup_prox, args=(row_id, 0))
            with c7:
                st.button("➡️ P. Venerdì", key=f"pv_{row_id}", use_container_width=True, on_click=set_fup_prox, args=(row_id, 4))

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")

f1, f2 = st.columns([1.5, 1])
t_ricerca = f1.text_input("Cerca Cliente o Note") 
oggi_dt = datetime.today().date()
# Aggiunto format="DD/MM/YYYY" al filtro periodo
periodo = f2.date_input("Periodo", [oggi_dt - timedelta(days=60), oggi_dt], format="DD/MM/YYYY")

with st.expander("⚙️ Filtri Avanzati"):
    c_f1, c_f2, c_f3 = st.columns(3)
    f_agente = c_f1.selectbox("Agente", ["Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])
    f_tipo = c_f2.selectbox("Tipo", ["Tutti", "Prospect", "Cliente"])
    f_stato_crm = c_f3.selectbox("Stato CRM", ["Tutti", "Da Caricare", "Caricati"])
    
    st.write("")
    c_f4, c_f5 = st.columns(2)
    f_referente = c_f4.selectbox("Referente", ["Tutti", "Con Referente", "Senza Referente"])
    f_autonomia = c_f5.selectbox("Autonomia", ["Tutte", "In Autonomia", "In Affiancamento"])
    
    c_f6, c_f7 = st.columns(2)
    f_cng = c_f6.selectbox("Customer Net Gain", ["Tutti", "Sì", "No"])
    f_cross = c_f7.selectbox("Cross Selling", ["Tutti", "Sì", "No"])

if st.button("🔎 CERCA VISITE", use_container_width=True):
    st.session_state.ricerca_attiva = True
    st.session_state.edit_mode_id = None 

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    
    if t_ricerca:
        df = df[df['cliente'].str.contains(t_ricerca, case=False, na=False) | 
                df['note'].str.contains(t_ricerca, case=False, na=False)]
    if f_agente != "Tutti":
        df = df[df['agente'] == f_agente]
    if f_tipo != "Tutti":
        df = df[df['tipo_cliente'] == f_tipo]
    if f_stato_crm == "Da Caricare":
        df = df[(df['copiato_crm'] == 0) | (df['copiato_crm'].isnull())]
    elif f_stato_crm == "Caricati":
        df = df[df['copiato_crm'] == 1]
    if f_referente == "Con Referente":
        df = df[(df['referente'].notnull()) & (df['referente'].str.strip() != '')]
    elif f_referente == "Senza Referente":
        df = df[(df['referente'].isnull()) | (df['referente'].str.strip() == '')]
    if f_autonomia == "In Autonomia":
        df = df[df['visita_autonoma'] == 1]
    elif f_autonomia == "In Affiancamento":
        df = df[(df['visita_autonoma'] == 0) | (df['visita_autonoma'].isnull())]
    if f_cng == "Sì":
        df = df[df['customer_net_gain'] == 1]
    elif f_cng == "No":
        df = df[(df['customer_net_gain'] == 0) | (df['customer_net_gain'].isnull())]
    if f_cross == "Sì":
        df = df[df['operazioni_cross_selling'] == 1]
    elif f_cross == "No":
        df = df[(df['operazioni_cross_selling'] == 0) | (df['operazioni_cross_selling'].isnull())]

    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
         df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        if st.button("❌ Chiudi Ricerca"):
            st.session_state.ricerca_attiva = False
            st.rerun()

        for _, row in df.iterrows():
            try:
                row_id = int(float(row['id']))
            except (ValueError, TypeError):
                continue
                
            icona_crm = "✅" if row.get('copiato_crm') == 1 else ""
            badge_tipo = f"[{row['tipo_cliente']}]" if row['tipo_cliente'] else ""
            
            key_conf = f"confirm_del_{row_id}"
            tendina_aperta = (st.session_state.edit_mode_id == row_id) or st.session_state.get(key_conf, False)
            
            with st.expander(f"{icona_crm} {row['data']} - {row['cliente']} {badge_tipo}", expanded=tendina_aperta):
                
                # --- MODALITÀ MODIFICA (ARCHIVIO) ---
                if st.session_state.edit_mode_id == row_id:
                    st.info("✏️ Modifica Dati")
                    st.text_input("Cliente", value=str(row['cliente'] or ""), key=f"e_cli_{row_id}")
                    
                    lista_tp = ["Prospect", "Cliente"]
                    try: idx_tp = lista_tp.index(row['tipo_cliente'])
                    except: idx_tp = 0
                    st.selectbox("Stato", lista_tp, index=idx_tp, key=f"e_tp_{row_id}")

                    c_rt1, c_rt2 = st.columns(2)
                    with c_rt1: st.text_input("Referente", value=str(row.get('referente', '') or ""), key=f"e_ref_{row_id}")
                    with c_rt2: st.text_input("Mail o Telefono", value=str(row.get('telefono', '') or ""), key=f"e_tel_{row_id}")

                    st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], index=["HSE", "BIENNE", "PALAGI", "SARDEGNA"].index(row['agente']) if row['agente'] in ["HSE", "BIENNE", "PALAGI", "SARDEGNA"] else 0, key=f"e_ag_{row_id}")
                    
                    st.write("Dettagli:")
                    ca1, ca2, ca3 = st.columns(3)
                    with ca1: st.checkbox("🚶‍♂️ In Autonomia", value=bool(row.get('visita_autonoma', 0)), key=f"e_aut_{row_id}")
                    with ca2: st.checkbox("🚀 C. Net Gain", value=bool(row.get('customer_net_gain', 0)), key=f"e_cng_{row_id}")
                    with ca3: st.checkbox("🔄 Cross Selling", value=bool(row.get('operazioni_cross_selling', 0)), key=f"e_cross_{row_id}")
                    
                    st.text_area("Note", value=str(row['note'] or ""), height=250, key=f"e_note_{row_id}")
                    
                    fup_attuale = row['data_followup']
                    val_ini = datetime.strptime(fup_attuale[:10], "%Y-%m-%d").date() if fup_attuale else datetime.today().date()
                    attiva_fup = st.checkbox("Imposta Ricontatto", value=True if fup_attuale else False, key=f"e_chk_{row_id}")
                    if attiva_fup:
                        # Aggiunto format="DD/MM/YYYY" alla data di modifica ricontatto
                        st.date_input("Nuova Data Ricontatto", value=val_ini, format="DD/MM/YYYY", key=f"e_dt_{row_id}")

                    cs, cc = st.columns(2)
                    cs.button("💾 SALVA", key=f"save_{row_id}", type="primary", use_container_width=True, on_click=execute_save_modifica, args=(row_id,))
                    cc.button("❌ ANNULLA", key=f"canc_{row_id}", use_container_width=True, on_click=cancel_edit)
                
                # --- MODALITÀ VISUALIZZAZIONE (ARCHIVIO) ---
                else:
                    aut_text = "🚶‍♂️ In Autonomia" if row.get('visita_autonoma') == 1 else "🤝 In Affiancamento"
                    cng_text = " | 🚀 C. Net Gain" if row.get('customer_net_gain') == 1 else ""
                    cross_text = " | 🔄 Cross Selling" if row.get('operazioni_cross_selling') == 1 else ""
                    
                    st.write(f"**Stato:** {row['tipo_cliente']} | **Agente:** {row['agente']} | {aut_text}{cng_text}{cross_text}")
                    
                    ref_val = row.get('referente', '')
                    tel_val = row.get('telefono', '')
                    if ref_val or tel_val:
                        st.write(f"👤 **Referente:** {ref_val} | 📞 **Mail/Tel:** {tel_val}")
                        
                    st.text_area("Note:", value=str(row['note'] or ""), height=250, key=f"v_note_{row_id}")
                    
                    is_copied = True if row.get('copiato_crm') == 1 else False
                    st.checkbox("✅ Salvato su CRM", value=is_copied, key=f"chk_crm_{row_id}", on_change=toggle_crm_copy, args=(row_id,))

                    if row['data_followup']:
                        try:
                            fup_str = row['data_followup']
                            if ":" in fup_str:
                                data_fup_it = datetime.strptime(fup_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y alle %H:%M")
                            else:
                                data_fup_it = datetime.strptime(fup_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                            st.write(f"📅 **Ricontatto:** {data_fup_it}")
                        except: pass
                    
                    cb_m, cb_d = st.columns([1, 1])
                    cb_m.button("✏️ Modifica", key=f"btn_mod_{row_id}", on_click=set_edit_mode, args=(row_id,))
                    cb_d.button("🗑️ Elimina", key=f"btn_del_{row_id}", on_click=ask_delete, args=(row_id,))
                    
                    # --- CONFERMA ELIMINAZIONE ---
                    if st.session_state.get(key_conf, False):
                        st.warning("⚠️ Confermi l'eliminazione definitiva?")
                        cy, cn = st.columns(2)
                        cy.button("SÌ, ELIMINA", key=f"yes_{row_id}", type="primary", on_click=execute_delete_visita, args=(row_id,))
                        cn.button("ANNULLA", key=f"no_{row_id}", on_click=cancel_delete, args=(row_id,))
    else:
        st.warning("Nessun risultato trovato.")

# --- GESTIONE DATI E RIPRISTINO SICURO ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE E BACKUP"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    
    st.download_button("📥 SCARICA DATABASE (EXCEL)", output.getvalue(), "backup_crm.xlsx", use_container_width=True)
    
    st.markdown("---")
    st.write("📤 **RIPRISTINO DATI**")
    st.caption("Carica un backup Excel. ATTENZIONE: i dati attuali verranno sostituiti!")
    file_caricato = st.file_uploader("Seleziona il file Excel di backup", type=["xlsx"])
    
    if file_caricato is not None:
        if st.button("⚠️ AVVIA RIPRISTINO (Sovrascrive tutto)", type="primary", use_container_width=True):
            try:
                df_ripristino = pd.read_excel(file_caricato)
                if 'cliente' in df_ripristino.columns:
                    with sqlite3.connect('crm_mobile.db') as conn:
                        c = conn.cursor()
                        c.execute("DROP TABLE IF EXISTS visite")
                        conn.commit()
                        
                        c.execute('''CREATE TABLE visite 
                                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                      cliente TEXT, localita TEXT, provincia TEXT,
                                      tipo_cliente TEXT, data TEXT, note TEXT,
                                      data_followup TEXT, data_ordine TEXT, agente TEXT,
                                      latitudine TEXT, longitudine TEXT, copiato_crm INTEGER DEFAULT 0,
                                      referente TEXT, telefono TEXT, visita_autonoma INTEGER DEFAULT 0,
                                      customer_net_gain INTEGER DEFAULT 0,
                                      operazioni_cross_selling INTEGER DEFAULT 0)''')
                        conn.commit()
                        
                        df_ripristino.to_sql('visite', conn, if_exists='append', index=False)
                        
                    st.success("✅ Database ripristinato correttamente! Riavvio...")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("❌ Il file non sembra un backup valido del CRM.")
            except Exception as e:
                st.error(f"Errore durante il ripristino: {e}")
                
    st.markdown("---")
    st.write("📂 **BACKUP AUTOMATICI (Dal Server)**")
    
    cartella_backup = "BACKUPS_AUTOMATICI"
    if os.path.exists(cartella_backup):
        files_backup = [f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')]
        if files_backup:
            files_backup.sort(reverse=True)
            file_selezionato = st.selectbox("Seleziona il backup automatico (Ne viene salvato solo uno!):", files_backup)
            
            with open(os.path.join(cartella_backup, file_selezionato), "rb") as f:
                st.download_button(
                    label=f"⬇️ SCARICA {file_selezionato}",
                    data=f,
                    file_name=file_selezionato,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        else:
            st.info("Nessun backup automatico generato finora.")
    else:
        st.info("La cartella dei backup verrà creata al primo salvataggio.")

# --- LOGO FINALE ---
st.write("") 
st.divider() 

col_f1, col_f2, col_f3 = st.columns([1, 2, 1]) 

with col_f2:
    try:
        st.image("logo.jpg", use_container_width=True)
        st.markdown("<p style='text-align: center; color: grey; font-size: 0.8em; font-weight: bold;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
    except Exception:
        st.info("✅ Michelone Approved")
