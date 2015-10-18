#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

from __future__ import division

import os
import sys
import socket

try:
    import cjson as json
except ImportError:
    import json

from random import randint
from oping import PingObj
from time import sleep, time
from optparse import OptionParser

from ctrl import process_ctrl

def main():
    if os.getuid() != 0:
        raise RuntimeError("need to be root, sorry about that")

    ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
    ctrl.bind(("127.0.0.1", 55432))

    targets = {}

    parser = OptionParser("Usage: %prog [options] <target ...>")
    parser.add_option(
        "-i", "--interval", help="Interval in which pings are sent", type=int, default=30
    )
    options, posargs = parser.parse_args()

    pingobj = PingObj()

    for target in posargs:
        for info in socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM):
            pingobj.add_host(info[4][0])

    try:
        while True:
            now = time()
            next_ping = now + options.interval

            process_ctrl(ctrl, targets, pingobj)

            pingobj.send()

            for hostinfo in pingobj.get_hosts():
                target = targets.setdefault(hostinfo["addr"], {
                    "name": hostinfo["name"],
                    "addr": hostinfo["addr"],
                    "sent": 0,
                    "lost": 0,
                    "recv": 0,
                    "last": 0,
                    "sum":  0,
                    "min":  0,
                    "max":  0
                })

                target["sent"] += 1

                if hostinfo["latency"] != -1:
                    target["recv"] += 1
                    if target["recv"] > target["sent"]:
                        # can happen if sent is reset after a ping has been sent out, but before its answer arrives
                        target["sent"] = target["recv"]
                    target["last"]  = hostinfo["latency"]
                    target["sum"]  += target["last"]
                    target["max"]   = max(target["max"], target["last"])

                    if target["min"] == 0:
                        target["min"] = target["last"]
                    else:
                        target["min"] = min(target["min"], target["last"])

                else:
                    target["lost"] += 1
                    if target["lost"] > target["sent"]:
                        # can happen if sent is reset after a ping has been sent out, but before its answer arrives
                        target["sent"] = target["lost"]

            if time() < next_ping:
                sleep(next_ping - time())

    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
