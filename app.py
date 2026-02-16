import streamlit as st
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation

# --- 1. FUNZIONI DI SUPPORTO ---
def inizializza_db():
    conn = sqlite3.connect('crm_mobile.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS visite 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cliente TEXT, localita TEXT, provincia TEXT,
                  tipo_cliente TEXT, data TEXT, note TEXT,
                  data_followup TEXT, data_ordine TEXT, agente TEXT,
                  latitudine TEXT, longitudine TEXT)''')
    conn.commit()
    conn.close()

# Callback per evitare errori GPS
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
    cliente = s.get('cliente_key', '')
    note = s.get('note_key', '')
    
    if cliente.strip() != "" and note.strip() != "":
        conn = sqlite3.connect('crm_mobile.db')
        c = conn.cursor()
        
        # Date per il salvataggio
        data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
        data_ord = s.data_key.strftime("%Y-%m-%d")
        
        # --- LOGICA FOLLOW UP INTELLIGENTE ---
        scelta = s.get('fup_opt', 'No')
        data_fup = ""
        
        if scelta == "7 gg":
            data_scadenza = s.data_key + timedelta(days=7)
            data_fup = data_scadenza.strftime("%Y-%m-%d")
        elif scelta == "30 gg":
            data_scadenza = s.data_key + timedelta(days=30)
            data_fup = data_scadenza.strftime("%Y-%m-%d")
        # ----------------------------------------

        lat = s.get('lat_val', "")
        lon = s.get('lon_val', "")
        
        c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                     data_followup, data_ordine, agente, latitudine, longitudine) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cliente, s.localita_key.upper(), s.prov_key.upper(), s.tipo_key, data_visita_fmt, note, data_fup, data_ord, s.agente_key, lat, lon))
        conn.commit()
        conn.close()
        
        # Reset
        s.cliente_key = ""; s.localita_key = ""; s.prov_key = ""; s.note_key = ""
        s.lat_val = ""; s.lon_val = ""; s.fup_opt = "No" 
        if 'gps_temp' in s: del s['gps_temp']
        
        st.toast("✅ Visita salvata!")
        st.rerun() 
    else:
        st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 2. INTERFACCIA ---
# Modificato il titolo della pagina nel browser
st.set_page_config(page_title="CRM Michelone", page_icon="💼", layout="centered")
inizializza_db()

# Modificato il titolo principale dell'App
st.title("💼 CRM Michelone")

# --- MODULO INSERIMENTO (Parte CHIUSO) ---
with st.expander("➕ REGISTRA NUOVA VISITA", expanded=False):
    st.text_input("Nome Cliente", key="cliente_key")
    st.radio("Stato", ["Cliente", "Potenziale (Prospect)"], key="tipo_key", horizontal=True)
    
    st.markdown("---")

    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)

    # GPS Logic
    loc_data = get_geolocation()
    if loc_data:
        if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
            try:
                lat = loc_data['coords']['latitude']
                lon = loc_data['coords']['longitude']
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", 
                                 headers={'User-Agent': 'CRM_Michelone'}).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', a.get('state', ''))
                if "Roma" in prov_full or "Rome" in prov_full: prov_sigla = "RM"
                else: prov_sigla = prov_full[:2].upper()
                
                st.session_state['gps_temp'] = {
                    'citta': citta.upper() if citta else "",
                    'prov': prov_sigla,
                    'lat': str(lat),
                    'lon': str(lon)
                }
            except: st.warning("Indirizzo non trovato.")

        if 'gps_temp' in st.session_state:
            dati = st.session_state['gps_temp']
            st.info(f"🛰️ Trovato: **{dati['citta']} ({dati['prov']})**")
            c_yes, c_no = st.columns(2)
            with c_yes: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
            with c_no: 
                if st.button("❌ ANNULLA", use_container_width=True):
                    del st.session_state['gps_temp']; st.rerun()

    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["HSE", "BIENNE", "PALAGI", "SARDEGNA"], key="agente_key")
    
    st.text_area("Note", key="note_key", height=150)
    
    # Selezione Follow Up
    st.write("📅 **Pianifica Ricontatto (dalla data visita):**")
    st.radio("Scadenza", ["No", "7 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- SEZIONE AUTOMATICA SCADENZE (ALERT) ---
conn = sqlite3.connect('crm_mobile.db')
oggi = datetime.now().strftime("%Y-%m-%d")
df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)
conn.close()

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
        
        try:
            data_scad = datetime.strptime(row['data_followup'], "%Y-%m-%d")
            data_oggi_dt = datetime.strptime(oggi, "%Y-%m-%d")
            giorni_ritardo = (data_oggi_dt - data_scad).days
            msg_ritardo = "Scaduto OGGI" if giorni_ritardo == 0 else f"Scaduto da {giorni_ritardo} gg"
        except:
            msg_ritardo = "Scaduto"

        with st.container():
            col_txt, col_btn = st.columns([4, 1])
            with col_txt:
                st.markdown(f"**{icon} {row['cliente']}** - {row['localita']}")
                st.caption(f"📅 **{msg_ritardo}** | Note: {row['note']}")
            with col_btn:
                if st.button("✅", key=f"fatto_{row['id']}", help="Segna come fatto"):
                    conn = sqlite3.connect('crm_mobile.db')
                    c = conn.cursor()
                    c.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.rerun()
    st.divider()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3 = st.columns([1.5, 1, 1])
with f1: t_ricerca = st.text_input("Cerca...")
with f2: periodo = st.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
with f3: f_agente = st.selectbox("Agente", ["Seleziona...", "Tutti", "HSE", "BIENNE", "PALAGI", "SARDEGNA"])

if t_ricerca.strip() != "" or f_agente != "Seleziona...":
    conn = sqlite3.connect('crm_mobile.db')
    df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    conn.close()

    if t_ricerca:
        df = df[df.apply(lambda row: t_ricerca.lower() in str(row).lower(), axis=1)]
    if isinstance(periodo, list) and len(periodo) == 2:
        df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]
    if f_agente not in ["Tutti", "Seleziona..."]:
        df = df[df['agente'] == f_agente]

    if not df.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.drop(columns=['data_ordine', 'id']).to_excel(writer, index=False, sheet_name='Visite')
        st.download_button("📊 SCARICA EXCEL", output.getvalue(), "report.xlsx", use_container_width=True)

        for _, row in df.iterrows():
            icon = "🤝" if row['tipo_cliente'] == "Cliente" else "🚀"
            with st.expander(f"{icon} {row['agente']} | {row['data']} - {row['cliente']}"):
                st.write(f"**📍 Città:** {row['localita']} ({row['provincia']})")
                st.write(f"**📝 Note:** {row['note']}")
                if row['latitudine']:
                    link = f"https://www.google.com/maps/search/?api=1&query={row['latitudine']},{row['longitudine']}"
                    st.markdown(f"[📍 Mappa]({link})")
                
                # --- TASTO ELIMINA CON SICUREZZA ---
                col_del_btn, col_del_confirm = st.columns([1, 4])
                
                if st.button("🗑️ Elimina", key=f"pre_del_{row['id']}"):
                    st.session_state[f"confirm_del_{row['id']}"] = True
                
                if st.session_state.get(f"confirm_del_{row['id']}", False):
                    st.error("⚠️ Sei sicuro di voler eliminare questa visita?")
                    c_yes, c_no = st.columns(2)
                    with c_yes:
                        if st.button("SÌ, ELIMINA", key=f"yes_del_{row['id']}", use_container_width=True):
                            conn = sqlite3.connect('crm_mobile.db')
                            c = conn.cursor()
                            c.execute("DELETE FROM visite WHERE id = ?", (row['id'],))
                            conn.commit()
                            conn.close()
                            st.session_state[f"confirm_del_{row['id']}"] = False
                            st.rerun()
                    with c_no:
                        if st.button("NO, ANNULLA", key=f"no_del_{row['id']}", use_container_width=True):
                            st.session_state[f"confirm_del_{row['id']}"] = False
                            st.rerun()
    else:
        st.info("Nessuna visita trovata.")
else:

    st.caption("Usa i filtri per cercare.")

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

class CRMApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Michelone CRM - Gestione Clienti")
        self.root.geometry("1000x700")
        self.root.configure(bg="#f0f0f0")

        # --- CONFIGURAZIONE LAYOUT ---
        # Barra laterale (Sidebar)
        self.sidebar = tk.Frame(self.root, bg="#2c3e50", width=250)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Area Principale
        self.main_content = tk.Frame(self.root, bg="white")
        self.main_content.pack(side="right", expand=True, fill="both")

        # --- INSERIMENTO LOGO ---
        self.carica_logo()

        # --- ELEMENTI SIDEBAR ---
        self.crea_menu_sidebar()

        # --- BENVENUTO ---
        self.mostra_dashboard()

    def carica_logo(self):
        try:
            # Apriamo il file caricato
            img_originale = Image.open("logo.jpg")
            
            # Ridimensioniamo il logo per adattarlo alla sidebar (es. 180x180 pixel)
            img_resized = img_originale.resize((180, 180), Image.Resampling.LANCZOS)
            
            # Convertiamo per Tkinter
            self.logo_image = ImageTk.PhotoImage(img_resized)
            
            # Label per mostrare il logo
            self.label_logo = tk.Label(self.sidebar, image=self.logo_image, bg="#2c3e50")
            self.label_logo.pack(pady=20)
            
        except Exception as e:
            print(f"Errore caricamento logo: {e}")
            tk.Label(self.sidebar, text="Logo non trovato", fg="white", bg="#2c3e50").pack(pady=20)

    def crea_menu_sidebar(self):
        # Stile bottoni
        style = ttk.Style()
        style.configure("Menu.TButton", font=("Arial", 12), padding=10)

        pulsanti = ["Dashboard", "Anagrafica Clienti", "Fatturazione", "Impostazioni"]
        for testo in pulsanti:
            btn = tk.Button(self.sidebar, text=testo, bg="#34495e", fg="white", 
                            font=("Arial", 11, "bold"), bd=0, cursor="hand2",
                            activebackground="#1abc9c", activeforeground="white")
            btn.pack(fill="x", padx=10, pady=5)

    def mostra_dashboard(self):
        # Titolo nell'area principale
        lbl_titolo = tk.Label(self.main_content, text="Benvenuto nel tuo CRM", 
                              font=("Arial", 24, "bold"), bg="white", fg="#2c3e50")
        lbl_titolo.pack(pady=40)
        
        lbl_info = tk.Label(self.main_content, text="Il sistema è sincronizzato e 'Michelone Approved'!", 
                            font=("Arial", 14), bg="white", fg="#7f8c8d")
        lbl_info.pack(pady=10)

        # Esempio di tabella dati
        columns = ("id", "nome", "stato")
        tree = ttk.Treeview(self.main_content, columns=columns, show="headings")
        tree.heading("id", text="ID")
        tree.heading("nome", text="Nome Cliente")
        tree.heading("stato", text="Stato Pagamento")
        
        # Dati di esempio
        tree.insert("", "end", values=("001", "Mario Rossi", "Pagato"))
        tree.insert("", "end", values=("002", "Luigi Bianchi", "In attesa"))
        
        tree.pack(pady=20, padx=20, fill="x")

if __name__ == "__main__":
    root = tk.Tk()
    app = CRMApp(root)
    root.mainloop()
