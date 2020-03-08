#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

from __future__ import division

import sys
import socket

from redis    import StrictRedis
from optparse import OptionParser

def main():
    parser = OptionParser(usage="Usage: %prog [options] -- no options = list")

    parser.add_option("-d", "--delete",    help="remove target",    default=False, action="store_true")
    parser.add_option("-a", "--add",       help="add target",       default=False, action="store_true")
    parser.add_option("-r", "--redishost", help="Redis Host [127.0.0.1]", default="127.0.0.1")
    options, posargs = parser.parse_args()

    redis = StrictRedis(host=options.redishost)

    if options.add:
        for target in posargs:
            if "@" not in target:
                for info in socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM):
                    target_with_addr = "%s@%s" % (target, info[4][0])
                    redis.sadd("meshping:targets", target_with_addr)
                    redis.srem("meshping:foreign_targets", target_with_addr)
                    print(target_with_addr)
            else:
                redis.sadd("meshping:targets", target)
                redis.srem("meshping:foreign_targets", target)
                print(target)

    elif options.delete:
        for target in redis.smembers("meshping:targets"):
            target = target.decode("utf-8")
            for arg in posargs:
                if "@" in arg:
                    if target == arg:
                        redis.srem("meshping:targets", target)
                        print(target)
                else:
                    name, addr = target.split("@", 1)
                    if name == arg or addr == arg:
                        redis.srem("meshping:targets", target)
                        print(target)

    else:
        forn_targets = set([
            target.decode("utf-8")
            for target in redis.smembers("meshping:foreign_targets")
        ])
        for target in sorted(redis.smembers("meshping:targets")):
            target = target.decode("utf-8")
            if target in forn_targets:
                print("%s (FOREIGN)" % target)
            else:
                print(target)


if __name__ == '__main__':
    sys.exit(main())
