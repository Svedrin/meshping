import socket
import ipaddress
import netifaces

class Ifaces4:
    def __init__(self):
        self.networks = []
        # Get addresses from our interfaces
        for iface in netifaces.interfaces():
            for family, addresses in netifaces.ifaddresses(iface).items():
                if family != socket.AF_INET:
                    continue

                for addrinfo in addresses:
                    self.networks.append(
                        ipaddress.IPv4Network("%s/%s" % (
                            ipaddress.ip_address(addrinfo["addr"]),
                            ipaddress.ip_address(addrinfo["netmask"])
                        ), strict=False)
                    )

    def find_iface_for_network(self, target):
        target = ipaddress.IPv4Address(target)
        for addr in self.networks:
            if target in addr:
                return addr
        return None

    def is_local(self, target):
        return self.find_iface_for_network(target) is not None

class Ifaces6:
    def __init__(self):
        self.networks = []
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

                    self.networks.append(
                        ipaddress.IPv6Network("%s/%d" % (
                            ipaddress.ip_address(addrinfo["addr"]),
                            addrinfo["netmask"]
                        ), strict=False)
                    )

    def find_iface_for_network(self, target):
        target = ipaddress.IPv6Address(target)
        for addr in self.networks:
            if target in addr:
                return addr
        return None

    def is_local(self, target):
        return self.find_iface_for_network(target) is not None


def test():
    if4 = Ifaces4()
    for target in ("192.168.0.1", "10.159.1.1", "10.159.1.2", "10.5.1.2", "10.9.9.9", "8.8.8.8", "192.168.44.150"):
        print("%s -> %s" % (target, if4.is_local(target)))

    if6 = Ifaces6()
    for target in ("2001:4860:4860::8888", "2001:4860:4860::8844", "::1"):
        print("%s -> %s" % (target, if6.is_local(target)))

if __name__ == '__main__':
    test()
