import src.openmeteo as api
from datetime import date

print(api.obter_dados_clima(date.today(), 'SÃO JOÃO DA BOA VISTA'))
