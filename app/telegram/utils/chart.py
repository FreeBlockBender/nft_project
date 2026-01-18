# app/telegram/utils/chart.py

import os
import io
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from datetime import datetime
from app.telegram.utils.telegram_query import get_collection_chart_data
from app.golden_cross.moving_average import calculate_sma

def create_nft_chart(slug: str, data: list, field: str, chain: str, days: int, chain_currency_symbol: str = None):
    """
    Genera un grafico dei floor price e delle medie mobili per una collezione NFT.
    
    Args:
        slug (str): Slug della collezione NFT.
        data (list): Lista di tuple (data, floor_price) dalla tabella historical_nft_data.
        field (str): Campo da plottare ('floor_native' o 'floor_usd').
        chain (str): Chain della collezione (per il titolo e l'etichetta).
        days (int): Numero di giorni da visualizzare.
        chain_currency_symbol (str, optional): Simbolo della valuta nativa della chain (es. ETH, BNB).
    
    Returns:
        BytesIO: Buffer contenente l'immagine del grafico in formato PNG.
    """
    if not data:
        return None
    
    # Estrai date e valori, convertendo None o non numerici in np.nan
    dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
    values = []
    for row in data:
        value = row[1]
        if value is None or not (isinstance(value, (int, float)) or str(value).replace('.', '').replace('-', '').isdigit()):
            values.append(np.nan)
        else:
            values.append(float(value))
    
    if all(np.isnan(values)):
        return None
    
    # Crea una serie temporale continua
    date_nums = np.array([d.timestamp() for d in dates])
    value_nums = np.array(values, dtype=np.float64)
    date_min = min(dates)
    date_max = max(dates)
    date_range = np.linspace(date_min.timestamp(), date_max.timestamp(), max(10, len(dates)))
    interp_func = interp1d(date_nums, value_nums, kind='linear', fill_value="extrapolate")
    interp_values = interp_func(date_range)
    interp_dates = [datetime.fromtimestamp(ts) for ts in date_range]
    
    # Definisci le medie mobili in base al numero di giorni
    date_value_list = [(d.strftime("%Y-%m-%d"), v) for d, v in zip(dates, values)]
    end_date = date_max.strftime("%Y-%m-%d")
    periods = []
    if days >= 7:  # 7 days or more: show floor price
        pass  # Floor price is always shown
    if days >= 30:  # 1 month
        periods.append((20, 1, "SMA20"))
    if days >= 90:  # 3 months
        periods.append((50, 3, "SMA50"))
    if days >= 180:  # 6 months or 1 year
        periods.extend([(100, 5, "SMA100"), (200, 10, "SMA200")])
    
    sma_data = {}
    for period, threshold, label in periods:
        sma_values = []
        for i in range(len(interp_dates)):
            window_end = interp_dates[i].strftime("%Y-%m-%d")
            sma = calculate_sma(date_value_list, period, window_end, missing_threshold=threshold)
            sma_values.append(sma if not np.isnan(sma) else np.nan)
        sma_nums = np.array(sma_values)
        sma_interp = interp1d(np.arange(len(sma_nums)), sma_nums, kind='linear', fill_value="extrapolate")
        sma_data[label] = sma_interp(np.linspace(0, len(sma_nums)-1, len(interp_dates)))
        print(f"{label} values: {sma_values[:10]}...")  # Debug
    
    # Imposta uno stile crypto-friendly con tema dark e floor price in blu
    plt.style.use('dark_background')  # Tema scuro
    plt.figure(figsize=(12, 6), facecolor='#1E1E1E')  # Sfondo nero
    ax = plt.gca()
    ax.set_facecolor('#2B2B2B')  # Sfondo dell'asse
    
    # Plot del floor price in blu
    plt.plot(interp_dates, interp_values, label=f"Floor Price ({field})", color="#3B82F6", linewidth=2, marker='o', markersize=4)
    
    # Plot delle medie mobili come linee continue
    colors = {"SMA20": "#F97316", "SMA50": "#34D399", "SMA100": "#F87171", "SMA200": "#A855F7"}
    for label, sma_values in sma_data.items():
        plt.plot(interp_dates, sma_values, label=label, color=colors[label], linewidth=1.5)
    
    # Personalizza gli assi e la griglia
    plt.title(f"📈 Floor Price and Moving Averages for {slug} ({chain}) - {days} days", color="white")
    plt.xlabel("Date", color="white")
    # Usa chain_currency_symbol per nft_chart_native, altrimenti USD
    y_label = f"Floor Price ({chain_currency_symbol if field == 'floor_native' and chain_currency_symbol else chain.upper() if field == 'floor_native' else 'USD'})"
    plt.ylabel(y_label, color="white")
    plt.grid(True, color="#4B5563", linestyle='--', alpha=0.5)  # Griglia leggera
    plt.xticks(rotation=45, color="white")
    plt.yticks(color="white")
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1), frameon=False, facecolor='#2B2B2B', edgecolor='#2B2B2B', labelcolor='white')
    
    # Ottimizza il layout
    plt.tight_layout()
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", bbox_inches="tight", facecolor='#1E1E1E')
    buffer.seek(0)
    plt.close()
    return buffer