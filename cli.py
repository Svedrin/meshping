#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

from __future__ import division

import sys
import json
import struct
import socket

from optparse import OptionParser
from select   import select

def main():
    parser = OptionParser(usage="Usage: %prog [options] -- no options = list without reset")

    parser.add_option("-j", "--json",     help="Output the reply", default=False, action="store_true")
    parser.add_option("-r", "--reset",    help="Reset statistics", default=False, action="store_true")
    parser.add_option("-d", "--delete",   help="remove target",    default=False, action="store_true")
    parser.add_option("-a", "--add",      help="add target",       default=False, action="store_true")
    parser.add_option("-t", "--name",     help="target name",      default="")
    parser.add_option("-T", "--address",  help="target address",   default="")
    parser.add_option("-i", "--interval", help="ping interval",    type=int, default=30)
    parser.add_option("-A", "--addscript",help="generate host add script for the currently configured hosts", default=False, action="store_true")

    options, posargs = parser.parse_args()

    ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)

    if options.add:
        opts = {
            "cmd":    "add",
            "itv":    options.interval,
        }
        if options.name:
            opts["name"] = options.name
        if options.address:
            opts["addr"] = options.address
        ctrl.sendto(json.dumps(opts), ("127.0.0.1", 55432) )

    elif options.delete:
        opts = {
            "cmd":    "remove",
            "itv":    options.interval,
        }
        if options.name:
            opts["name"] = options.name
        if options.address:
            opts["addr"] = options.address
        ctrl.sendto(json.dumps(opts), ("127.0.0.1", 55432) )

    else:
        ctrl.sendto( json.dumps({
            "cmd":    "list",
            "reset":  options.reset,
        }), ("127.0.0.1", 55432) )

    rdy_read, _, _ = select([ctrl], [], [], 5)
    if ctrl in rdy_read:
        reply, addr = ctrl.recvfrom(2**14)

        if options.json or options.add or options.delete:
            print json.dumps(json.loads(reply), indent=4)

        else:
            targets = json.loads(reply)

            if options.addscript:
                for targetinfo in targets.values():
                    print "%s -a -t %s -T %s" % (sys.argv[0], targetinfo["name"], targetinfo["addr"])
                return

            print "Target                     Sent  Recv   Succ    Loss      Avg       Min       Max      Last"

            def ip_as_int(tgt):
                return struct.unpack("!I", socket.inet_aton( tgt["addr"] ))[0]

            for targetinfo in targets.values(): #sorted(targets.values(), key=ip_as_int):
                loss = 0
                errs = 0
                if targetinfo["sent"]:
                    loss = (targetinfo["sent"] - targetinfo["recv"]) / targetinfo["sent"] * 100
                avg = 0
                if targetinfo["recv"]:
                    avg = targetinfo["sum"] / targetinfo["recv"]
                outd = 0
                print "%-25s %5d %5d %6.2f%% %6.2f%% %7.2f   %7.2f   %7.2f   %7.2f" % (
                    targetinfo["addr"], targetinfo["sent"], targetinfo["recv"], 100 - loss, loss,
                    avg, targetinfo["min"], targetinfo["max"], targetinfo["last"])

    else:
        print "timeout, is meshping running?"


if __name__ == '__main__':
    sys.exit(main())
