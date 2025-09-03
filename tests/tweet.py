import tweepy

# Credenziali X
API_KEY = "1Swt1hyrw17mLRsUOxgd2S2m2"
API_SECRET_KEY = "VuxyjKZYRA1HretOOZtgroev9xfQ3HqJp45gV7rLOcqMSN9tBN"
ACCESS_TOKEN = "1485619485201604609-fKwvzg4VeabYxJKZmqsPK6FIDYDuGO"
ACCESS_TOKEN_SECRET = "QEQGcY9LS61eCvskX9erMhBMIfdhPhIHds8TnJydau1fT"

try:
    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET_KEY,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
    user = client.get_me()
    print(f"Autenticazione riuscita! Account: {user.data.username}")
except tweepy.TweepyException as e:
    print(f"Errore di autenticazione: {e}")