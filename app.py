import streamlit as st
import pandas as pd
import requests
from io import BytesIO
import os
import tempfile
from fpdf import FPDF
from datetime import datetime

# Configurazione della pagina
st.set_page_config(page_title="Generatore Preventivi", layout="wide", page_icon="📄")

# --- TRUCCHETTO CSS PER CAMPO E BOTTONI VERDI ---
st.markdown("""
<style>
/* Sfondo verde chiaro per i campi di testo */
div[data-testid="stTextInput"] input {
    background-color: #e8f5e9 !important; 
    border: 2px solid #4CAF50 !important; 
    color: #000000 !important;
    font-weight: bold;
}
/* Colore verde per i bottoni "Primari" (Aggiungi, Prepara PDF, Scarica) */
button[kind="primary"] {
    background-color: #4CAF50 !important;
    color: white !important;
    border: none !important;
}
button[kind="primary"]:hover {
    background-color: #45a049 !important;
}
</style>
""", unsafe_allow_html=True)

# --- INIZIALIZZAZIONE DELLA MEMORIA ---
if 'carrello' not in st.session_state:
    st.session_state['carrello'] = []

if 'espositori_selezionati' not in st.session_state:
    st.session_state['espositori_selezionati'] = []

# --- CARICAMENTO DATI ---
@st.cache_data
def carica_dati(path, tipo="base"):
    if not os.path.exists(path):
        return None
    try:
        data = pd.read_excel(path)
        if tipo == "atg":
            # MODIFICA FATTA QUI: Ora legge 6 colonne (fino alla F) e assegna l'ultima all'IMMAGINE
            data = data.iloc[:, :6]
            # Assicurati che l'Excel abbia 6 colonne per l'ATG: le prime 5 classiche + la 6^ con il link
            data.columns = ['ARTICOLO', 'RIVESTIMENTO', 'QTA_BOX', 'RANGE_TAGLIE', 'LISTINO', 'IMMAGINE']
        else:
            data.columns = [str(c).strip().upper() for c in data.columns]
        return data
    except Exception as e:
        st.error(f"Errore nel caricamento del file {path}: {e}")
        return None

df_base = carica_dati('Listino_agente.xlsx', "base")
df_atg = carica_dati('Listino_ATG.xlsx', "atg")

# =========================================================
# --- SIDEBAR: DATI CLIENTE, SCONTI, NOTE E ESPOSITORI ---
# =========================================================
st.sidebar.header("📋 Dati Documento")
nome_cliente = st.sidebar.text_input("Nome del Cliente:", placeholder="Ragione Sociale...")
nome_referente = st.sidebar.text_input("Nome Referente:", placeholder="Mario Rossi...")

st.sidebar.divider()

# Sconti Base
st.sidebar.header("💰 Sconto Base")
col_sc1, col_sc2, col_sc3 = st.sidebar.columns(3)
sc1 = col_sc1.number_input("Sc. 1 %", 0.0, 100.0, 40.0, key="sc_base1")
sc2 = col_sc2.number_input("Sc. 2 %", 0.0, 100.0, 10.0, key="sc_base2")
sc3 = col_sc3.number_input("Sc. 3 %", 0.0, 100.0, 0.0, key="sc_base3")

st.sidebar.divider()

# Sconti ATG
st.sidebar.header("🧤 Sconto ATG")
col_atg1, col_atg2, col_atg3 = st.sidebar.columns(3)
sc_atg1 = col_atg1.number_input("Sc. ATG 1 %", 0.0, 100.0, 40.0, key="sc_atg1")
sc_atg2 = col_atg2.number_input("Sc. ATG 2 %", 0.0, 100.0, 10.0, key="sc_atg2")
sc_atg3 = col_atg3.number_input("Sc. ATG 3 %", 0.0, 100.0, 0.0, key="sc_atg3")

st.sidebar.divider()

# --- SEZIONE SIDEBAR: PULSANTI ESPOSITORI MULTIPLI ---
st.sidebar.header("🎁 Espositori Omaggio")
st.sidebar.write("Clicca per aggiungere gli espositori al PDF:")

col_esp1, col_esp2 = st.sidebar.columns(2)
col_esp3, col_esp4 = st.sidebar.columns(2)

def seleziona_espositore(nome_file_img):
    if nome_file_img not in st.session_state['espositori_selezionati']:
        st.session_state['espositori_selezionati'].append(nome_file_img)
        st.toast(f"Aggiunto: {nome_file_img.replace('.jpg','')}", icon="✅")
    else:
        st.toast("Espositore già aggiunto!", icon="⚠️")

with col_esp1:
    if st.button("ATG Banco", use_container_width=True):
        seleziona_espositore("ATG banco.jpg")
with col_esp2:
    if st.button("ATG Terra", use_container_width=True):
        seleziona_espositore("ATG terra.jpg")
with col_esp3:
    if st.button("Base Banco", use_container_width=True):
        seleziona_espositore("Base banco.jpg")
with col_esp4:
    if st.button("Base Terra", use_container_width=True):
        seleziona_espositore("BASE terra.jpg")

if st.session_state['espositori_selezionati']:
    st.sidebar.markdown("**Espositori inclusi nel preventivo:**")
    
    nomi_belli = {
        "ATG banco.jpg": "Espositore ATG girevole da Banco",
        "ATG terra.jpg": "Espositore ATG in Metallo da Terra",
        "Base banco.jpg": "Espositore BASE da Banco 1 Modello",
        "BASE terra.jpg": "Espositore BASE da terra 7 modelli"
    }
    
    for esp in st.session_state['espositori_selezionati']:
        st.sidebar.success(f"✅ {nomi_belli.get(esp, esp)}")
        
    if st.sidebar.button("❌ Rimuovi Tutti gli Espositori"):
        st.session_state['espositori_selezionati'] = []
        st.rerun()

st.sidebar.divider()

# --- CAMPI: CONDIZIONI COMMERCIALI CON VALORI DI DEFAULT ---
st.sidebar.header("⚖️ Condizioni Commerciali")
campo_pagamento = st.sidebar.text_input("Pagamento:", value="Ri.Ba. 60 giorni")
campo_trasporto = st.sidebar.text_input("Trasporto:", value="P.to Franco")
campo_validita = st.sidebar.text_input("Validità Offerta:", value="30.06.2026")

st.sidebar.divider()

note_preventivo = st.sidebar.text_area("📝 Note Aggiuntive (verranno inserite a fine PDF):", height=200, placeholder="Scrivi qui le tue note...")

# =========================================================
# --- PAGINA PRINCIPALE: RICERCA UNIFICATA ---
# =========================================================
st.title("📄 OFFERTE & ORDINI")

if df_base is None and df_atg is None:
    st.warning("⚠️ Nessun file Excel trovato. Assicurati che i file 'Listino_agente.xlsx' e 'Listino_ATG.xlsx' siano nella cartella.")
else:
    st.markdown("### 🟢 :green[Ricerca Articolo]")
    ricerca = st.text_input("Inserisci nome modello:", placeholder="Cerca su tutto il catalogo (Base o ATG)...").upper()

    if ricerca:
        # Prepariamo una lista dove metteremo tutti i risultati trovati
        risultati_trovati = []
        
        # Cerchiamo nel listino base
        if df_base is not None:
            r_base = df_base[df_base['ARTICOLO'].astype(str).str.upper().str.contains(ricerca, na=False)].copy()
            if not r_base.empty:
                r_base['CATALOGO_PROVENIENZA'] = "Listino Base"
                risultati_trovati.append(r_base)
                
        # Cerchiamo nel listino ATG
        if df_atg is not None:
            r_atg = df_atg[df_atg['ARTICOLO'].astype(str).str.upper().str.contains(ricerca, na=False)].copy()
            if not r_atg.empty:
                r_atg['CATALOGO_PROVENIENZA'] = "Listino ATG"
                risultati_trovati.append(r_atg)
        
        # Se abbiamo trovato qualcosa uniamo i risultati
        if risultati_trovati:
            risultato_completo = pd.concat(risultati_trovati, ignore_index=True)
            
            scelta = st.selectbox("Seleziona l'articolo:", risultato_completo['ARTICOLO'].unique())
            d = risultato_completo[risultato_completo['ARTICOLO'] == scelta].iloc[0]
            
            catalogo_selezionato = d['CATALOGO_PROVENIENZA']
            
            # --- NOVITÀ: RECUPERO LA NORMATIVA DALLA COLONNA 8 (INDICE 7) DEL LISTINO BASE ---
            normativa_articolo = ""
            if catalogo_selezionato == "Listino Base" and len(d) >= 8:
                valore_normativa = str(d.iloc[7]).strip()
                if valore_normativa.lower() != "nan" and valore_normativa != "":
                    normativa_articolo = valore_normativa
            
            # Applichiamo sconti e taglie in base al catalogo di provenienza
            if catalogo_selezionato == "Listino Base":
                sconto_applicato = (sc1, sc2, sc3)
                taglie_disponibili = list(range(35, 51))
            else:
                sconto_applicato = (sc_atg1, sc_atg2, sc_atg3)
                taglie_disponibili = [6, 7, 8, 9, 10, 11, 12]
            
            st.divider()
            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.subheader(f"Modello: {d['ARTICOLO']}")
                st.caption(f"📍 Trovato in: **{catalogo_selezionato}**") 
                
                # Mostra la normativa a schermo se esiste
                if normativa_articolo:
                    st.caption(f"⚖️ **Normativa:** {normativa_articolo}")
                
                if catalogo_selezionato == "Listino ATG":
                    st.caption(f"**Rivestimento:** {d.get('RIVESTIMENTO', '-')} | **Q.tà Box:** {d.get('QTA_BOX', '-')} | **Range Taglie:** {d.get('RANGE_TAGLIE', '-')}")
                
                prezzo_listino = float(d['LISTINO'])
                s1, s2, s3 = sconto_applicato
                prezzo_netto = prezzo_listino * (1 - s1/100) * (1 - s2/100) * (1 - s3/100)
                st.markdown(f"### Prezzo Netto: :green[{prezzo_netto:.2f} €]")
                
                st.divider()
                
                modalita = st.radio(
                    "Scegli la modalità di inserimento:", 
                    ["Specifica Taglie", "Solo Modello/Vetrina (Senza taglie)"], 
                    horizontal=True,
                    key="mod_inserimento"
                )
                
                st.write("")
                
                if modalita == "Specifica Taglie":
                    st.write("**Quantità per Taglia:**")
                    
                    if st.button("🔄 Azzera Campi"):
                        for t in taglie_disponibili:
                            st.session_state[f"qta_{t}_{catalogo_selezionato}"] = 0
                        st.rerun()

                    quantita_taglie = {}
                    
                    for i in range(0, len(taglie_disponibili), 8):
                        chunk = taglie_disponibili[i:i+8]
                        cols = st.columns(8)
                        for j, t in enumerate(chunk):
                            with cols[j]:
                                key = f"qta_{t}_{catalogo_selezionato}"
                                if key not in st.session_state: st.session_state[key] = 0
                                quantita_taglie[t] = st.number_input(str(t), min_value=0, step=1, key=key)

                    st.write("")
                    if st.button("🛒 Aggiungi al Preventivo", use_container_width=True, type="primary"):
                        aggiunti = 0
                        for t, q in quantita_taglie.items():
                            if q > 0:
                                st.session_state['carrello'].append({
                                    "Articolo": d['ARTICOLO'], "Taglia": t, "Quantità": q,
                                    "Netto U.": f"{prezzo_netto:.2f} €", "Totale Riga": prezzo_netto * q,
                                    "Immagine": str(d.get('IMMAGINE', '')).strip(),
                                    "Normativa": normativa_articolo # Salviamo la normativa nel carrello
                                })
                                aggiunti += 1
                        if aggiunti > 0: 
                            st.success("Aggiunto con successo!")
                            st.rerun()
                        else: 
                            st.warning("Inserisci almeno una quantità!")
                
                else:
                    st.info("💡 In questa modalità puoi inserire l'articolo senza specificare le taglie.")
                    qta_generica = st.number_input("Quantità generica totale:", min_value=0, step=1, value=0, key="qta_gen")
                    
                    if st.button("🛒 Aggiungi Modello", use_container_width=True, type="primary"):
                        st.session_state['carrello'].append({
                            "Articolo": d['ARTICOLO'], 
                            "Taglia": "-", 
                            "Quantità": qta_generica,
                            "Netto U.": f"{prezzo_netto:.2f} €", 
                            "Totale Riga": prezzo_netto * qta_generica,
                            "Immagine": str(d.get('IMMAGINE', '')).strip(),
                            "Normativa": normativa_articolo # Salviamo la normativa nel carrello
                        })
                        st.success("Modello aggiunto al preventivo!")
                        st.rerun()
                    
            with c2:
                url = str(d.get('IMMAGINE', '')).strip()
                # Se c'è un link (sia per Base che per ATG) prova a caricarlo
                if url.startswith('http'):
                    try:
                        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                        if r.status_code == 200:
                            st.image(BytesIO(r.content), caption=d['ARTICOLO'], use_container_width=True)
                        else:
                            st.warning("Immagine non trovata (Errore dal sito).")
                    except Exception: 
                        st.warning("Impossibile caricare l'immagine dal link fornito.")
                # Se non c'è link ed è ATG, mostra il messaggio di default
                elif catalogo_selezionato == "Listino ATG":
                    st.markdown("### 🧤 **Prodotto ATG**")
                    st.write("*(Nessuna immagine nel listino per questo articolo)*")
                else:
                    st.write("Immagine non disponibile")
        else:
            st.warning("Nessun articolo trovato con questo nome. Riprova con una parola diversa!")

# =========================================================
# --- RIEPILOGO E PDF ---
# =========================================================
if st.session_state['carrello']:
    st.divider()
    st.header("🛒 Riepilogo")
    df_c = pd.DataFrame(st.session_state['carrello'])
    
    st.table(df_c[["Articolo", "Taglia", "Quantità", "Netto U.", "Totale Riga"]])
    
    totale_generale = df_c["Totale Riga"].sum()
    st.markdown(f"### Totale Generale: **{totale_generale:.2f} €**")
    
    c_p1, c_p2 = st.columns(2)
    with c_p1:
        if st.button("🗑️ Svuota Tutto", use_container_width=True):
            st.session_state['carrello'] = []
            st.rerun()
            
    with c_p2:
        if st.button("📄 Prepara PDF per il Download", use_container_width=True, type="primary"):
            raggruppo = {}
            for r in st.session_state['carrello']:
                art = r["Articolo"]
                if art not in raggruppo:
                    # Passiamo anche la normativa al PDF
                    raggruppo[art] = {
                        "T": [], 
                        "Tot": 0, 
                        "Img": r["Immagine"], 
                        "Netto": r["Netto U."],
                        "Normativa": r.get("Normativa", "")
                    }
                
                if r["Quantità"] > 0:
                    if r["Taglia"] == "-":
                        raggruppo[art]["T"].append(f"Q.tà: {r['Quantità']}pz")
                    else:
                        raggruppo[art]["T"].append(f"Tg{r['Taglia']}: {r['Quantità']}pz")
                
                raggruppo[art]["Tot"] += r["Totale Riga"]

            class PDF(FPDF):
                def header(self):
                    # Logo
                    for f in ["logo.png", "logo.jpg", "logo.jpeg"]:
                        if os.path.exists(f):
                            self.image(f, 10, 8, 60)
                            break
                            
                    # Spett.le
                    self.set_font("helvetica", "", 12)
                    self.set_xy(100, 15)
                    self.cell(100, 6, "Spett.le", align="R", ln=1)
                    
                    # Nome Cliente
                    self.set_font("helvetica", "B", 20) 
                    self.set_x(100) 
                    testo_nome = nome_cliente if nome_cliente else "Cliente"
                    self.cell(100, 8, testo_nome, align="R", ln=1)
                    
                    # Nome Referente
                    if nome_referente:
                        self.set_font("helvetica", "", 15) 
                        self.set_x(100)
                        self.cell(100, 7, f"c.a. {nome_referente}", align="R", ln=1)
                    
                    self.ln(20) 

            pdf = PDF()
            pdf.add_page()
            
            # --- CICLO PRODOTTI ---
            for art, dati in raggruppo.items():
                y_inizio = pdf.get_y()
                if y_inizio > 230:
                    pdf.add_page()
                    y_inizio = pdf.get_y()

                pdf.set_xy(10, y_inizio)
                pdf.set_font("helvetica", "B", 12)
                pdf.cell(135, 7, f"Modello: {art}", ln=1)
                
                # --- NOVITÀ: STAMPA DELLA NORMATIVA SOTTO IL NOME MODELLO ---
                if dati.get("Normativa"):
                    pdf.set_font("helvetica", "I", 9) # Font in corsivo, un po' più piccolo
                    pdf.cell(135, 5, f"Normativa: {dati['Normativa']}", ln=1)
                
                pdf.set_font("helvetica", "", 10)
                pdf.cell(135, 6, f"Prezzo Netto: {dati['Netto'].replace('€', 'Euro')}", ln=1)
                
                if dati["T"]:
                    pdf.set_font("helvetica", "I", 9)
                    pdf.multi_cell(135, 5, " | ".join(dati["T"]))
                else:
                    pdf.set_font("helvetica", "I", 9)
                    pdf.cell(135, 5, "Proposta Modello (Nessuna quantità specificata)", ln=1)
                
                pdf.ln(2) 
                
                if dati['Tot'] > 0:
                    pdf.set_x(10) 
                    pdf.set_font("helvetica", "B", 10)
                    pdf.cell(135, 6, f"Subtotale: {dati['Tot']:.2f} Euro", ln=1)
                
                y_fine_testo = pdf.get_y()

                foto_inserita = False
                y_fine_immagine = y_inizio + 10 
                
                if dati["Img"].startswith("http"):
                    try:
                        res = requests.get(dati["Img"], headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                        if res.status_code == 200:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                                tmp.write(res.content)
                                pdf.image(tmp.name, x=155, y=y_inizio, w=35)
                            os.remove(tmp.name)
                            foto_inserita = True
                            y_fine_immagine = y_inizio + 35 
                    except: 
                        pass
                
                if not foto_inserita:
                    pdf.set_xy(155, y_inizio + 10)
                    pdf.set_font("helvetica", "I", 9)
                    pdf.set_text_color(150, 150, 150)
                    pdf.cell(35, 10, "Foto non disponibile", align="C")
                    pdf.set_text_color(0, 0, 0)
                    y_fine_immagine = y_inizio + 20
                
                y_fine_blocco = max(y_fine_testo, y_fine_immagine)
                pdf.set_y(y_fine_blocco + 5)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(5)

            # --- TOTALE GENERALE ---
            pdf.ln(5)
            if totale_generale > 0:
                pdf.set_font("helvetica", "B", 14)
                pdf.cell(0, 10, f"TOTALE GENERALE: {totale_generale:.2f} Euro", align="R")
                pdf.ln(10)

            # --- ESPOSITORI ---
            if st.session_state['espositori_selezionati']:
                pdf.ln(5)
                nomi_espositori_pdf = {
                    "ATG banco.jpg": "Espositore ATG girevole da Banco",
                    "ATG terra.jpg": "Espositore ATG in Metallo da Terra",
                    "Base banco.jpg": "Espositore BASE da Banco 1 Modello",
                    "BASE terra.jpg": "Espositore BASE da terra 7 modelli"
                }

                for esp_file in st.session_state['espositori_selezionati']:
                    if pdf.get_y() > 220: 
                        pdf.add_page()
                    
                    current_y_esp = pdf.get_y()
                    descrizione_espositore = nomi_espositori_pdf.get(esp_file, esp_file.replace('.jpg', '').upper())

                    if os.path.exists(esp_file):
                        pdf.image(esp_file, x=10, y=current_y_esp, w=35)
                    else:
                        pdf.set_xy(10, current_y_esp)
                        pdf.set_font("helvetica", "I", 10)
                        pdf.set_text_color(200,0,0)
                        pdf.cell(35, 10, f"Foto Mancante", ln=1)
                        pdf.set_text_color(0,0,0)

                    pdf.set_xy(50, current_y_esp + 10) 
                    pdf.set_font("helvetica", "B", 14)
                    pdf.set_text_color(0, 100, 0) 
                    testo_omaggio = f"Modello: {descrizione_espositore}\nEspositore in OMAGGIO con questo ordine!"
                    pdf.multi_cell(0, 7, testo_omaggio)
                    pdf.set_text_color(0, 0, 0) 
                    pdf.set_y(current_y_esp + 45) 

            # --- NOTE ---
            if note_preventivo.strip():
                pdf.ln(5)
                pdf.set_font("helvetica", "B", 14) 
                pdf.cell(0, 8, "Note:")
                pdf.ln(8)
                pdf.set_font("helvetica", "", 13) 
                testo_note = note_preventivo.replace('€', 'Euro')
                pdf.multi_cell(0, 6, testo_note)
            
            # --- PAGAMENTO, TRASPORTO, VALIDITA' E PREZZI SULLA STESSA RIGA ---
            pdf.ln(6) 
            h_c = 6
            
            if campo_pagamento.strip():
                pdf.set_font("helvetica", "B", 10)
                pdf.cell(pdf.get_string_width("Pagamento: ") + 2, h_c, "Pagamento:", ln=0)
                pdf.set_font("helvetica", "", 10)
                pdf.cell(pdf.get_string_width(campo_pagamento) + 6, h_c, campo_pagamento, ln=0)

            if campo_trasporto.strip():
                pdf.set_font("helvetica", "B", 10)
                pdf.cell(pdf.get_string_width("Trasporto: ") + 2, h_c, "Trasporto:", ln=0)
                pdf.set_font("helvetica", "", 10)
                pdf.cell(pdf.get_string_width(campo_trasporto) + 6, h_c, campo_trasporto, ln=0)
            
            if campo_validita.strip():
                pdf.set_font("helvetica", "B", 10)
                pdf.cell(pdf.get_string_width("Validità: ") + 2, h_c, "Validità:", ln=0)
                pdf.set_font("helvetica", "", 10)
                pdf.cell(pdf.get_string_width(campo_validita) + 6, h_c, campo_validita, ln=0)
                
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(pdf.get_string_width("Prezzi: ") + 2, h_c, "Prezzi:", ln=0)
            pdf.set_font("helvetica", "", 10)
            pdf.cell(0, h_c, "netti iva esclusa", ln=1)

            # --- FIRMA ---
            pdf.ln(10)
            pdf.set_font("helvetica", "I", 11)
            pdf.cell(0, 6, "Michele Cavallo - Area Manager | Base Protection srl", align="R", ln=1)
            pdf.cell(0, 6, "Tel. 389.0199088", align="R", ln=1)

            pdf_out = pdf.output()
            
            if isinstance(pdf_out, str):
                pdf_bytes = pdf_out.encode('latin-1')
            else:
                pdf_bytes = bytes(pdf_out)
            
            data_oggi = datetime.now().strftime("%d.%m.%Y")
            nome_sicuro = "".join(x for x in nome_cliente if x.isalnum() or x in " -_").strip()
            nome_sicuro = nome_sicuro.replace(" ", "_") if nome_sicuro else "Cliente"
            nome_file_dinamico = f"{nome_sicuro}_{data_oggi}.pdf"
            
            st.divider()
            st.success("✅ PDF pronto per essere scaricato!")
            
            st.download_button(
                label=f"⬇️ Clicca qui per Salvare '{nome_file_dinamico}'",
                data=pdf_bytes,
                file_name=nome_file_dinamico,
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
