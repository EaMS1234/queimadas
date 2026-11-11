import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import src.openmeteo as api
import src.queimada as q


def meses_faltantes(municipio):
    existentes = df_agrupado[municipio] if municipio in df_agrupado else []
    return [mes for mes in todos_os_meses if mes not in existentes]


def obter_com_retry(dia, municipio, max_tentativas=10):
    """Devolve o resultado da API ou None se esgotar as tentativas."""
    for tentativa in range(max_tentativas):
        try:
            return api.obter_dados_clima(dia, municipio)
        except requests.exceptions.RequestException:
            if tentativa == max_tentativas - 1:
                return None
            espera = 2 ** (tentativa + 1)
            print(f'Erro: tentando de novo em {espera} segundos')
            time.sleep(espera)


arquivo = 'bdqueimadas.csv'

nome = input('  Nome do arquivo (bdqueimadas.csv): ').strip()
if nome:
    arquivo = nome

if not os.path.exists(arquivo):
    print(f'{arquivo} não existe!')
    exit()

df = pd.read_csv(arquivo)

# Colunas não utilizadas pra treinamento
df = df.drop(columns=['Satelite', 'Pais', 'Estado', 'FRP', 'Latitude', 'Longitude'])

# Apaga os dados dos biomas que não sejam mata atlântica e cerrado
df = df[df["Bioma"].isin(["Mata Atlântica", "Cerrado"])]

# Converte o bioma em um valor numérico baseado no tipo de vegetação.
dados = {'Mata Atlântica': 1.7, 'Cerrado': 3}
df['Bioma'] = df['Bioma'].map(dados)

# Filtra os dados quebrados
df = df[df["DiaSemChuva"] >= 0]
df = df[df["RiscoFogo"] >= 0]

# Garante que a coluna é datetime
df['DataHora'] = pd.to_datetime(df['DataHora'])

# Cria uma coluna temporária com o dia para filtrar as entradas repetidas do mesmo dia
df['Data_Temp'] = df['DataHora'].dt.date
df = df.drop_duplicates(subset=['Data_Temp', 'Municipio'], keep='first')
df = df.drop(columns=['Data_Temp'])

# Converte a DataHora para o período mensal em texto (Ex: '2025-09').
# Como string, a comparação com os meses de todos_os_meses funciona direito.
df['DataHora'] = df['DataHora'].dt.to_period('M').astype(str)

# Agrupa por Mês e Município, e tira a média das outras colunas
df = df.groupby(['DataHora', 'Municipio']).mean().reset_index()

# Ordena por lugar e data
df = df.sort_values(by=['Municipio', 'DataHora'])
df = df.reset_index(drop=True)

# Fogo = 1 para todos os dados do bdqueimadas (meses em que o local REGISTROU foco de calor)
df['Fogo'] = 1

# Adiciona os meses faltantes, onde Fogo = 0 (meses em que o local NÃO registrou foco de calor)
data_inicio = df['DataHora'].min()
data_fim = df['DataHora'].max()

print(f'    Compilando dados de {data_inicio} até {data_fim}')

municipios = df['Municipio'].unique()
todos_os_meses = (
    pd.date_range(start=data_inicio, end=data_fim, freq='MS')
    .strftime('%Y-%m')
    .tolist()
)
df_agrupado = df.groupby('Municipio')['DataHora'].unique()

# Vegetação por município calculada uma vez só (evita filtrar o df a cada iteração)
vegetacao_por_municipio = df.groupby('Municipio')['Bioma'].mean().to_dict()

total = sum(len(meses_faltantes(m)) for m in municipios)
processados = 0
novas_linhas = []
pulados = []
inicio = time.perf_counter()


def mostrar_progresso(municipio, mes, status):
    decorrido = time.perf_counter() - inicio
    restante = (decorrido / processados) * (total - processados)
    print(
        f'[{processados / total * 100:5.1f}%] {processados}/{total} | '
        f'decorrido: {timedelta(seconds=int(decorrido))} | '
        f'faltam ~{timedelta(seconds=int(restante))} | '
        f'{status}: {municipio} {mes}'
    )


try:
    for municipio in municipios:
        for mes in meses_faltantes(municipio):
            dia = datetime.strptime(mes, '%Y-%m').date()

            resultado = obter_com_retry(dia, municipio)
            processados += 1

            if resultado is None:
                pulados.append((municipio, mes))
                mostrar_progresso(municipio, mes, 'PULADO')
                continue

            vegetacao = vegetacao_por_municipio[municipio]
            umidade = resultado['umidade']
            temperatura = resultado['temperatura']
            precipitacao = resultado['precipitacao']
            precs = {k: v for k, v in resultado.items() if k.startswith('prec')}

            pse = q.periodo_de_secura(precs)
            rf = q.risco_fogo(vegetacao, pse, umidade, temperatura)

            novas_linhas.append([mes, municipio, vegetacao, pse, precipitacao, rf, 0])
            mostrar_progresso(municipio, mes, 'ok')

finally:
    # Mesmo com Ctrl+C ou erro inesperado, o que já foi coletado entra no df
    if novas_linhas:
        df = pd.concat(
            [df, pd.DataFrame(novas_linhas, columns=df.columns)],
            ignore_index=True,
        )

print(f'\nConcluído. {len(pulados)} entradas puladas.')
for municipio, mes in pulados:
    print(f'  - {municipio} {mes}')

# Número total de municípios únicos
total_municipios = df['Municipio'].nunique()

# Conta quantas vezes cada município aparece e depois tira a média
media_aparicoes = df['Municipio'].value_counts().mean()

print(f'Número de municípios: {total_municipios}')
print(f'Média de focos por município: {media_aparicoes:.2f}')

# Salva o dataframe em um arquivo CSV
df.to_csv("out/out.csv", index=False)
