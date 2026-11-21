"""Descobre o TELEGRAM_CHAT_ID depois que voce manda uma mensagem para o bot.

Uso:  python3 src/descobrir_chat.py
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config


def main():
    if not config.telegram_token:
        print("Falta TELEGRAM_TOKEN no .env.")
        print("Fale com @BotFather no Telegram, mande /newbot e cole o token la.")
        sys.exit(1)

    url = "https://api.telegram.org/bot%s/getUpdates" % config.telegram_token
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            dados = json.loads(r.read().decode())
    except Exception as e:
        print("Nao consegui falar com o Telegram: %s" % e)
        sys.exit(1)

    if not dados.get("ok"):
        print("Token recusado pelo Telegram. Confira o TELEGRAM_TOKEN.")
        sys.exit(1)

    chats = {}
    for u in dados.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            nome = chat.get("title") or " ".join(
                filter(None, [chat.get("first_name"), chat.get("last_name")])) or "?"
            chats[chat["id"]] = (nome, chat.get("type"))

    if not chats:
        print("Nenhuma mensagem encontrada.")
        print("Abra o Telegram, mande qualquer mensagem para o seu bot e rode de novo.")
        return

    print("Chats encontrados:\n")
    for identificador, (nome, tipo) in chats.items():
        print("  TELEGRAM_CHAT_ID=%s     (%s, %s)" % (identificador, nome, tipo))
    print("\nCopie a linha certa para o .env.")


if __name__ == "__main__":
    main()
