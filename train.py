import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from sklearn.model_selection import train_test_split
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.neural_network import MLPClassifier

import pickle
import os

arquivo = 'out.csv'

nome = input('  Nome do arquivo (out.csv): ').strip()
if nome:
    arquivo = nome

if not os.path.exists(arquivo):
    print(f'{arquivo} não existe!')
    exit()

df = pd.read_csv(arquivo)

ano = df["DataHora"].str[:4].astype(int).max()

X = df[["Bioma", "DiaSemChuva", "Precipitacao", "RiscoFogo"]]
y = df["Fogo"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(
    length_scale=[1.0] * X_train_scaled.shape[1], 
    length_scale_bounds=(1e-2, 1e2)
)

gpc = GaussianProcessClassifier(
    kernel=kernel,
    random_state=42,
    n_jobs=-1
)

mlp = MLPClassifier(
    hidden_layer_sizes=(8),
    activation='relu',
    solver='adam',
    max_iter=500,
    random_state=42
)

gpc.fit(X_train_scaled, y_train)
mlp.fit(X_train_scaled, y_train)

pickle.dump(gpc, open(f'out/gpc-{ano}.pkl', 'wb'))
pickle.dump(mlp, open(f'out/mlp-{ano}.pkl', 'wb'))
pickle.dump(scaler, open(f'out/scaler-{ano}.pkl', 'wb'))
