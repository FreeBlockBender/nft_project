from datetime import datetime

def unix_to_yyyy_mm_dd(epoch):
    """
    Converte un timestamp Unix epoch (secondi o millisecondi) in formato YYYY-MM-DD.
    Se epoch è None o non valido, restituisce None.
    """
    if epoch is None:
        return None
    try:
        if epoch > 1e12:
            epoch = epoch / 1000  # ms to s
        return datetime.utcfromtimestamp(int(epoch)).strftime("%Y-%m-%d")
    except Exception:
        return None

def unix_to_hh_mm(epoch):
    """
    Converte un timestamp Unix (secondi o millisecondi) restituendo l'orario "HH:MM" (ora e minuti, a 2 cifre).
    Se il timestamp non è valido o None, restituisce None.
    Adatto per inserimento in campi TEXT di SQLite.
    """
    from datetime import datetime
    if epoch is None:
        return None
    try:
        # Se epoch è in millisecondi, porta a secondi
        if epoch > 1e12:
            epoch = epoch / 1000
        # Usa UTC per uniformità nei dati di archivio
        return datetime.utcfromtimestamp(int(epoch)).strftime("%H:%M")
    except Exception:
        return None

def extract_or_none(data, path, default=None):
    """
    Estrae un valore annidato da un dizionario seguendo la lista di chiavi in `path`.
    Restituisce None (o default) se una delle chiavi non esiste o il valore è falsy.
    Esempio:
        extract_or_none(item, ["stats", "floorInfo", "tokenInfo", "contract"])
        => None se manca uno dei livelli, altrimenti il valore.
    """
    try:
        for p in path:
            data = data.get(p, None)
            if data is None:
                return default
        # Considera empty string e valori "falsy" come None per il DB
        if data in ("", [], {}, ()): 
            return default
        return data
    except Exception:
        return default