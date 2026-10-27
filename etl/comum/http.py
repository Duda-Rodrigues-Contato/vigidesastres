"""Requisições com tempo limite, nova tentativa e User-Agent.

Antes, cada conector tinha a sua cópia desta lógica. Agora uma correção
aqui vale para todos.
"""

import time

import requests

from etl import config


def _com_tentativas(fazer, descricao):
    for tentativa in range(1, config.TENTATIVAS + 1):
        try:
            resposta = fazer()
            resposta.raise_for_status()
            return resposta
        except requests.RequestException as erro:
            if tentativa == config.TENTATIVAS:
                raise
            espera = 2**tentativa
            print(f"  falha em {descricao} ({erro}); nova tentativa em {espera}s")
            time.sleep(espera)


def get_json(url, params=None, timeout=None):
    return _com_tentativas(
        lambda: requests.get(url, params=params, headers=config.HEADERS,
                             timeout=timeout or config.TIMEOUT),
        url,
    ).json()


def get_bytes(url, params=None, timeout=None):
    return _com_tentativas(
        lambda: requests.get(url, params=params, headers=config.HEADERS,
                             timeout=timeout or config.TIMEOUT, allow_redirects=True),
        url,
    ).content
