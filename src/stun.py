# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

"""Minimal STUN (RFC 8489) client, just enough to ask a server which public
address it sees us coming from."""

import ipaddress
import logging
import os
import socket
import struct
import time

MAGIC_COOKIE    = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0101
ATTR_MAPPED     = 0x0001   # legacy RFC 3489 form, some old servers only send this
ATTR_XOR_MAPPED = 0x0020

def parse_binding_response(data, txid):
    """Return the mapped address from a Binding response as a string, or None
    if `data` isn't a successful response to the request with `txid`."""
    if len(data) < 20:
        return None

    msg_type, msg_len, cookie, resp_txid = struct.unpack("!HHI12s", data[:20])
    if msg_type != BINDING_SUCCESS or cookie != MAGIC_COOKIE or resp_txid != txid:
        return None

    body = data[20:20 + msg_len]
    pos  = 0
    while pos + 4 <= len(body):
        attr_type, attr_len = struct.unpack("!HH", body[pos:pos + 4])
        value = body[pos + 4:pos + 4 + attr_len]
        pos  += 4 + ((attr_len + 3) & ~3)   # attributes are padded to 4 bytes

        if attr_type not in (ATTR_XOR_MAPPED, ATTR_MAPPED) or len(value) < 4:
            continue

        family, raw = value[1], value[4:]
        if attr_type == ATTR_XOR_MAPPED:
            mask = struct.pack("!I", MAGIC_COOKIE) + txid
            raw  = bytes(a ^ b for a, b in zip(raw, mask))

        if family == 1 and len(raw) == 4:
            return str(ipaddress.IPv4Address(raw))
        if family == 2 and len(raw) == 16:
            return str(ipaddress.IPv6Address(raw))

    return None

def query_public_ip(host, port, timeout=2.0, attempts=2):
    """Ask the STUN server at host:port for our public IP. Returns it as a
    string, or None if the server couldn't be reached or didn't answer.
    Blocking, so run it in a thread from async code."""
    try:
        candidates = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror as err:
        logging.warning("STUN: could not resolve %s: %s", host, err)
        return None

    for family, socktype, proto, _, sockaddr in candidates:
        txid    = os.urandom(12)
        request = struct.pack("!HHI12s", BINDING_REQUEST, 0, MAGIC_COOKIE, txid)

        try:
            with socket.socket(family, socktype, proto) as sock:
                for _ in range(attempts):
                    sock.sendto(request, sockaddr)
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        sock.settimeout(max(deadline - time.monotonic(), 0.01))
                        try:
                            data, _ = sock.recvfrom(2048)
                        except socket.timeout:
                            break
                        addr = parse_binding_response(data, txid)
                        if addr is not None:
                            return addr
        except OSError as err:
            logging.warning("STUN: query to %s failed: %s", sockaddr[0], err)

    logging.warning("STUN: no usable answer from %s:%s", host, port)
    return None
