"""Leitura de tabelas publicadas no portal: CSV baixado ou API do datastore.

Os CSVs do portal variam de ano para ano: UTF-8 ou Windows-1252, separador
";" ou ",", às vezes com BOM. Esta leitura cobre os três casos.
"""

import csv
import io

from ftfy import fix_text

from etl.comum.ckan import ler_datastore
from etl.comum.http import get_bytes


def decodificar(conteudo):
    """UTF-8 quando for; senão Windows-1252. ftfy conserta acento quebrado."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", "replace")
    return fix_text(texto)


def ler_csv(conteudo):
    """Bytes de um CSV -> leitor de dicts, com o separador detectado."""
    texto = decodificar(conteudo)
    cabecalho = texto.split("\n", 1)[0]
    sep = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    return csv.DictReader(io.StringIO(texto), delimiter=sep)


def ler_recurso(recurso, timeout=120):
    """Todas as linhas de um recurso: pela API se estiver no datastore, senão pelo CSV."""
    if recurso.get("datastore_active"):
        return [{k: fix_text(v) if isinstance(v, str) else v for k, v in l.items()}
                for l in ler_datastore(recurso["id"])]
    return list(ler_csv(get_bytes(recurso["url"], timeout=timeout)))
