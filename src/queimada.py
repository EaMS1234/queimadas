import math


def risco_fogo(vegetacao, dias_sem_chuva, umidade, temperatura):
    '''
    Calcula o risco fogo a partir do constante A (tipo de vegetação),
    período de secura, umidade relativa do ar e máxima de temperatura.

    vegetacao = constante
    dias_sem_chuva = deve ser calculada usando a função periodo_de_secura
    umidade = 0 a 100
    temperatura = graus celsius
    
    Fonte: http://mtc-m21c.sid.inpe.br/col/sid.inpe.br/mtc-m21c/2019/11.21.11.03/doc/publicacao.pdf
    '''

    rb = 0.8 * ( 1 + math.sin( ( vegetacao * dias_sem_chuva - 90 ) * math.pi / 180 ) ) / 2

    fu = -0.006 * umidade + 1.3
    ft = 0.02 * temperatura + 0.4

    return rb * fu * ft


def periodo_de_secura(prec):
    '''
    Calcula o período de secura (PSE) a partir da precipitação passada
    
    prec = {prec1, prec2, prec3, prec4, prec5, prec10, prec15, prec30, prec60, prec90, prec120}

    Fonte: http://mtc-m21c.sid.inpe.br/col/sid.inpe.br/mtc-m21c/2019/11.21.11.03/doc/publicacao.pdf
    '''

    euler = math.e
    
    fp = {
        'fp1': euler ** (-0.14 * prec['prec1']),
        'fp2': euler ** (-0.07 * (prec['prec2'] - prec['prec1'])),
        'fp3': euler ** (-0.04 * (prec['prec3'] - prec['prec2'])),
        'fp4': euler ** (-0.03 * (prec['prec4'] - prec['prec3'])),
        'fp5': euler ** (-0.02 * (prec['prec5'] - prec['prec4'])),
        'fp6a10': euler ** (-0.01 * (prec['prec10'] - prec['prec5'])),
        'fp11a15': euler ** (-0.008 * (prec['prec15'] - prec['prec10'])),
        'fp16a30': euler ** (-0.004 * (prec['prec30'] - prec['prec15'])),
        'fp31a60': euler ** (-0.002 * (prec['prec60'] - prec['prec30'])),
        'fp61a90': euler ** (-0.001 * (prec['prec90'] - prec['prec60'])),
        'fp91a120': euler ** (-0.0007 * (prec['prec120'] - prec['prec90']))
        }

    pse = 105

    for f in fp.values():
        pse *= f

    return pse
