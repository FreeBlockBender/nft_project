# app/telegram/utils/chart.py

import os
import io
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

from app.telegram.utils.telegram_query import get_collection_chart_data

def create_nft_chart(slug, days=30, mode="native"):
    """
    Genera un grafico dei prezzi di una collezione NFT (native o USD).
    Salva il grafico in una cartella charts/ e restituisce dict con status e filepath.
    
    :param slug: lo slug della collezione NFT
    :param days: quanti giorni visualizzare (intero)
    :param mode: 'native' oppure 'usd'
    :return: dict: { 'status': 'success'|'error', 'filepath': path } oppure { 'status': 'error', 'reason': ... }
    """
    try:
        # Recupera i dati dal database: la funzione deve restituire lista di tuple (date, price)
        chart_data = get_collection_chart_data(slug, days, price_mode=mode)
        if not chart_data or len(chart_data) < 2:
            return {"status": "error", "reason": "Dati insufficienti per generare il grafico."}
        
        # Parsing dati
        dates = [r[0] for r in chart_data]
        prices = [float(r[1]) for r in chart_data]

        # Graficazione con matplotlib
        fig, ax = plt.subplots()
        ax.plot(dates, prices, marker='o', linestyle='-')
        ax.set_title(f'Prezzo {"Native" if mode == "native" else "USD"} - {slug}')
        ax.set_xlabel('Data')
        ax.set_ylabel('Prezzo')
        ax.grid(True)
        fig.autofmt_xdate()

        charts_dir = os.path.join(os.path.dirname(__file__), '../../../charts')
        os.makedirs(charts_dir, exist_ok=True)
        filename = f"chart_{slug}_{mode}_{days}d.png"
        filepath = os.path.abspath(os.path.join(charts_dir, filename))
        plt.savefig(filepath)
        plt.close(fig)

        return {"status": "success", "filepath": filepath}
    except Exception as e:
        return {"status": "error", "reason": str(e)}