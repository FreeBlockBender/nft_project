from typing import List, Tuple
from datetime import datetime, timedelta
import numpy as np

def count_days_present(
    date_value_list: List[Tuple[str, float]],
    period: int,
    end_date: str
) -> Tuple[int, int]:
    """
    Conta quanti giorni sono presenti e quanti mancanti negli ultimi {period} giorni da end_date (inclusa).
    Ritorna: (present, missing)
    """
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days_window = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(period)][::-1]
    dates_available = set(d for d, _ in date_value_list)
    present = sum(1 for d in days_window if d in dates_available)
    missing = period - present
    return present, missing

def calculate_sma(
    date_value_list: list,
    period: int,
    end_date: str,
    missing_threshold: int
) -> float:
    """
    Calcola la media mobile semplice (SMA) su un periodo specifico.

    Un giorno viene considerato 'mancante' se:
    - Non esiste una riga per quella data nell'elenco;
    - Oppure, esiste una riga ma il valore è NULL.

    Se i giorni mancanti superano missing_threshold, ritorna np.nan.
    Se mancano pochi giorni, esegue interpolazione lineare tra i valori noti più vicini.

    Args:
        date_value_list: elenco di tuple (data as 'YYYY-MM-DD', valore float o None)
        period: numero di giorni della SMA
        end_date: stringa 'YYYY-MM-DD', data finale della finestra
        missing_threshold: massimo numero di giorni interpolabili

    Returns:
        float: valore SMA, oppure np.nan se non calcolabile
    """
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days_window = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(period)][::-1]
    values_by_date = {d: v for d, v in date_value_list}

    available = []
    missing_indices = []
    for i, d in enumerate(days_window):
        if d in values_by_date and values_by_date[d] is not None:
            available.append(values_by_date[d])
        else:
            available.append(None)
            missing_indices.append(i)

    if len(missing_indices) > missing_threshold:
        return np.nan

    # Interpolazione lineare dei buchi interni/estremi
    for idx in missing_indices:
        prev = next((available[i] for i in range(idx - 1, -1, -1) if available[i] is not None), None)
        nextv = next((available[i] for i in range(idx + 1, len(available)) if available[i] is not None), None)
        if prev is not None and nextv is not None:
            available[idx] = (prev + nextv) / 2
        elif prev is not None:
            available[idx] = prev
        elif nextv is not None:
            available[idx] = nextv
        else:
            return np.nan  # Nessun dato interpolabile

    # Calcola la media sui valori (ora tutti not None)
    return sum(available) / period if available else np.nan