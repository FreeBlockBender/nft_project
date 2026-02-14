# 🎨 NFT Social Hype - Guida Configurazione

## Panoramica

Il **NFT Social Hype** è un nuovo modulo che misura il "sentiment" e il "vibe" generale del mercato NFT usando l'API di Grok (xAI). Analizza il sentiment della comunità e fornisce score di hype in tempo reale.

### Cosa è Grok?

Grok è un'intelligenza artificiale avanzata creata da xAI che può analizzare i trend attuali del mercato. È basato su accesso real-time a X (Twitter) e altri fonti di dati.

---

## Configurazione

### 1. Ottenere la API Key di Grok

1. Vai a [https://console.x.ai/](https://console.x.ai/)
2. Accedi con il tuo account X (Twitter)
3. Crea una nuova API Key
4. Copia la chiave

### 2. Configurare il File .env

Aggiungi queste variabili al tuo file `.env`:

```bash
# Grok API Configuration
GROK_API_KEY=xai-xxxxxxxxxxxxx
GROK_API_ENDPOINT=https://api.x.ai/v1
```

### 3. Inizializzare il Database

Se è la prima volta, assicurati che il database sia initializzato:

```bash
python scripts/create_database.py
```

Questo creerà la tabella `nft_social_hype` automaticamente.

---

## Utilizzo

### Via Telegram Bot

#### Comando 1: `/vibes`
Mostra i dati di social hype più recenti:
```
/vibes
```

Risposta:
```
🎨 NFT Market Vibes (2026-02-14)

🚀 Hype Score: 72/100
🟢 Sentiment: POSITIVE
📈 Trend: UP

🏷️ Keywords: NFT Renaissance, Layer 2 Adoption, Creator Economy

📝 Summary:
Il mercato NFT mostra sentimenti positivi con aumento di attività nei Layer 2...

🕐 Updated: 2026-02-14T15:30:00
```

#### Comando 2: `/import_vibes`
Genera nuovi dati di sentiment usando Grok:
```
/import_vibes
```

Questo comando:
1. Chiama l'API di Grok
2. Analizza il sentimento attuale del mercato NFT
3. Salva i risultati nel database
4. Mostra il risultato all'utente

### Via Terminal (Script)

#### Importare i dati:
```bash
python scripts/import_social_hype.py
```

Questo script:
- Esegue Grok
- Salva il sentiment nel database
- Invia una notifica al chat di monitoring Telegram

#### Visualizzare i dati:
```bash
python scripts/view_social_hype.py
```

Output:
```
======================================================================
📊 NFT SOCIAL HYPE - DATI RECENTI
======================================================================

[1] Date: 2026-02-14
    Hype Score: 72/100 🚀
    Sentiment: POSITIVE
    Trend: UP
    Keywords: NFT Renaissance, Layer 2 Adoption, Creator Economy
    Summary: Il mercato NFT mostra sentimenti positivi...
    Updated: 2026-02-14T15:30:00
----------------------------------------------------------------------
```

---

## Schema del Database

### Tabella: nft_social_hype

```sql
CREATE TABLE nft_social_hype (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT UNIQUE,                          -- Data della misurazione (YYYY-MM-DD)
    timestamp TEXT,                            -- Timestamp ISO preciso
    hype_score INTEGER,                        -- Score 0-100 (0=basso, 100=massimo)
    sentiment TEXT,                            -- POSITIVE | NEUTRAL | NEGATIVE
    trend TEXT,                                -- UP | STABLE | DOWN
    keywords TEXT,                             -- Parole chiave principali (comma-separated)
    summary TEXT,                              -- Riassunto del sentiment (<200 chars)
    raw_response TEXT,                         -- JSON completo da Grok (per debugging)
    created_at TEXT                            -- Timestamp creazione record
);
```

### Colonne Spiegate

| Colonna | Tipo | Descrizione |
|---------|------|-------------|
| `date` | TEXT | Data giornaliera (UNIQUE - 1 record per giorno) |
| `hype_score` | INTEGER | 0-100: misura l'intensità del hype nel mercato |
| `sentiment` | TEXT | POSITIVE (bullish), NEUTRAL, NEGATIVE (bearish) |
| `trend` | TEXT | UP (migliora), STABLE (stabile), DOWN (peggiora) |
| `keywords` | TEXT | Topic principali del sentiment (es: "Layer 2, Creator Economy") |
| `summary` | TEXT | Riassunto breve e significativo |
| `raw_response` | TEXT | JSON completo per debugging e analisi avanzata |

---

## Interpretazione dei Dati

### Hype Score
- **75-100**: 🚀 Entusiasmo massimo - Mercato molto bullish
- **50-74**: 📊 Fiducia moderata - Interesse crescente
- **25-49**: ❄️ Cauzione - Sentiment misto o depresso
- **0-24**: 🔴 Pessimismo - Mercato in fase bearish

### Sentiment
- **POSITIVE** 🟢: Comunità bullish, ottimismo alto
- **NEUTRAL** 🟡: Attesa, risolutezza, balanced sentiment  
- **NEGATIVE** 🔴: Pessimismo, preoccupazioni, bearish mood

### Trend
- **UP** 📈: Sentiment sta migliorando
- **STABLE** ➡️: Nessun cambiamento significativo
- **DOWN** 📉: Sentiment sta peggiorando

---

## Funzionamento Interno

### Flow di Analisi

```
1. Utente esegue /import_vibes
   ↓
2. Si chiama l'API di Grok con un prompt specializzato
   ↓
3. Grok analizza:
   - Sentiment della comunità crypto su X
   - Trend recenti nel mercato NFT
   - Notizie e discussioni su blockchain
   - Attività nelle principali piattaforme NFT
   ↓
4. Grok restituisce JSON con:
   - hype_score (0-100)
   - sentiment (POSITIVE/NEUTRAL/NEGATIVE)
   - trend (UP/STABLE/DOWN)
   - keywords
   - summary
   ↓
5. I dati vengono salvati nel database
   ↓
6. Notifica inviata al chat Telegram
```

### Prompt di Grok

Il modello Grok riceve questo prompt:

```
Analizza il sentimento attuale del mercato NFT globale basandoti su:
1. Tendenze recenti del mercato NFT
2. Sentiment della comunità crypto
3. Attività in piattaforme NFT major (OpenSea, Magic Eden, etc.)
4. Notizie recenti su blockchain e NFT
5. Atteggiamento dei creator e degli investitori

Fornisci risposta in JSON con:
{
    "hype_score": 0-100,
    "sentiment": "POSITIVE|NEUTRAL|NEGATIVE",
    "trend": "UP|STABLE|DOWN",
    "keywords": "3-5 parole chiave",
    "summary": "<200 caratteri>",
    "reasoning": "breve spiegazione"
}
```

---

## Troubleshooting

### Errore: "GROK_API_KEY non configurato"
**Soluzione:** Aggiungi `GROK_API_KEY` al file `.env`
```bash
GROK_API_KEY=xai-xxxxxxxxxxxxx
```

### Errore: "Impossibile trovare JSON nella risposta"
**Causa:** Grok ha restituito un formato non valido
**Soluzione:** 
- Verifica che la API Key sia valida
- Controlla la connessione internet
- Prova di nuovo manualmente: `/import_vibes`

### I dati non si salvano nel database
**Cause possibili:**
- Il database non è inizializzato
- Mancanza di permessi di scrittura

**Soluzione:**
```bash
python scripts/create_database.py
python scripts/verify_database.py
```

---

## Integrazioni Future

Con questa tabella puoi:

1. **Correzione Prezzo**: Usare hype_score come signal per MA crossing
2. **Filtri Golden Cross**: Ignorare segnali quando sentiment è eccessivamente negativo
3. **Ranking**: Penalizzare collezioni quando mercato è in bearish
4. **Allerte**: Notificare quando sentiment cambia drasticamente
5. **Correlazione**: Analizzare correlazione tra hype_score e volume/floor price

---

## Utilità e Valore

- **Real-time Market Pulse**: Comprendi le vibes istantanee del mercato
- **Risk Indicator**: Usa hype_score per validare i segnali di trading
- **Community Sentiment**: Vedi cosa ne pensa la comunità crypto
- **Trend Prediction**: Anticipa i movimenti di prezzo
- **Data-Driven Decisions**: Basi le decisioni su sentiment analizzato dall'AI

---

## Per Sviluppatori

### Importare il modulo nei tuoi script:

```python
from app.data_import.import_social_hype import get_nft_market_sentiment, save_social_hype_to_db

sentiment_data = get_nft_market_sentiment()
if sentiment_data:
    save_social_hype_to_db(sentiment_data)
    print(f"Hype Score: {sentiment_data['hype_score']}")
```

### Interrogare il database:

```python
from app.database.db_connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM nft_social_hype ORDER BY date DESC LIMIT 5")
for row in cursor.fetchall():
    print(row)
conn.close()
```

---

**Creato:** Febbraio 2026  
**Modulo:** app.data_import.import_social_hype, app/telegram/commands/vibes.py
