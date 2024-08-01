import socket

from icmplib.sockets import ICMPv4Socket, ICMPSocketError
from icmplib.models  import ICMPRequest

# see /usr/include/linux/in.h
IP_MTU_DISCOVER = 10
IP_PMTUDISC_DO  =  2
IP_MTU          = 14
IP_HEADER_LEN   = 20
ICMP_HEADER_LEN =  8

# see /usr/include/linux/in6.h
IPV6_MTU_DISCOVER = 23
IPV6_PMTUDISC_DO  =  2
IPV6_MTU          = 24
IPV6_HEADER_LEN   = 40

UDP_HEADER_LEN    =  8

def reverse_lookup(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return ip


class PMTUDv4Socket(ICMPv4Socket):
    def _create_socket(self, type):
        sock = super(PMTUDv4Socket, self)._create_socket(type)
        sock.setsockopt(socket.IPPROTO_IP, IP_MTU_DISCOVER, IP_PMTUDISC_DO)
        return sock

    def get_mtu(self):
        return self._sock.getsockopt(socket.IPPROTO_IP, IP_MTU)

    def send(self, request):
        self._sock.connect((request.destination, 0))
        return super(PMTUDv4Socket, self).send(request)

def ipv4_pmtud(ip):
    mtu = 9999
    with PMTUDv4Socket(address=None, privileged=True) as sock:
        for sequence in range(30):
            request = ICMPRequest(
                destination  = ip,
                id           = 1337,
                sequence     = sequence,
                payload_size = mtu - IP_HEADER_LEN - ICMP_HEADER_LEN
            )
            try:
                # deliberately send a way-too-large packet to provoke an error
                sock.send(request)
                sock.receive(request, 1)
                break
            except ICMPSocketError as err:
                print("nay! %r" % err)
                if "Message too long" not in err.message:
                    raise

            mtu = sock.get_mtu()
            print("new mtu!", mtu)
            continue

    print("done:", mtu)
    return mtu


def ipv6_pmtud(ip):
    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IPV6, IPV6_MTU_DISCOVER, IPV6_PMTUDISC_DO)
    s.connect((ip, 99))

    try:
        # deliberately send a way-too-large packet to provoke an error
        s.send(b'#' * 9999)
    except socket.error:
        return s.getsockopt(socket.IPPROTO_IPV6, IPV6_MTU)
    else:
        raise ValueError("Path MTU not found")


def ip_pmtud(ip, default=None):
    # Prefer IPv6. If that doesn't work, fallback to v4.
    try:
        return ipv6_pmtud(ip)
    except socket.gaierror:
        # Host not found, try ipv4
        pass

    try:
        return ipv4_pmtud(ip)
    except socket.gaierror:
        return default
