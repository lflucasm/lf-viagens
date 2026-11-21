#!/bin/bash
# Sincroniza os voos do MilhasFlow e gera o CSV do dia.
cd "$(dirname "$0")" || exit 1
exec /usr/bin/python3 src/sync.py "$@"
