import socket

from icmplib.sockets    import ICMPv4Socket, ICMPv6Socket
from icmplib.exceptions import ICMPSocketError, TimeoutExceeded
from icmplib.models     import ICMPRequest
from icmplib.utils      import unique_identifier

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
ICMPV6_HEADER_LEN =  8

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

    def get_header_len(self):
        return IP_HEADER_LEN + ICMP_HEADER_LEN

    def get_mtu(self):
        return self._sock.getsockopt(socket.IPPROTO_IP, IP_MTU)

    def send(self, request):
        self._sock.connect((request.destination, 0))
        return super(PMTUDv4Socket, self).send(request)


class PMTUDv6Socket(ICMPv6Socket):
    def _create_socket(self, type):
        sock = super(PMTUDv6Socket, self)._create_socket(type)
        sock.setsockopt(socket.IPPROTO_IPV6, IPV6_MTU_DISCOVER,    IPV6_PMTUDISC_DO)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_DONTFRAG, 1)
        return sock

    def get_header_len(self):
        return IPV6_HEADER_LEN + ICMPV6_HEADER_LEN

    def get_mtu(self):
        return self._sock.getsockopt(socket.IPPROTO_IPV6, IPV6_MTU)

    def send(self, request):
        self._sock.connect((request.destination, 0))
        return super(PMTUDv6Socket, self).send(request)


def ip_pmtud(ip, default=None):
    try:
        addrinfo = socket.getaddrinfo(ip, 0, type=socket.SOCK_DGRAM)[0]
    except socket.gaierror:
        return default

    if addrinfo[0] == socket.AF_INET6:
        sock = PMTUDv6Socket(address=None, privileged=True)
    else:
        sock = PMTUDv4Socket(address=None, privileged=True)

    mtu = 9999
    with sock:
        ping_id = unique_identifier()
        for sequence in range(30):
            request = ICMPRequest(
                destination  = ip,
                id           = ping_id,
                sequence     = sequence,
                payload_size = mtu - sock.get_header_len()
            )
            try:
                # deliberately send a way-too-large packet to provoke an error.
                # if the ping is successful, we found the MTU.
                sock.send(request)
                sock.receive(request, 1)
                print(ip, "success, done:", mtu)
                return mtu

            except TimeoutExceeded:
                # Target down, but no error -> MTU is probably fine.
                print(ip, "down, done:", mtu)
                return mtu

            except ICMPSocketError as err:
                print(ip, mtu, err)
                if "Errno 90" not in str(err):
                    raise

            new_mtu = sock.get_mtu()
            if new_mtu == mtu:
                break
            mtu = new_mtu
            print(ip, "new mtu!", mtu)

    print(ip, "done:", mtu)
    return mtu
