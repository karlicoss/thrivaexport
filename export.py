#!/usr/bin/env python3

cookie = 'TODO'

# meh
cookies = {
    k: v for k, v in [
        x.split('=') for x in cookie.split(';')
    ]
}


import requests

def get(endpoint: str):
    API = 'https://api.thriva.co/v1'
    res = requests.get(
        API + endpoint,
        cookies=cookies
    )
    return res.json()

def result(tid: str):
    return get(f'/tests/{tid}?include=panel.profiles.analytes,result,result.analyte_results,result.attachments,report.analyte_comments,report.doctor,interventions,interventions.intervention_analytes')


def tests():
    # TODO does't work??
    # https://api.thriva.co/v1/tests?include=panel.profiles,panel.profiles.analytes,result,result.attachments,result.analyte_results,report.doctor,interventions,interventions.intervention_analytes&filter[state]=complete,active,scheduled
    pass


if __name__ == '__main__':
    pass
