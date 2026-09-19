# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

# STUN server used to find out our public IP address, in case none of our
# network interfaces has one (i.e. we're behind NAT). Format: (host, port).
#
# Nextcloud is EU-funded and doesn't route this through the big US tech
# companies. If it is unreachable, these are known alternatives:
#
#   ("stun.cloudflare.com",      3478)   # Cloudflare (US)
#   ("stun.l.google.com",       19302)   # Google (US); stun1..stun4 exist too
#   ("stun.sipgate.net",         3478)   # sipgate (DE), a commercial VoIP provider
#   ("stun.stunprotocol.org",    3478)   # community-run, please go easy on it
STUN_SERVER = ("stun.nextcloud.com", 443)

# Seconds to wait for the STUN server to answer, per attempt.
STUN_TIMEOUT = 2.0
