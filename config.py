# ShukCar/config.py
import os

# ----- ВАЖНО -----
# Впиши сюда свой токен DaData (чтобы PyCharm видел сразу при запуске main.py)
DADATA_TOKEN = "012eb14e0e42b24dcf1278b6e6d6e3ea4006f193"  # пример: "3cd6b0f5...."
DADATA_SECRET = ""  # обычно не нужен, оставь пустым

# ----- Опционально: прокси -----
# Если у тебя корпоративная сеть/домашний файрвол, можно указать HTTP(S) прокси:
# Пример: "http://user:pass@proxy.company.local:3128"
HTTP_PROXY = os.getenv("HTTP_PROXY", "")
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")
WIPE_SECRET = os.getenv("WIPE_SECRET", "Rbhbkk00798@")  # ← поставь СВОЙ надёжный пароль
