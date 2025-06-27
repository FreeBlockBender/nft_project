from typing import List, Tuple
from datetime import datetime, timedelta

def count_days_present(
    date_value_list: List[Tuple[str, float]],
    period: int,
    end_date: str
) -> Tuple[int, int]:
    """
    Conta quanti giorni sono presenti e quanti mancanti negli ultimi {period} giorni da end_date (inclusa).
    Ritorna: (present, missing)
    """
    # Costruisco insieme delle date da trovare
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days_window = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(period)][::-1]
    # Estraggo le date effettivamente presenti, come stringhe
    dates_available = set(d for d, _ in date_value_list)
    present = sum(1 for d in days_window if d in dates_available)
    missing = period - present
    return present, missing

def calculate_sma(
    date_value_list: list,
    period: int,
    end_date: str,
    missing_threshold: int
) -> str:
    """
    Calcola la media mobile semplice (SMA) su un periodo specifico.

    Un giorno viene considerato 'mancante' se:
    - Non esiste una riga per quella data nell'elenco;
    - Oppure, esiste una riga ma il valore è NULL.

    Se i giorni mancanti superano missing_threshold, ritorna "N/A per assenza di giorni".
    Se mancano pochi giorni, esegue interpolazione lineare tra i valori noti più vicini.

    Args:
        date_value_list: elenco di tuple (data as 'YYYY-MM-DD', valore float o None)
        period: numero di giorni della SMA
        end_date: stringa 'YYYY-MM-DD', data finale della finestra
        missing_threshold: massimo numero di giorni interpolabili

    Returns:
        str: valore SMA formattato, oppure "N/A per assenza di giorni"
    """
    from datetime import datetime, timedelta

    # Costruisce la finestra di date
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days_window = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(period)][::-1]
    values_by_date = {d: v for d, v in date_value_list}

    available = []
    missing_indices = []
    for i, d in enumerate(days_window):
        # Caso (a) Non presente nel dict, (b) presente ma valore None/NULL
        if d in values_by_date and values_by_date[d] is not None:
            available.append(values_by_date[d])
        else:
            available.append(None)
            missing_indices.append(i)

    if len(missing_indices) > missing_threshold:
        return "N/A per assenza di giorni"

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
            return "N/A per assenza di giorni"  # Nessun dato interpolabile

    # Calcola la media sui valori (ora tutti not None)
    return f"{sum(available) / period:.4f}"