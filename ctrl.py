# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import os
import sys
import socket
import select
import json

from random import randint
from time import sleep, time

def process_ctrl(ctrl, targets):
    rdy_read, _, _ = select.select([ctrl], [], [], 0)
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

    if data["cmd"] == "noop":
        ctrl.sendto('{"status": "mkay"}', addr)

    elif data["cmd"] == "list":
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
                    "due":  0,
                })

    elif data["cmd"] == "add":
        if "name" not in data and "addr" not in data:
            ctrl.sendto('{"status": "you suck"}', addr)
            return

        target_name = data.get("name", data.get("addr", ""))
        target_addr = data.get("addr", data.get("name", ""))
        for info in socket.getaddrinfo(target_addr, 0, socket.AF_INET, socket.SOCK_STREAM):
            # dubs. check'em.
            for key, tgt in targets.items():
                if tgt["addr"] == info[4][0]:
                    break
            else:
                # try to avoid pid collisions
                tgt_id = randint(0x8000 + 1, 0xFFFF)
                while tgt_id in targets:
                    tgt_id = randint(0x8000 + 1, 0xFFFF)
                tgt = {
                    "addr": info[4][0],
                    "name": target_name,
                    "sent": 0,
                    "recv": 0,
                    "errs": 0,
                    "outd": 0,
                    "id":   tgt_id,
                    "last": 0,
                    "avg":  0,
                    "min":  0,
                    "max":  0,
                    "itv":  data.get("itv", 1),
                    "due":  0
                }
                targets[tgt_id] = tgt
        ctrl.sendto('{"status": "mkay"}', addr)

    elif data["cmd"] == "remove":
        if "name" not in data and "addr" not in data:
            ctrl.sendto('{"status": "you suck"}', addr)
            return

        if "name" in data:
            for key, tgt in targets.items():
                if tgt["name"] == data["name"]:
                    del targets[key]

        if "addr" in data:
            for key, tgt in targets.items():
                if tgt["addr"] == data["addr"]:
                    del targets[key]

        ctrl.sendto('{"status": "mkay"}', addr)

