#!/usr/bin/env python3
import sys

import requests

from thriva_secrets import cookie

# meh
cookies = {
    k: v for k, v in [
        x.split('=') for x in cookie.split(';')
    ]
}

API = 'https://api.thriva.co/v1'


def get(endpoint: str):
    res = requests.get(
        API + endpoint,
        cookies=cookies
    )
    j = res.json()
    assert j is not None
    return j


def result(tid: str):
    return get(f'/tests/{tid}?include=panel.profiles.analytes,result,result.analyte_results,result.attachments,report.analyte_comments,report.doctor,interventions,interventions.intervention_analytes')


# TODO pagination??
def tests():
    # TODO no idea why this vvvv doesn't work. it results in empty body...
    # return get('tests?include=panel.profiles,panel.profiles.analytes,result,result.attachments,result.analyte_results,report.doctor,interventions,interventions.intervention_analytes&filter[state]=complete,active,scheduled')
    print('Go to https://app.thriva.co/tests')
    print('open the inspector console and execute:')
    code = '''
    res = await fetch('https://api.thriva.co/v1/tests?include=panel.profiles,panel.profiles.analytes,result,result.attachments,result.analyte_results,report.doctor,interventions,interventions.intervention_analytes&filter[state]=complete,active,scheduled',  {method: 'GET', credentials: "include"})
    json = await res.json()
    json.data.map(x => x.id).join(' ')
'''
    print(code)
    idss = input('Insert the results here: ')
    ids = idss.strip().strip('"').split()
    return ids


def export():
    results = {}
    # TODO crap. it still returns None for past tests...
    for tid in tests():
        results[tid] = result(tid)
    print(results)


if __name__ == '__main__':
    export()
