# encoding: utf-8

import json
import requests

from time import sleep
from behave import given, when, then

@when('we wait {n:d} seconds')
def step(context, n):
    sleep(n)

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

@when('we delete a target of "{address}"')
def step(context, address):
    resp = requests.delete("http://meshping:9922/api/targets/%s" % address)
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

@then('there exists no target of "{address}"')
def step(context, address):
    resp = requests.get("http://meshping:9922/api/targets")
    resp.raise_for_status()
    assert resp.json()["success"] == True
    for target in resp.json()["targets"]:
        if target["addr"] == address and target["name"] == name:
            assert False, "target exists (it shouldn't)"

@when('we request a histogram for target "{address}"')
def step(context, address):
    context.resp = requests.get("http://meshping:9922/histogram/obsolete/%s.png" % address)

@then('we get a response with status code {status:d}')
def step(context, status):
    assert context.resp.status_code, status
