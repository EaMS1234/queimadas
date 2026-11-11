from flask import Flask, request, jsonify
from datetime import datetime as dt
import openmeteo as om
import queimada as qm
import pickle
from pathlib import Path
import sys

api = Flask(__name__)
modelos = {}
scalers = {}


def carregar_modelos(pasta):
    pasta = Path(pasta)
    
    for arq in pasta.glob("*.pkl"):
        nome_base = arq.stem
        
        # Verifica se é o arquivo de scaler (ex: scaler-2023.pkl)
        if nome_base.startswith("scaler-"):
            ano = nome_base.split("-", 1)[1]
            with arq.open("rb") as f:
                scalers[ano] = pickle.load(f)
                
        else:
            try:
                metodo, ano = nome_base.rsplit("-", 1)
                with arq.open("rb") as f:
                    modelos[f"{metodo}_{ano}"] = pickle.load(f)
            except ValueError:
                continue

def get_clima(lat, long, hora):
    hora = dt.fromisoformat(hora)

    clima = om.obter_dados_clima_coord(hora.date(), lat, long)
    
    precs = {k: v for k, v in clima.items() if k.startswith('prec')}
    pse = qm.periodo_de_secura(precs)

    # bioma 2.5 = média entre 2 e 3, que são o fator de vegetação predominantes
    #             na mata atlântica e no cerrado, respectivamente
    rf = qm.risco_fogo(2.5, pse, clima['umidade'], clima['temperatura'])

    return (rf, pse, clima)

@api.get('/modelos/')
def listar_modelos():
    return jsonify(list(modelos.keys()))

@api.get('/modelos/<modelo>')
def prever(modelo):
    lat = float(request.args['lat'])
    long = float(request.args['long'])
    hora = request.args['datetime']

    clima = get_clima(lat, long, hora)
    # bioma 2.5 = média entre 2 e 3, que são o fator de vegetação predominantes
    #             na mata atlântica e no cerrado, respectivamente
    dados = scalers[modelo[-4:]].transform([[
        2.5,                      # Bioma
        clima[1],                 # DiaSemChuva
        clima[2]['precipitacao'], # Precipitacao
        clima[0]                  # RiscoFogo
        ]])

    previsao = float(modelos[modelo].predict_proba(dados)[0][1])

    return jsonify(modelo=modelo, probabilidade_de_incendio=previsao, risco_fogo=clima[0], periodo_de_secura=clima[1], clima=clima[2])

@api.get('/clima')
def clima():
    lat = float(request.args['lat'])
    long = float(request.args['long'])
    hora = request.args['datetime']

    dados = get_clima(lat, long, hora)

    return jsonify(risco_fogo=dados[0], periodo_de_secura=dados[1], clima=dados[2])


if __name__ == '__main__':
    pasta = 'out/'
    
    try:
        pasta = sys.argv[1]

    except:
        pasta = 'out/'

    carregar_modelos(pasta)
    print(modelos)
    api.run(debug=True, port=5000)
