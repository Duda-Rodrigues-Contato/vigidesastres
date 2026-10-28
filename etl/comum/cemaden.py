"""Cliente da Plataforma de Entrega de Dados (PED) do CEMADEN.

Cadastro gratuito em ped.cemaden.gov.br; credenciais no .env
(CEMADEN_EMAIL, CEMADEN_SENHA). Regras da plataforma que este cliente respeita:
  - até 12 requisições por minuto para usuário externo: pausa entre chamadas;
  - o token expira: renova uma vez se a API responder 401.
Citação obrigatória ao exibir: "Dados da Rede Observacional do CEMADEN/MCTIC".
"""

import csv
import io
import os
import time

import requests

from etl import config

TOKEN_URL = "https://ped.cemaden.gov.br/SGAA/rest/controle-token/tokens"
API = "https://sws.cemaden.gov.br/PED/rest"
PAUSA_S = 5.5  # 60 s / 12 requisições, com folga
FONTE = "Dados da Rede Observacional do CEMADEN/MCTIC"


class ClienteCemaden:
    def __init__(self, email=None, senha=None):
        self.email = email or os.getenv("CEMADEN_EMAIL")
        self.senha = senha or os.getenv("CEMADEN_SENHA")
        if not (self.email and self.senha):
            raise ValueError("CEMADEN_EMAIL e CEMADEN_SENHA ausentes no .env")
        self._token = None
        self._ultima = 0.0

    def _esperar(self):
        falta = PAUSA_S - (time.monotonic() - self._ultima)
        if falta > 0:
            time.sleep(falta)
        self._ultima = time.monotonic()

    def _renovar_token(self):
        self._esperar()
        r = requests.post(TOKEN_URL, json={"email": self.email, "password": self.senha},
                          headers=config.HEADERS, timeout=config.TIMEOUT)
        r.raise_for_status()
        self._token = r.json()["token"]

    def get(self, rota, params, aceita="application/json"):
        """GET autenticado; devolve a Response (o chamador decide JSON ou texto)."""
        if not self._token:
            self._renovar_token()
        for tentativa in range(2):
            self._esperar()
            r = requests.get(f"{API}/{rota}", params=params, timeout=config.TIMEOUT,
                             headers={**config.HEADERS, "accept": aceita, "token": self._token})
            if r.status_code == 401 and tentativa == 0:
                self._renovar_token()
                continue
            return r
        return r

    def estacoes_do_municipio(self, codibge, uf):
        """[{codestacao, id_tipoestacao, nome}] do cadastro (sem coordenada)."""
        r = self.get("pcds-cadastro/estacoes", {"rede": "11", "uf": uf, "codibge": codibge})
        r.raise_for_status()
        return r.json()

    def serie_csv(self, codigo, uf, inicio, fim, sensor="10"):
        """Texto CSV de uma estação no período (máx. 31 dias). '' se não houver dado."""
        r = self.get("pcds/dados_pcd", {
            "rede": "11", "uf": uf, "sensor": sensor, "codigo": codigo,
            "inicio": f"{inicio:%Y%m%d%H%M}", "fim": f"{fim:%Y%m%d%H%M}",
        }, aceita="text/csv")
        texto = r.text or ""
        # período sem leitura volta como aviso, não como erro
        if r.status_code in (200, 202) and "cod.estacao" in texto:
            return texto
        if r.status_code in (200, 202, 204, 404) or "nenhum resultado" in texto.lower():
            return ""
        r.raise_for_status()
        return ""


def ler_serie(texto):
    """CSV do dados_pcd -> dicts. Pula a linha de aviso antes do cabeçalho."""
    linhas = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas) if l.startswith("cod.estacao")), None)
    if inicio is None:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(linhas[inicio:])), delimiter=";"))
