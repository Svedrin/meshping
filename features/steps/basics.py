# encoding: utf-8

import json
import requests

from behave import given, when, then

@when('we add a target of "{address}" named "{name}"')
def step(context, address, name):
    resp = requests.post(
        "http://meshping:9922/api/targets",
        data=json.dumps({
            "target": "%s@%s" % (name, address)
        }),
        headers = {
            "Content-Type": "application/json"
        }
    )
    resp.raise_for_status()
    assert resp.json()["success"] == True

@then('there exists a target of "{address}" named "{name}"')
def step(context, address, name):
    resp = requests.get("http://meshping:9922/api/targets")
    resp.raise_for_status()
    assert resp.json()["success"] == True
    for target in resp.json()["targets"]:
        if target["addr"] == address and target["name"] == name:
            break
    else:
        assert False, "target does not exist"
