"""Lista os chats das fontes de promocao usando a sessao ja gravada
(~/.lf-telegram-sessao). Sem novo login; so leitura. Mostra id, tipo e nome.

Uso: python3 scripts/telegram_chats.py   (pede api_id e api_hash de novo)
"""

import os

from telethon.sessions import StringSession
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetForumTopicsRequest

PALAVRAS = ("alertas cph", "milhasvip", "milhas vip", "pdm", "ebc", "promoç", "dicas")

sessao = open(os.path.expanduser("~/.lf-telegram-sessao")).read().strip()
api_id = int(input("api_id: ").strip())
api_hash = input("api_hash: ").strip()

with TelegramClient(StringSession(sessao), api_id, api_hash) as cliente:
    for d in cliente.iter_dialogs():
        if any(p in (d.name or "").lower() for p in PALAVRAS):
            e = d.entity
            tipo = "forum" if getattr(e, "forum", False) else ("canal" if getattr(e, "broadcast", False) else "grupo")
            print("%-16s %-6s %s" % (d.id, tipo, d.name))
            if tipo == "forum":
                r = cliente(GetForumTopicsRequest(peer=e, offset_date=None, offset_id=0,
                                                  offset_topic=0, limit=100))
                for t in r.topics:
                    print("    topico %-8s %s" % (t.id, t.title))
