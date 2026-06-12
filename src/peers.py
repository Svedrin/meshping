import os
import json
import logging
import httpx
import trio

from ifaces import Ifaces

async def run_peers(mp):
    peers = os.environ.get("MESHPING_PEERS", "")
    if peers:
        peers = peers.split(",")
    else:
        return

    while True:
        ifaces = Ifaces()

        peer_targets = [
            dict(
                name  = target.name,
                addr  = target.addr,
                local = ifaces.is_local(target.addr)
            )
            for target in mp.all_targets()
            if not target.is_foreign # ENOFORN
        ]

        async with httpx.AsyncClient() as client:
            for peer in peers:
                try:
                    await client.post(
                        f"http://{peer}/peer",
                        headers={
                            "Content-Type": "application/json"
                        },
                        data=json.dumps(dict(targets=peer_targets))
                    )
                except Exception as err:
                    logging.warning("Could not connect to peer %s: %s", peer, err)

        await trio.sleep(
            int(os.environ.get("MESHPING_PEERING_INTERVAL", 30))
        )
