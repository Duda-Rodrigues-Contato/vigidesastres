from etl.fontes import infodengue
from etl.historico import infodengue as hist


def test_cobre_todos_os_anos_sem_duplicar(destino, monkeypatch):
    pedidos = []

    def api(url, params):
        pedidos.append((params["ey_start"], params["ey_end"]))
        return [{"SE": ano * 100 + 10, "data_iniSE": f"{ano}-03-08", "casos": 5, "casos_est": 6, "nivel": 1}
                for ano in range(params["ey_start"], params["ey_end"] + 1)]
    monkeypatch.setattr(infodengue, "get_json", api)
    hist.carregar(destino, 2014, 2019, avisar=lambda s: None)
    anos_pedidos = {a for par in pedidos for a in range(par[0], par[1] + 1)}
    assert anos_pedidos == set(range(2014, 2020))
    sem = destino.banco["silver_arbovirose_semanal"]
    assert sem.count_documents({"doenca": "dengue"}) == 6           # uma semana por ano, sem duplicar
    hist.carregar(destino, 2014, 2019, avisar=lambda s: None)
    assert sem.count_documents({"doenca": "dengue"}) == 6
