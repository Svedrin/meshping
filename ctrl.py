# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import os
import sys
import socket
import select
import json

from random import randint
from time import sleep, time

def process_ctrl(ctrl, targets, pingobj):
    rdy_read, _, _ = select.select([ctrl], [], [], 0)
    if ctrl not in rdy_read:
        return # nothing to do

    pkt, addr = ctrl.recvfrom(4096)
    try:
        data = json.loads(pkt)
    except ValueError:
        ctrl.sendto('{"status": "invalid json"}', addr)
        return

    if "cmd" not in data:
        ctrl.sendto('{"status": "need cmd variable"}', addr)
        return

    if data["cmd"] == "noop":
        ctrl.sendto('{"status": "ok"}', addr)

    elif data["cmd"] == "list":
        ctrl.sendto(json.dumps(targets), addr)
        if data.get("reset", False):
            for tgt in targets.values():
                tgt.update({
                    "sent": 0,
                    "recv": 0,
                    "lost": 0,
                    "last": 0,
                    "sum":  0,
                    "min":  0,
                    "max":  0,
                })

    elif data["cmd"] == "add":
        if "name" not in data and "addr" not in data:
            ctrl.sendto('{"status": "need name or addr variable"}', addr)
            return

        target_name = data.get("name", data.get("addr", ""))
        target_addr = data.get("addr", data.get("name", ""))

        try:
            addrs = socket.getaddrinfo(target_addr, 0, 0, socket.SOCK_STREAM)
        except socket.gaierror, err:
            ctrl.sendto('{"status": "error", "errmessage": "' + err.args[1] + '"}', addr)
            return

        for info in addrs:
            pingobj.add_host(info[4][0])

        ctrl.sendto('{"status": "ok"}', addr)

    elif data["cmd"] == "remove":
        if "name" not in data and "addr" not in data:
            ctrl.sendto('{"status": "need name or addr variable"}', addr)
            return

        target_name = data.get("name", data.get("addr", ""))
        target_addr = data.get("addr", data.get("name", ""))

        try:
            addrs = socket.getaddrinfo(target_addr, 0, 0, socket.SOCK_STREAM)
        except socket.gaierror, err:
            ctrl.sendto('{"status": "error", "errmessage": "' + err.args[1] + '"}', addr)
            return

        for info in addrs:
            pingobj.remove_host(info[4][0])
            if info[4][0] in targets:
                del targets[info[4][0]]

        ctrl.sendto('{"status": "ok"}', addr)

