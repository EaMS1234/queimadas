import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import src.openmeteo as api
import src.queimada as q


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


def mostrar_progresso(municipio, mes, status, atual, total):
    decorrido = time.perf_counter() - inicio
    restante = (decorrido / atual) * (total - atual) if atual > 0 else 0
    print(
        f'[{atual / total * 100:5.1f}%] {atual}/{total} | '
        f'decorrido: {timedelta(seconds=int(decorrido))} | '
        f'faltam ~{timedelta(seconds=int(restante))} | '
        f'{status}: {municipio} {mes}'
    )


arquivo = 'out/out.csv'

nome = input('  Nome do arquivo (out/out.csv): ').strip()
if nome:
    arquivo = nome

if not os.path.exists(arquivo):
    print(f'{arquivo} não existe!')
    exit()

df = pd.read_csv(arquivo)

# Filtra apenas os índices onde Fogo == 0
indices_fogo_zero = df[df['Fogo'] == 0].index
total = len(indices_fogo_zero)

if total == 0:
    print('Nenhum registro com Fogo = 0 encontrado no arquivo.')
    exit()

print(f'Encontrados {total} registros com Fogo = 0 para atualizar o DiaSemChuva.')

inicio = time.perf_counter()
processados = 0
pulados = []

try:
    for idx in indices_fogo_zero:
        mes = str(df.at[idx, 'DataHora'])
        municipio = str(df.at[idx, 'Municipio'])
        dia = datetime.strptime(mes, '%Y-%m').date()

        processados += 1
        resultado = obter_com_retry(dia, municipio)

        if resultado is None:
            pulados.append((municipio, mes))
            mostrar_progresso(municipio, mes, 'PULADO', processados, total)
            continue

        # Atualiza o DiaSemChuva com o valor novo da API
        df.at[idx, 'DiaSemChuva'] = resultado['diasemchuva']

        # Atualiza também os demais dados correlacionados para manter a consistência
        vegetacao = df.at[idx, 'Bioma']
        umidade = resultado['umidade']
        temperatura = resultado['temperatura']
        precipitacao = resultado['precipitacao']
        precs = {k: v for k, v in resultado.items() if k.startswith('prec')}

        pse = q.periodo_de_secura(precs)
        df.at[idx, 'Precipitacao'] = precipitacao
        df.at[idx, 'RiscoFogo'] = q.risco_fogo(vegetacao, pse, umidade, temperatura)

        mostrar_progresso(municipio, mes, 'ok', processados, total)

finally:
    # Salva o DataFrame atualizado de volta no arquivo CSV
    df.to_csv(arquivo, index=False)
    print(f'\nAtualização concluída e salva em: {arquivo}')

print(f'Total de entradas puladas: {len(pulados)}')
for municipio, mes in pulados:
    print(f'  - {municipio} {mes}')
