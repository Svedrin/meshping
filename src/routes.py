import struct
import socket
import ipaddress
import netifaces

class Routes4:
    RTF_REJECT = 0x200 # for "unreachable" routes
    COLUMNS = (
        "Iface", "Destination", "Gateway", "Flags", "RefCnt", "Use",
        "Metric", "Mask", "MTU", "Window", "IRTT"
    )
    ADDR_COLUMNS = ("Destination", "Gateway", "Mask")
    HEX_COLUMNS  = ("Flags",)
    INT_COLUMNS  = ("RefCnt", "Use", "Metric", "MTU", "Window", "IRTT")

    def __init__(self):
        # Get the routing table from the Kernel and store it.
        self.routes = {}

        # Get addresses from our interfaces
        for iface in netifaces.interfaces():
            for family, addresses in netifaces.ifaddresses(iface).items():
                if family != socket.AF_INET:
                    continue

                for addrinfo in addresses:
                    route = dict(
                        Family = socket.AF_INET,
                        Iface  = iface,
                        Destination = ipaddress.IPv4Network("%s/%s" % (
                            ipaddress.ip_address(addrinfo["addr"]),
                            ipaddress.ip_address(addrinfo["netmask"])
                        ), strict=False),
                        Gateway = None,
                        Flags   = 0,
                        RefCnt  = 0,
                        Use     = 0,
                        Metric  = 0,
                        Mask    = struct.unpack("!I", socket.inet_aton(addrinfo["netmask"]))[0],
                        MTU     = 0,
                        Window  = 0,
                        IRTT    = 0
                    )
                    self.routes[route["Destination"]] = route

        with open("/proc/net/route", "r") as routes_fd:
            for line in routes_fd:
                if not line or line.startswith("Iface"):
                    continue

                route = dict(zip(Routes4.COLUMNS, line.strip().split()))
                route["Family"] = socket.AF_INET

                for addr_field in Routes4.ADDR_COLUMNS:
                    route[addr_field] = socket.htonl(int(route[addr_field], 16))
                for hex_field in Routes4.HEX_COLUMNS:
                    route[hex_field] = int(route[hex_field], 16)
                for int_field in Routes4.INT_COLUMNS:
                    route[int_field] = int(route[int_field], 10)

                route["Destination"] = ipaddress.IPv4Network("%s/%s" % (
                    ipaddress.ip_address(route["Destination"]),
                    ipaddress.ip_address(route["Mask"])
                ))

                if route["Gateway"] != 0:
                    route["Gateway"] = ipaddress.ip_address(route["Gateway"])
                else:
                    route["Gateway"] = None

                self.routes[route["Destination"]] = route

    def get_route_for_host(self, target):
        target = ipaddress.IPv4Address(target)
        best_match = None

        for _, route in self.routes.items():
            if target not in route["Destination"]:
                continue
            if best_match is None:
                continue
            assert isinstance(best_match, dict)
            if route["Destination"].subnet_of(best_match["Destination"]):
                best_match = route
                #print("%s -- %s via %s dev %s metric %d" % (
                    #target, best_match["Destination"], best_match["Gateway"], best_match["Iface"], best_match["Metric"]
                #))

        if best_match["Flags"] & Routes4.RTF_REJECT:
            # The best match is a reject route that defines this address as unreachable.
            return None

        return best_match


class Routes6:
    COLUMNS = (
        "Destination", "DestinationPfxLen",
        "Source", "SourcePfxLen",
        "Gateway", "Metric", "RefCnt", "Use", "Flags", "Iface"
    )
    HEX_COLUMNS = (
        "Destination", "DestinationPfxLen",
        "Source", "SourcePfxLen",
        "Gateway", "Metric"
    )
    INT_COLUMNS = ("RefCnt", "Use", "Flags")

    def __init__(self):
        # Get the routing table from the Kernel and store it.
        self.routes = {}

        # Get addresses from our interfaces
        for iface in netifaces.interfaces():
            for family, addresses in netifaces.ifaddresses(iface).items():
                if family != socket.AF_INET6:
                    continue

                for addrinfo in addresses:
                    if "%" in addrinfo["addr"]:
                        part_addr, part_iface = addrinfo["addr"].split("%", 1)
                        assert part_iface == iface
                        addrinfo["addr"] = part_addr

                    # netmask is ffff:ffff:ffff:etc:ffff/128 for some reason, we only need the length
                    addrinfo["netmask"] = int(addrinfo["netmask"].split("/")[1], 10)

                    route = dict(
                        Family = socket.AF_INET6,
                        Iface  = iface,
                        Destination = ipaddress.IPv6Network("%s/%d" % (
                            ipaddress.ip_address(addrinfo["addr"]),
                            addrinfo["netmask"]
                        ), strict=False),
                        DestinationPfxLen = addrinfo["netmask"],
                        SourceNetwork = None,
                        SourcePfxLen  = 0,
                        Gateway = None,
                        Metric  = 0,
                        RefCnt  = 0,
                        Use     = 0,
                        Flags   = 0
                    )
                    self.routes[route["Destination"]] = route

        with open("/proc/net/ipv6_route", "r") as routes_fd:
            for line in routes_fd:
                route = dict(zip(Routes6.COLUMNS, line.strip().split()))
                route["Family"] = socket.AF_INET6

                for hex_field in Routes6.HEX_COLUMNS:
                    route[hex_field] = int(route[hex_field], 16)
                for int_field in Routes6.INT_COLUMNS:
                    route[int_field] = int(route[int_field], 10)

                if route["Metric"] == 0xFFFFFFFF:
                    continue

                route["Destination"] = ipaddress.IPv6Network("%s/%d" % (
                    ipaddress.IPv6Address(route["Destination"]),
                    route["DestinationPfxLen"]
                ))

                if route["Gateway"] != 0:
                    route["Gateway"] = ipaddress.ip_address(route["Gateway"])
                else:
                    route["Gateway"] = None

                self.routes[route["Destination"]] = route

    def get_route_for_host(self, target):
        target = ipaddress.IPv6Address(target)
        best_match = None

        for _, route in self.routes.items():
            if target not in route["Destination"]:
                continue
            if best_match is None or route["Destination"].subnet_of(best_match["Destination"]):
                best_match = route
                #print("%s -- %s via %s dev %s metric %d" % (
                    #target, best_match["Destination"], best_match["Gateway"], best_match["Iface"], best_match["Metric"]
                #))

        return best_match


def test():
    routes4 = Routes4()

    for target in ("192.168.0.1", "10.159.1.1", "10.159.1.2", "10.5.1.2", "10.9.9.9", "8.8.8.8"):
        best_match = routes4.get_route_for_host(target)
        if best_match is not None:
            print("%s -- %s via %s dev %s metric %d" % (
                target, best_match["Destination"], best_match["Gateway"], best_match["Iface"], best_match["Metric"]
            ))
        else:
            print("%s -- no route to host" % target)


    routes6 = Routes6()

    for target in ("2001:4860:4860::8888", "2001:4860:4860::8844"):
        best_match = routes6.get_route_for_host(target)
        if best_match is not None:
            print("%s -- %s via %s dev %s metric %d" % (
                target, best_match["Destination"], best_match["Gateway"], best_match["Iface"], best_match["Metric"]
            ))
        else:
            print("%s -- no route to host" % target)

if __name__ == '__main__':
    test()
