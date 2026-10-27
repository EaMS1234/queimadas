from datetime import date, timedelta

import requests

URL_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"

# O arquivo histórico tem alguns dias de atraso; datas mais recentes vêm da API de previsão.
DIAS_ATRASO_HISTORICO = 7


def _consultar(dia, lat, long, diario=None, horario=None):
    """Consulta o Open-Meteo para um único dia e devolve o JSON da resposta."""
    if isinstance(dia, date):
        dia_str = dia.isoformat()
    else:
        dia_str = str(dia)
        dia = date.fromisoformat(dia_str)

    url = URL_HISTORICO if dia <= date.today() - timedelta(days=DIAS_ATRASO_HISTORICO) else URL_PREVISAO

    params = {
        "latitude": lat,
        "longitude": long,
        "start_date": dia_str,
        "end_date": dia_str,
        "timezone": "auto",
    }
    if diario:
        params["daily"] = diario
    if horario:
        params["hourly"] = horario

    resposta = requests.get(url, params=params, timeout=15)
    resposta.raise_for_status()
    return resposta.json()


def obter_precipitacao(dia, lat, long):
    """Precipitação total do dia, em mm."""
    dados = _consultar(dia, lat, long, diario="precipitation_sum")
    return dados["daily"]["precipitation_sum"][0]


def obter_umidade(dia, lat, long):
    """Umidade relativa média do dia, em %, calculada a partir dos valores horários."""
    dados = _consultar(dia, lat, long, horario="relative_humidity_2m")
    valores = [v for v in dados["hourly"]["relative_humidity_2m"] if v is not None]
    if not valores:
        return None
    return sum(valores) / len(valores)


def obter_temperatura(dia, lat, long):
    """Temperatura média do dia a 2 m, em °C."""
    dados = _consultar(dia, lat, long, diario="temperature_2m_mean")
    return dados["daily"]["temperature_2m_mean"][0]


PERIODOS_PRECIPITACAO = (1, 2, 3, 4, 5, 10, 15, 30, 60, 90, 120)


def _precipitacao_diaria(inicio, fim, lat, long):
    """Precipitação diária (mm) de `inicio` a `fim`, inclusive, como {date: mm}.

    Divide o intervalo entre a API de histórico e a de previsão, conforme a idade de cada data.
    """
    limite = date.today() - timedelta(days=DIAS_ATRASO_HISTORICO)

    trechos = []
    if inicio <= limite:
        trechos.append((URL_HISTORICO, inicio, min(fim, limite)))
    if fim > limite:
        trechos.append((URL_PREVISAO, max(inicio, limite + timedelta(days=1)), fim))

    resultado = {}
    for url, ini, f in trechos:
        params = {
            "latitude": lat,
            "longitude": long,
            "start_date": ini.isoformat(),
            "end_date": f.isoformat(),
            "daily": "precipitation_sum",
            "timezone": "auto",
        }
        resposta = requests.get(url, params=params, timeout=30)
        resposta.raise_for_status()
        diario = resposta.json()["daily"]
        for dia_str, valor in zip(diario["time"], diario["precipitation_sum"]):
            resultado[date.fromisoformat(dia_str)] = valor
    return resultado


def obter_precipitacoes_anteriores(dia, lat, long, periodos=PERIODOS_PRECIPITACAO):
    """Precipitação média diária (mm/dia) nos N dias anteriores a `dia`.

    Retorna um dicionário {"prec1": ..., "prec2": ..., "prec3": ..., "prec5": ..., ...}.
    precN é a média dos N dias imediatamente anteriores a `dia` (o próprio `dia` não entra).
    """
    if not isinstance(dia, date):
        dia = date.fromisoformat(str(dia))

    # Uma única consulta cobre o maior período; as médias menores saem dela.
    diaria = _precipitacao_diaria(
        dia - timedelta(days=max(periodos)), dia - timedelta(days=1), lat, long
    )

    resultado = {}
    for n in periodos:
        valores = [diaria.get(dia - timedelta(days=i)) for i in range(1, n + 1)]
        valores = [v for v in valores if v is not None]
        resultado[f"prec{n}"] = sum(valores) / len(valores) if valores else None
    return resultado
