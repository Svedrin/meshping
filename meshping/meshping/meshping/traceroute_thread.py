import logging
import time
from threading import Thread
from icmplib import traceroute
from ipwhois import IPWhois, IPDefinedError
from netaddr import IPAddress, IPNetwork
from .socklib import reverse_lookup, ip_pmtud
from ..models import Target, Meta


class TracerouteThread(Thread):
    def __init__(self, mp_config, *args, **kwargs):
        self.mp_config = mp_config
        self.whois_cache = {}
        super().__init__(*args, **kwargs)

    def whois(self, hop_address):
        # If we know this address already and it's up-to-date, skip it
        now = int(time.time())
        if (
            hop_address in self.whois_cache
            and self.whois_cache[hop_address].get("last_check", 0)
            + self.mp_config.whois_cache_validiy_h * 3600
            < now
        ):
            return self.whois_cache[hop_address]

        # Check if the IP is private or reserved
        addr = IPAddress(hop_address)
        # TODO split out into separate function and allow configuration
        # pylint: disable=too-many-boolean-expressions
        if (
            addr.version == 4
            and (
                addr in IPNetwork("10.0.0.0/8")
                or addr in IPNetwork("172.16.0.0/12")
                or addr in IPNetwork("192.168.0.0/16")
                or addr in IPNetwork("100.64.0.0/10")
            )
        ) or (addr.version == 6 and addr not in IPNetwork("2000::/3")):
            return {}

        # It's not, look up whois info
        try:
            self.whois_cache[hop_address] = dict(
                IPWhois(hop_address).lookup_rdap(), last_check=now
            )
        except IPDefinedError:
            # RFC1918, RFC6598 or something else
            return {}
        # we do not have a global exception handler atm, thus we want to catch all
        # errors here
        # pylint: disable=broad-exception-caught
        except Exception as err:
            logging.warning("Could not query whois for IP %s: %s", hop_address, err)
        return self.whois_cache[hop_address]

    def run(self):
        while True:
            now = time.time()
            next_run = now + self.mp_config.traceroute_interval
            pmtud_cache = {}
            for target in Target.objects.all():
                target_meta, _created = Meta.objects.get_or_create(target=target)

                trace = traceroute(
                    target.addr,
                    fast=True,
                    timeout=self.mp_config.traceroute_timeout,
                    count=self.mp_config.traceroute_packets,
                )
                hopaddrs = [hop.address for hop in trace]
                hoaddrs_set = set(hopaddrs)
                target_meta.route_loop = (
                    len(hopaddrs) != len(hoaddrs_set) and len(hoaddrs_set) > 1
                )

                trace_hops = []
                for hop in trace:
                    if hop.address not in pmtud_cache:
                        pmtud_cache[hop.address] = ip_pmtud(hop.address)

                    trace_hops.append(
                        {
                            "name": reverse_lookup(hop.address),
                            "distance": hop.distance,
                            "address": hop.address,
                            "max_rtt": hop.max_rtt,
                            "pmtud": pmtud_cache[hop.address],
                            "whois": self.whois(hop.address),
                            "time": now,
                        }
                    )

                target_meta.traceroute = trace_hops
                if trace_hops and trace_hops[-1]["address"] == target.addr:
                    # Store last known good traceroute
                    target_meta.lkgt = trace_hops

                # Running a bunch'a traceroutes all at once might trigger our default
                # gw's rate limiting if it receives too many packets with a ttl of 1
                # too quickly. Let's go a bit slower so that it doesn't stop sending
                # "ttl exceeded" replies and messing up our results.
                time.sleep(self.mp_config.traceroute_ratelimit_interval)

                target_meta.save()

            time.sleep(max(0, next_run - time.time()))
