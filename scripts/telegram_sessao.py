"""Gera a sessao de LEITURA da conta do proprietário no Telegram (uma vez, no Mac).

Uso:
    pip install telethon
    python3 scripts/telegram_sessao.py

Pede api_id e api_hash (my.telegram.org -> API development tools), depois o
telefone e o codigo que o Telegram manda. Grava a sessao em
~/.lf-telegram-sessao (so voce le) e lista os chats cujo nome bate com as
palavras-chave, pra gente fixar o id de cada fonte de promocao.
Nada e enviado, apagado ou marcado como lido: so a leitura que o robo fara.
"""

import os
import stat

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

CAMINHO = os.path.expanduser("~/.lf-telegram-sessao")
PALAVRAS = ("alertas cph", "milhasvip", "pdm", "ebc")

api_id = int(input("api_id: ").strip())
api_hash = input("api_hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as cliente:
    with open(CAMINHO, "w") as f:
        f.write(cliente.session.save())
    os.chmod(CAMINHO, stat.S_IRUSR | stat.S_IWUSR)
    print("\nSessao gravada em %s" % CAMINHO)
    print("\nChats encontrados:")
    for d in cliente.iter_dialogs():
        if any(p in (d.name or "").lower() for p in PALAVRAS):
            print("  %-14s %-10s %s" % (d.id, "forum" if getattr(d.entity, "forum", False) else "", d.name))
