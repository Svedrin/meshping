#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

from __future__ import division

import os
import os.path
import sys
import socket

try:
    import cjson as json
except ImportError:
    import json

from threading import Thread
from random import randint
from oping import PingObj
from time import sleep, time
from optparse import OptionParser
from Queue import Queue, Empty

from ctrl import process_ctrl

class MeshPing(object):
    def __init__(self, interval=30, timeout=1, logdir=None):
        self.addq = Queue()
        self.remq = Queue()
        self.rstq = Queue()
        self.targets = {}
        self.interval = interval
        self.timeout  = timeout
        self.logdir   = logdir

        self.pingdaemon = Thread(target=self.ping_daemon_runner)
        self.pingdaemon.daemon = True

        self.logfd = {}

    def start(self):
        self.pingdaemon.start()

    def is_alive(self):
        return self.pingdaemon.is_alive()

    def add_host(self, name, addr):
        for info in socket.getaddrinfo(addr, 0, 0, socket.SOCK_STREAM):
            if info[4][0] not in self.targets:
                self.addq.put((name, info[4][0], info[0]))

    def remove_host(self, name, addr):
        for info in socket.getaddrinfo(addr, 0, 0, socket.SOCK_STREAM):
            self.remq.put((name, info[4][0], info[0]))

    def reset_stats(self):
        self.rstq.put(True)

    def reset_stats_for_target(self, addr):
        self.targets[addr].update({
            "sent": 0,
            "lost": 0,
            "recv": 0,
            "last": 0,
            "sum":  0,
            "min":  0,
            "max":  0
        })


    def ping_daemon_runner(self):
        pingobj = PingObj()
        pingobj.set_timeout(self.timeout)

        next_ping = time() + 0.1

        while True:
            while time() < next_ping:
                # Process Host Add/Remove queues
                try:
                    while True:
                        name, addr, afam = self.addq.get(timeout=0.1)
                        pingobj.add_host(addr)
                        self.targets[addr] = {
                            "name": name,
                            "addr": addr,
                            "af":   afam
                        }
                        self.reset_stats_for_target(addr)
                except Empty:
                    pass

                try:
                    while True:
                        name, addr, afam = self.remq.get(timeout=0.1)
                        pingobj.remove_host(addr)
                        if addr in self.targets:
                            del self.targets[addr]
                except Empty:
                    pass

                try:
                    self.rstq.get(timeout=0.1)
                except Empty:
                    pass
                else:
                    for addr in self.targets:
                        self.reset_stats_for_target(addr)

            now = time()
            next_ping = now + self.interval

            pingobj.send()

            for hostinfo in pingobj.get_hosts():
                target = self.targets[hostinfo["addr"]]

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

                    if self.logdir:
                        if hostinfo["addr"] not in self.logfd:
                            self.logfd[hostinfo["addr"]] = open(os.path.join(self.logdir, hostinfo["addr"] + ".txt"), mode="a", buffering=False)

                        print >> self.logfd[hostinfo["addr"]], target["last"]

                else:
                    target["lost"] += 1
                    if target["lost"] > target["sent"]:
                        # can happen if sent is reset after a ping has been sent out, but before its answer arrives
                        target["sent"] = target["lost"]



def main():
    if os.getuid() != 0:
        raise RuntimeError("need to be root, sorry about that")

    ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
    ctrl.bind(("127.0.0.1", 55432))

    parser = OptionParser("Usage: %prog [options] <target ...>")
    parser.add_option(
        "-i", "--interval", help="Interval in which pings are sent [30s]", type=int, default=30
    )
    parser.add_option(
        "-t", "--timeout",  help="Ping timeout [5s]", type=int, default=5
    )
    parser.add_option(
        "-l", "--logdir",   help="Log measurements to <addr>.txt files in this directory."
    )
    options, posargs = parser.parse_args()

    if options.logdir:
        options.logdir = os.path.abspath(options.logdir)
        if not os.path.exists(options.logdir):
            os.makedirs(options.logdir)

    mp = MeshPing(options.interval, options.timeout, options.logdir)

    for target in posargs:
        mp.add_host(target, target)

    try:
        mp.start()

        while mp.is_alive():
            process_ctrl(ctrl, mp)

    except KeyboardInterrupt:
        pass

    finally:
        del mp
        ctrl.close()

if __name__ == '__main__':
    main()
