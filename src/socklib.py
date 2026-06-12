import socket

from time import sleep

from icmplib.sockets    import ICMPv4Socket, ICMPv6Socket
from icmplib.exceptions import ICMPSocketError, TimeoutExceeded, TimeExceeded, ICMPLibError
from icmplib.models     import ICMPRequest, Hop
from icmplib.utils      import unique_identifier, resolve, is_hostname, is_ipv6_address

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
        sock = super()._create_socket(type)
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
        sock = super()._create_socket(type)
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


def ip_pmtud(ip):
    mtu = 9999

    try:
        addrinfo = socket.getaddrinfo(ip, 0, type=socket.SOCK_DGRAM)[0]
    except socket.gaierror as err:
        return {"state": "error", "error": str(err), "mtu": mtu}

    if addrinfo[0] == socket.AF_INET6:
        sock = PMTUDv6Socket(address=None, privileged=True)
    else:
        sock = PMTUDv4Socket(address=None, privileged=True)

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
                return {"state": "up", "mtu": mtu}

            except TimeoutExceeded:
                # Target down, but no error -> MTU is probably fine.
                return {"state": "down", "mtu": mtu}

            except (ICMPSocketError, OSError) as err:
                if "Errno 90" not in str(err):
                    return {"state": "error", "error": str(err), "mtu": mtu}

            new_mtu = sock.get_mtu()
            if new_mtu == mtu:
                break
            mtu = new_mtu

    return {"state": "ttl_exceeded", "mtu": mtu}


def traceroute(address, count=2, interval=0.05, timeout=2, first_hop=1,
        max_hops=30, fast=False, id=None, source=None, family=None,
        **kwargs):
    '''
    Drop-in replacement for icmplib's traceroute().

    icmplib computes `id = id or unique_identifier()` once before the
    loop, so every probe of the trace shares the same (id, sequence) pair
    (with the default count=1, sequence is always 0 too). Sockets match
    replies purely by (id, sequence) without checking which probe an ICMP
    error actually refers to, so a late or duplicate reply to an earlier
    probe can get matched to a later one, making an earlier hop's address
    appear to repeat further down the route, even though no such hop
    actually exists.

    Here, every probe gets its own unique id (unless the caller passed an
    explicit `id`), so a stale reply to an earlier probe no longer matches
    a later request and is simply ignored.

    '''
    if is_hostname(address):
        address = resolve(address, family)[0]

    if is_ipv6_address(address):
        _Socket = ICMPv6Socket
    else:
        _Socket = ICMPv4Socket

    ttl = first_hop
    host_reached = False
    hops = []

    with _Socket(source) as sock:
        while not host_reached and ttl <= max_hops:
            reply = None
            packets_sent = 0
            rtts = []
            # Generate a new id for each iteration so that a delayed answer to TTL=1/seq=0
            # does not count as a result for TTL=2/seq=0.
            id = unique_identifier()

            for sequence in range(count):
                request = ICMPRequest(
                    destination=address,
                    id=id,
                    sequence=sequence,
                    ttl=ttl,
                    **kwargs)

                try:
                    sock.send(request)
                    packets_sent += 1

                    reply = sock.receive(request, timeout)
                    rtts.append((reply.time - request.time) * 1000)

                    reply.raise_for_status()
                    host_reached = True

                except TimeExceeded:
                    sleep(interval)

                except ICMPLibError:
                    break

            if reply:
                hop = Hop(
                    address=reply.source,
                    packets_sent=packets_sent,
                    rtts=rtts,
                    distance=ttl)

                hops.append(hop)

            ttl += 1

    return hops
