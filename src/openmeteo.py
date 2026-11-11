import unicodedata
from datetime import date, timedelta
from functools import lru_cache

import requests

URL_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
URL_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"

# O arquivo histórico tem alguns dias de atraso; datas mais recentes vêm da API de previsão.
DIAS_ATRASO_HISTORICO = 7

PERIODOS_PRECIPITACAO = (1, 2, 3, 4, 5, 10, 15, 30, 60, 90, 120)

# A busca de cidades é limitada ao estado de São Paulo, Brasil.
PAIS = "BR"
ESTADO = "São Paulo"


class CidadeNaoEncontrada(ValueError):
    """A cidade não existe (ou não foi encontrada) no estado de São Paulo."""


def _normalizar(texto):
    """Minúsculas e sem acentos, para comparar nomes de forma tolerante."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.casefold().strip()


@lru_cache(maxsize=256)
def buscar_cidade(nome):
    """Localiza `nome` no estado de São Paulo e retorna os dados da cidade.

    Retorno:
        {"nome": str, "latitude": float, "longitude": float, "populacao": int | None}

    Levanta `CidadeNaoEncontrada` se nenhum resultado pertencer ao estado de SP.
    Se houver homônimas no estado, escolhe a mais populosa.
    """
    params = {
        "name": nome,
        "count": 100,  # máximo da API; garante que resultados de SP apareçam
        "language": "pt",
        "format": "json",
        "countryCode": PAIS,
    }
    resposta = requests.get(URL_GEOCODING, params=params, timeout=30)
    resposta.raise_for_status()
    resultados = resposta.json().get("results", [])

    estado = _normalizar(ESTADO)
    candidatas = [r for r in resultados if _normalizar(r.get("admin1", "")) == estado]

    if not candidatas:
        raise CidadeNaoEncontrada(f"Cidade '{nome}' não encontrada no estado de {ESTADO}.")

    # Prefere correspondência exata de nome; entre elas, a mais populosa.
    alvo = _normalizar(nome)
    exatas = [r for r in candidatas if _normalizar(r["name"]) == alvo]
    escolhida = max(exatas or candidatas, key=lambda r: r.get("population") or 0)

    return {
        "nome": escolhida["name"],
        "latitude": escolhida["latitude"],
        "longitude": escolhida["longitude"],
        "populacao": escolhida.get("population"),
    }


def _requisitar(url, inicio, fim, lat, long, horario=None):
    """Uma chamada ao Open-Meteo para o intervalo [inicio, fim]."""
    params = {
        "latitude": lat,
        "longitude": long,
        "start_date": inicio.isoformat(),
        "end_date": fim.isoformat(),
        "daily": "precipitation_sum,temperature_2m_mean",
        "timezone": "auto",
    }
    if horario:
        params["hourly"] = horario

    resposta = requests.get(url, params=params, timeout=30)
    resposta.raise_for_status()
    return resposta.json()


def obter_dados_clima(dia, cidade, periodos=PERIODOS_PRECIPITACAO):
    """Retorna todos os dados climáticos de `dia` para uma cidade do estado de SP.

    Retorno:
        {
            "cidade": nome oficial da cidade encontrada,
            "data": date,
            "precipitacao": mm do dia,
            "temperatura": °C média do dia,
            "umidade": % média do dia,
            "prec1": mm/dia médio nos 1 dia anterior,
            "prec2": ..., "prec3": ..., etc.
        }

    Nº de chamadas: 1 de geocodificação (cacheada por cidade) + 1 de clima se
    `dia` já está no arquivo histórico; 2 de clima se o intervalo de 120 dias
    cruza o limite entre histórico e previsão.

    Levanta `CidadeNaoEncontrada` se a cidade não existir no estado de SP.
    """
    if not isinstance(dia, date):
        dia = date.fromisoformat(str(dia))

    local = buscar_cidade(cidade)
    lat, long = local["latitude"], local["longitude"]

    inicio = dia - timedelta(days=max(periodos))
    limite = date.today() - timedelta(days=DIAS_ATRASO_HISTORICO)

    # Define os trechos (url, inicio, fim) necessários
    if dia <= limite:
        trechos = [(URL_HISTORICO, inicio, dia)]
    elif inicio > limite:
        trechos = [(URL_PREVISAO, inicio, dia)]
    else:
        trechos = [
            (URL_HISTORICO, inicio, limite),
            (URL_PREVISAO, limite + timedelta(days=1), dia),
        ]

    precipitacao = {}
    temperatura = {}
    valores_umidade = []

    for url, ini, fim in trechos:
        # Umidade horária só é pedida no trecho que contém o próprio `dia`
        horario = "relative_humidity_2m" if fim == dia else None
        dados = _requisitar(url, ini, fim, lat, long, horario)

        diario = dados["daily"]
        for d, prec, temp in zip(
            diario["time"], diario["precipitation_sum"], diario["temperature_2m_mean"]
        ):
            d = date.fromisoformat(d)
            precipitacao[d] = prec
            temperatura[d] = temp

        if horario:
            horas = dados["hourly"]
            valores_umidade = [
                v
                for t, v in zip(horas["time"], horas["relative_humidity_2m"])
                if t.startswith(dia.isoformat()) and v is not None
            ]

    resultado = {
        "cidade": local["nome"],
        "data": dia,
        "precipitacao": precipitacao.get(dia),
        "temperatura": temperatura.get(dia),
        "umidade": sum(valores_umidade) / len(valores_umidade) if valores_umidade else None,
    }

    # precN = média dos N dias anteriores (o próprio `dia` não entra)
    for n in periodos:
        valores = [precipitacao.get(dia - timedelta(days=i)) for i in range(1, n + 1)]
        valores = [v for v in valores if v is not None]
        resultado[f"prec{n}"] = sum(valores) / len(valores) if valores else None

    return resultado

def obter_dados_clima_coord(dia, latitude, longitude, periodos=PERIODOS_PRECIPITACAO):
    """Retorna todos os dados climáticos de `dia` para uma coordenada específica.

    Retorno:
        {
            "latitude": latitude,
            "longitude": longitude,
            "data": date,
            "precipitacao": mm do dia,
            "temperatura": °C média do dia,
            "umidade": % média do dia,
            "prec1": mm/dia médio nos 1 dia anterior,
            "prec2": ..., "prec3": ..., etc.
        }

    Nº de chamadas: 1 de clima se `dia` já está no arquivo histórico; 
    2 de clima se o intervalo de 120 dias cruza o limite entre histórico e previsão.
    """
    if not isinstance(dia, date):
        dia = date.fromisoformat(str(dia))

    inicio = dia - timedelta(days=max(periodos))
    limite = date.today() - timedelta(days=DIAS_ATRASO_HISTORICO)

    # Define os trechos (url, inicio, fim) necessários
    if dia <= limite:
        trechos = [(URL_HISTORICO, inicio, dia)]
    elif inicio > limite:
        trechos = [(URL_PREVISAO, inicio, dia)]
    else:
        trechos = [
            (URL_HISTORICO, inicio, limite),
            (URL_PREVISAO, limite + timedelta(days=1), dia),
        ]

    precipitacao = {}
    temperatura = {}
    valores_umidade = []

    for url, ini, fim in trechos:
        # Umidade horária só é pedida no trecho que contém o próprio `dia`
        horario = "relative_humidity_2m" if fim == dia else None
        dados = _requisitar(url, ini, fim, latitude, longitude, horario)

        diario = dados["daily"]
        for d, prec, temp in zip(
            diario["time"], diario["precipitation_sum"], diario["temperature_2m_mean"]
        ):
            d = date.fromisoformat(d)
            precipitacao[d] = prec
            temperatura[d] = temp

        if horario:
            horas = dados["hourly"]
            valores_umidade = [
                v
                for t, v in zip(horas["time"], horas["relative_humidity_2m"])
                if t.startswith(dia.isoformat()) and v is not None
            ]

    resultado = {
        "latitude": latitude,
        "longitude": longitude,
        "data": dia,
        "precipitacao": precipitacao.get(dia),
        "temperatura": temperatura.get(dia),
        "umidade": sum(valores_umidade) / len(valores_umidade) if valores_umidade else None,
    }

    # precN = média dos N dias anteriores (o próprio `dia` não entra)
    for n in periodos:
        valores = [precipitacao.get(dia - timedelta(days=i)) for i in range(1, n + 1)]
        valores = [v for v in valores if v is not None]
        resultado[f"prec{n}"] = sum(valores) / len(valores) if valores else None

    return resultado
