import socket

# see /usr/include/linux/in.h
IP_MTU_DISCOVER = 10
IP_PMTUDISC_DO  =  2
IP_MTU          = 14

# see /usr/include/linux/in6.h
IPV6_MTU_DISCOVER = 23
IPV6_PMTUDISC_DO  =  2
IPV6_MTU          = 24


def reverse_lookup(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return ip


def ipv4_pmtud(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, IP_MTU_DISCOVER, IP_PMTUDISC_DO)
    s.connect((ip, 99))

    try:
        # deliberately send a way-too-large packet to provoke an error
        s.send(b'#' * 9999)
    except socket.error:
        return s.getsockopt(socket.IPPROTO_IP, IP_MTU)
    else:
        raise ValueError("Path MTU not found")


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
