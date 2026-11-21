"""Silencia logs quando o repo e publico (LOG_SEGURO=1, ligado nos workflows).

Logs do GitHub Actions de repo publico sao abertos a qualquer pessoa, e os
scripts imprimem localizador, sobrenome etc. Aqui vale lista de permitidos:
- stdout: so passa linha so de numero (o workflow le "n=$(... --contar)");
- stderr, logging, subprocessos: descartados no nivel do descritor de arquivo;
- excecao nao tratada: so tipo + arquivo:linha, nunca a mensagem.
Para depurar, rode local sem LOG_SEGURO. Carregado via PYTHONPATH=src.
shortcut: nome de arquivo/linha da excecao pode, em tese, vazar se o nome do arquivo
for dado de cliente; scripts de src/ nao fazem isso.
"""
import os
import re
import sys

if os.environ.get("LOG_SEGURO") == "1":
    _nulo = os.open(os.devnull, os.O_WRONLY)
    _saida = os.fdopen(os.dup(1), "w")
    os.dup2(_nulo, 1)
    os.dup2(_nulo, 2)

    class _Filtro:
        def write(self, texto):
            for linha in texto.splitlines():
                if re.fullmatch(r"\d{1,6}", linha.strip()):
                    _saida.write(linha.strip() + "\n")
            _saida.flush()
            return len(texto)

        def flush(self):
            pass

    class _Descarta(_Filtro):
        def write(self, texto):
            return len(texto)

    sys.stdout = _Filtro()
    sys.stderr = _Descarta()

    def _erro_seguro(tipo, _valor, tb):
        while tb and tb.tb_next:
            tb = tb.tb_next
        onde = "%s:%s" % (os.path.basename(tb.tb_frame.f_code.co_filename), tb.tb_lineno) if tb else "?"
        _saida.write("ERRO %s em %s\n" % (tipo.__name__, onde))
        _saida.flush()

    sys.excepthook = _erro_seguro
