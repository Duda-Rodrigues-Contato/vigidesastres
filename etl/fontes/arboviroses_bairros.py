"""Arboviroses por bairro: casos prováveis e incidência por ano (decisões 001 e 002).

Fonte: SINAN, publicado pela Secretaria de Saúde no Portal de Dados Abertos
do Recife ("Casos de Dengue, Zika e Chikungunya"), um arquivo por doença e
ano, por BAIRRO DE RESIDÊNCIA. População: IBGE, Censo 2022.

  bronze  (não há: o arquivo tem nascimento, rua, CEP e comorbidades - decisão 001)
  silver  silver.arboviroses_bairro_ano    doença x ano x bairro: notificados, prováveis, incidência
  silver  silver.qualidade_arboviroses     por arquivo: linhas sem bairro, nomes não reconhecidos

LGPD: pela API do portal, só os 3 campos usados são pedidos. Arquivo que só
existe como CSV (dengue 2015 e 2019) é lido linha a linha e cada linha é
reduzida aos 3 campos na hora. Nada individual sai de extrair().

Dois formatos convivem no portal: até 2020 (co_municipio_residencia,
no_bairro_residencia, tp_classificacao_final) e de 2021 em diante (ID_MN_RESI,
NM_BAIRRO, CLASSI_FIN), às vezes em minúsculas. COLUNAS cobre os dois.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime

from dominio.arboviroses import DOENCAS, doenca_pela_classificacao
from etl import config
from etl.base import Conector
from etl.comum import ibge
from etl.comum.ckan import dataset_por_titulo, ler_datastore
from etl.comum.http import get_bytes, get_json
from etl.comum.tabela import ler_csv
from etl.comum.texto import normalizar
from etl.destinos.base import Carga

TITULO = "Casos de Dengue, Zika e Chikungunya"
ANO_INICIAL = 2013  # o portal tem dengue desde 2013; chikungunya e zika desde 2015
# campo canônico -> nomes possíveis no portal (comparados sem diferenciar maiúsculas)
COLUNAS = {
    "CLASSI_FIN": ("CLASSI_FIN", "tp_classificacao_final"),
    "NM_BAIRRO": ("NM_BAIRRO", "no_bairro_residencia"),
    "ID_MN_RESI": ("ID_MN_RESI", "co_municipio_residencia"),
}
DESCARTADO = 5  # classificação final no SINAN (decisão 002)
CODIGOS_RECIFE = {"261160", "2611606"}  # IBGE com e sem dígito verificador
FONTE = "SINAN, via Portal de Dados Abertos do Recife; população: IBGE, Censo 2022"

# nomes do SINAN que não batem com os do IBGE depois de normalizar
APELIDOS_SINAN = {"BAIRRO DO RECIFE": "RECIFE", "RECIFE ANTIGO": "RECIFE"}


def arquivos_de_casos(pacote, anos):
    """[{doenca, ano, id}] dos recursos do dataset, um por doença e ano."""
    arquivos = []
    for r in pacote["resources"]:
        nome = (r.get("name") or "").lower()
        ano = re.search(r"(20\d\d)", nome)
        doenca = next((d for d in DOENCAS if d in nome), None)
        if ano and doenca and "metadado" not in nome and int(ano.group(1)) in anos:
            arquivos.append({"doenca": doenca, "ano": int(ano.group(1)), "id": r["id"],
                             "api": bool(r.get("datastore_active")), "url": r.get("url"),
                             "nome": r.get("name")})
    return sorted(arquivos, key=lambda a: (a["ano"], a["doenca"]))


def campos_disponiveis(resource_id):
    res = get_json(f"{config.CKAN_RECIFE}/datastore_search", {"resource_id": resource_id, "limit": 0})
    return {f["id"] for f in res["result"]["fields"]}


def resolver_colunas(disponiveis):
    """{campo canônico: nome real da coluna} para os campos que existem no arquivo."""
    por_minuscula = {c.lower(): c for c in disponiveis}
    achados = {}
    for canonico, nomes in COLUNAS.items():
        real = next((por_minuscula[n.lower()] for n in nomes if n.lower() in por_minuscula), None)
        if real:
            achados[canonico] = real
    return achados


def linhas_do_arquivo(arquivo):
    """As linhas do arquivo JÁ reduzidas aos 3 campos, com os nomes canônicos.

    Pela API, só os 3 campos são pedidos. Pelo CSV, cada linha é reduzida na hora.
    """
    if arquivo["api"]:
        colunas = resolver_colunas(campos_disponiveis(arquivo["id"]))
        if "NM_BAIRRO" not in colunas:
            raise ValueError(f"sem coluna de bairro (há: {sorted(campos_disponiveis(arquivo['id']))[:8]}...)")
        brutas = ler_datastore(arquivo["id"], list(colunas.values()))
    else:
        leitor = ler_csv(get_bytes(arquivo["url"], timeout=300))
        colunas = resolver_colunas(leitor.fieldnames or [])
        if "NM_BAIRRO" not in colunas:
            raise ValueError("CSV sem coluna de bairro")
        brutas = leitor
    return [{canonico: l.get(real) for canonico, real in colunas.items()} for l in brutas]


def contar(linhas, bairros_ibge):
    """Linhas individuais -> contagem por bairro + indicadores de qualidade. Só totais saem daqui."""
    contagem = defaultdict(lambda: {"notificados": 0, "descartados": 0})
    q = {"linhas": len(linhas), "sem_bairro": 0, "fora_do_recife": 0}
    classes, nao_reconhecidos = Counter(), Counter()
    for l in linhas:
        municipio = str(l.get("ID_MN_RESI") or "").strip().split(".")[0]
        if municipio and municipio not in CODIGOS_RECIFE:
            q["fora_do_recife"] += 1
            continue
        classe = str(l.get("CLASSI_FIN") or "").strip().split(".")[0]
        classes[classe] += 1
        nome = normalizar(l.get("NM_BAIRRO") or "")
        nome = APELIDOS_SINAN.get(nome, nome)
        if not nome:
            q["sem_bairro"] += 1
        elif nome not in bairros_ibge:
            nao_reconhecidos[nome] += 1
        else:
            contagem[nome]["notificados"] += 1
            if classe == str(DESCARTADO):
                contagem[nome]["descartados"] += 1
    q["nao_reconhecidos"] = sum(nao_reconhecidos.values())
    q["classificacao"] = dict(classes)
    q["nomes_nao_reconhecidos"] = dict(nao_reconhecidos.most_common(10))
    return dict(contagem), q


class ArbovirosesBairros(Conector):
    nome = "arboviroses_bairros"
    frequencia = "anual"
    descricao = "Casos prováveis de dengue, chikungunya e zika por bairro e ano (SINAN)"
    guardar_bronze = False

    def __init__(self, destino, anos=None):
        super().__init__(destino)
        self.anos = list(anos or range(ANO_INICIAL, datetime.now().year))

    def extrair(self):
        """Já devolve contagens por bairro: {populacao, arquivos: [{doenca, ano, contagem, qualidade}]}."""
        populacao = ibge.populacao_por_bairro(ibge.linhas_do_recife())
        pacote = dataset_por_titulo("dengue", TITULO)
        if not pacote:
            raise ValueError(f"dataset '{TITULO}' não encontrado no portal")
        arquivos, falhas = [], []
        for a in arquivos_de_casos(pacote, self.anos):
            # um arquivo com problema vira aviso e entra na qualidade; não derruba os outros
            try:
                contagem, qualidade = contar(linhas_do_arquivo(a), populacao)
                outra = doenca_pela_classificacao(a["doenca"], qualidade["classificacao"])
                if outra:
                    raise ValueError(f"o conteúdo é de {outra}, não de {a['doenca']}: arquivo trocado no portal")
            except Exception as erro:  # noqa: BLE001
                print(f"  [{self.nome}] {a['doenca']} {a['ano']}: IGNORADO - {type(erro).__name__}: {erro}")
                falhas.append({"doenca": a["doenca"], "ano": a["ano"], "erro": f"{type(erro).__name__}: {erro}"})
                continue
            arquivos.append({**a, "contagem": contagem, "qualidade": qualidade})
        if not arquivos:
            raise ValueError("nenhum arquivo de casos pôde ser lido")
        return {"populacao": populacao, "arquivos": arquivos, "falhas": falhas}

    def transformar(self, bruto, coletado_em):
        populacao = bruto["populacao"]
        linhas, qualidade = [], []
        for a in bruto["arquivos"]:
            for chave, b in populacao.items():  # todo bairro entra, com zero se não teve caso
                c = a["contagem"].get(chave, {"notificados": 0, "descartados": 0})
                provaveis = c["notificados"] - c["descartados"]
                linhas.append({
                    "doenca": a["doenca"], "ano": a["ano"], "chave": chave, "bairro": b["nome"],
                    "notificados": c["notificados"], "descartados": c["descartados"], "provaveis": provaveis,
                    "populacao": b["populacao"],
                    "incidencia_10k": round(provaveis / b["populacao"] * 10_000, 1) if b["populacao"] else None,
                    "fonte": FONTE, "coletado_em": coletado_em,
                })
            q = a["qualidade"]
            qualidade.append({"doenca": a["doenca"], "ano": a["ano"], **q, "coletado_em": coletado_em})
            print(f"  [{self.nome}] {a['doenca']:<12} {a['ano']} ({'API' if a['api'] else 'CSV'}): "
                  f"{q['linhas']:>6} linhas | sem bairro {q['sem_bairro']} | não reconhecido "
                  f"{q['nao_reconhecidos']} | fora do Recife {q['fora_do_recife']} | classes {q['classificacao']}")
        for f in bruto.get("falhas", []):
            qualidade.append({**f, "coletado_em": coletado_em})
        return [
            Carga("silver.arboviroses_bairro_ano", linhas, chaves=("doenca", "ano", "chave")),
            Carga("silver.qualidade_arboviroses", qualidade, chaves=("doenca", "ano")),
        ]
