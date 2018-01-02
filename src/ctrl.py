# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import os
import sys
import socket
import select
import json

from random import randint
from time import sleep, time

def process_ctrl(ctrl, mp):
    rdy_read, _, _ = select.select([ctrl], [], [], 0.5)
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

    elif data["cmd"] == "histogram":
        if "addr" not in data:
            ctrl.sendto('{"status": "need addr variable"}', addr)
            return
        ctrl.sendto(json.dumps(mp.histograms.get(data["addr"], {})), addr)

    elif data["cmd"] == "add":
        if "name" not in data and "addr" not in data:
            ctrl.sendto('{"status": "need name or addr variable"}', addr)
            return

        target_name = data.get("name", data.get("addr", ""))
        target_addr = data.get("addr", data.get("name", ""))

        try:
            mp.add_host(target_name, target_addr)
        except socket.gaierror, err:
            ctrl.sendto('{"status": "error", "errmessage": "' + err.args[1] + '"}', addr)
            return

        ctrl.sendto('{"status": "ok"}', addr)

    elif data["cmd"] == "remove":
        if "name" not in data and "addr" not in data:
            ctrl.sendto('{"status": "need name or addr variable"}', addr)
            return

        target_name = data.get("name", data.get("addr", ""))
        target_addr = data.get("addr", data.get("name", ""))

        try:
            mp.remove_host(target_name, target_addr)
        except socket.gaierror, err:
            ctrl.sendto('{"status": "error", "errmessage": "' + err.args[1] + '"}', addr)
            return

        ctrl.sendto('{"status": "ok"}', addr)

