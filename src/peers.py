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
        peer_targets = []

        for target in mp.targets.values():
            peer_targets.append(dict(
                name  = target["name"],
                addr  = target["addr"],
                local = if4.is_local(target["addr"])
            ))

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
