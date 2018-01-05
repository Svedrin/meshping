#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

from __future__ import division

import sys
import socket

from redis import StrictRedis
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
                    redis.sadd("meshping:targets", "%s@%s" % (target, info[4][0]))
            else:
                redis.sadd("meshping:targets", target)

    elif options.delete:
        for target in posargs:
            if "@" not in target:
                for info in socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM):
                    redis.srem("meshping:targets", "%s@%s" % (target, info[4][0]))
            else:
                redis.srem("meshping:targets", target)

    else:
        for target in redis.smembers("meshping:targets"):
            print target


if __name__ == '__main__':
    sys.exit(main())
