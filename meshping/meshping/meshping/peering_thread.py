import json
import logging
import time
from threading import Thread
import requests
from .ifaces import Ifaces4, Ifaces6
from ..models import Target, Meta


# TODO test this code, has not even run once


class PeeringThread(Thread):
    def __init__(self, mp_config, *args, **kwargs):
        self.mp_config = mp_config
        super().__init__(*args, **kwargs)

    def run(self):
        if self.mp_config.peers:
            peers = self.mp_config.peers.split(",")
        else:
            return

        while True:
            if4 = Ifaces4()
            if6 = Ifaces6()

            def is_local(addr):
                try:
                    return if4.is_local(addr)
                except ValueError:
                    pass
                try:
                    return if6.is_local(addr)
                except ValueError:
                    pass
                return False

            peer_targets = []

            # TODO feels clumsy to get the meta objects one by one, maybe there is a
            #      more elegant way, i.e. something that maps to a join under the hood?
            for target in Target.objects.all():
                target_meta, _created = Meta.objects.get_or_create(target=target)
                if target_meta.is_foreign:
                    continue
                peer_targets.append(
                    {
                        "name": target.name,
                        "addr": target.addr,
                        "local": is_local(target.addr),
                    }
                )

            for peer in peers:
                try:
                    requests.post(
                        f"http://{peer}/peer",
                        headers={
                            "Content-Type": "application/json",
                        },
                        data=json.dumps({"targets": peer_targets}),
                        timeout=self.mp_config.peering_timeout,
                    )
                # TODO decide if this general exception catch is the correct way
                # pylint: disable=broad-exception-caught
                except Exception as err:
                    logging.warning("Could not connect to peer %s: %s", peer, err)

            time.sleep(self.mp_config.peering_interval)
