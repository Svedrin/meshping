from time import sleep

import os
import json
import traceback
import requests

from ifaces import Ifaces4

def run_peers(mp):
    peers = os.environ.get("MESHPING_PEERS", "")
    if peers:
        peers = peers.split(",")
    else:
        return

    while True:
        if4 = Ifaces4()
        forn_targets = [
            target.decode("utf-8")
            for target in mp.redis.smembers("meshping:foreign_targets")
        ]
        peer_targets = [
            dict(
                name  = target["name"],
                addr  = target["addr"],
                local = if4.is_local(target["addr"])
            )
            for target in mp.targets.values()
            if ("%(name)s@%(addr)s" % target) not in forn_targets # ENOFORN
        ]

        for peer in peers:
            try:
                requests.post(
                    "http://%s/peer" % peer,
                    headers={
                        "Content-Type": "application/json"
                    },
                    data=json.dumps(dict(targets=peer_targets))
                )
            except:
                traceback.print_exc()

        sleep(30)
