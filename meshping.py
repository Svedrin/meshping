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
from ping import send_one_ping, receive_one_ping
from time import sleep, time

from ctrl import process_ctrl

def main():
    ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
    ctrl.bind(("127.0.0.1", 55432))

    icmp = socket.getprotobyname("icmp")
    try:
        icmpv4 = socket.socket(socket.AF_INET,  socket.SOCK_RAW, icmp)
    except socket.error, (errno, msg):
        if errno == 1:
            # Operation not permitted
            msg = msg + (
                " - Note that ICMP messages can only be sent from processes"
                " running as root."
            )
            raise socket.error(msg)
        raise # raise the original error

    #os.setuid(os.getuid())
    os.setuid(1000)

    targets = {}
    sent_at = {}

    for target in sys.argv[1:]:
        try:
            if "/" in target:
                target, itv = target.split("/")
                itv = int(itv)
            else:
                itv = 1
            for info in socket.getaddrinfo(target, 0, socket.AF_INET, socket.SOCK_STREAM):
                # try to avoid pid collisions
                tgt_id = randint(0x8000 + 1, 0xFFFF)
                while tgt_id in targets:
                    tgt_id = randint(0x8000 + 1, 0xFFFF)
                tgt = {
                    "addr": info[4][0],
                    "name": target,
                    "sent": 0,
                    "recv": 0,
                    "errs": 0,
                    "outd": 0,
                    "id":   tgt_id,
                    "last": 0,
                    "sum":  0,
                    "min":  0,
                    "max":  0,
                    "itv":  itv,
                    "due":  0
                }
                targets[tgt_id] = tgt

        except socket.gaierror, e:
            print "failed. (socket error: '%s')" % e[1]
            continue

    try:
        seq = 0
        while True:
            now = time()
            next_ping = now + 1

            for targetinfo in targets.values():
                if now >= targetinfo["due"]:
                    send_one_ping(icmpv4, targetinfo["addr"], targetinfo["id"], seq)
                    sent_at[targetinfo["id"]] = time()
                    targetinfo["sent"] += 1
                    targetinfo["due"]   = now + targetinfo["itv"]

            while time() < next_ping:
                process_ctrl(ctrl, targets)

                response = receive_one_ping(icmpv4, 0.1, sent_at)

                if response["timeout"]:
                    # meh, retry
                    continue

                if "id" not in response or response["id"] not in targets:
                    # ignore, retry
                    continue

                target = targets[response["id"]]

                if response["seq"] != seq:
                    target["outd"] += 1

                if response["success"]:
                    target["recv"] += 1
                    if target["recv"] > target["sent"]:
                        # can happen if sent is reset after a ping has been sent out, but before its answer arrives
                        target["sent"] = target["recv"]
                    target["last"]  = response["delay"]
                    target["sum"]  += response["delay"]
                    target["min"]   = min(target["min"], response["delay"])
                    target["max"]   = max(target["max"], response["delay"])

                else:
                    target["errs"] += 1
                    if target["errs"] > target["sent"]:
                        # can happen if sent is reset after a ping has been sent out, but before its answer arrives
                        target["sent"] = target["errs"]

            seq += 1
            if seq >= 2**16:
                seq = 0
            if time() < next_ping:
                sleep(next_ping - time())

    except KeyboardInterrupt:
        pass

    finally:
        icmpv4.close()


if __name__ == '__main__':
    main()
