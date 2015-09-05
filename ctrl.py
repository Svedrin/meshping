#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import os
import sys
import socket
import select
import json

from random import randint
from ping import send_one_ping, receive_one_ping
from time import sleep, time

def process_ctrl(ctrl, targets):
    rdy_read, _, _ = select.select([ctrl], [], [], 0.1)
    if ctrl not in rdy_read:
        return # nothing to do

    pkt, addr = ctrl.recvfrom(4096)
    try:
        data = json.loads(pkt)
    except ValueError:
        ctrl.sendto('{"status": "you suck"}', addr)
        return

    if "cmd" not in data:
        ctrl.sendto('{"status": "you suck"}', addr)
        return

    if data["cmd"] == "list":
        ctrl.sendto(json.dumps(targets), addr)
        if data.get("reset", False):
            for tgt in targets.values():
                tgt.update({
                    "sent": 0,
                    "recv": 0,
                    "errs": 0,
                    "outd": 0,
                    "last": 0,
                    "avg":  0,
                    "min":  0,
                    "max":  0,
                })
