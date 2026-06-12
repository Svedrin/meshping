# Meshping Peering: Feature Spec

This document describes the planned evolution of meshping's peering feature
(`src/peers.py`, `/peer` endpoint in `src/api.py`).

## Current State

Today, peering does one thing: each node periodically POSTs its own list of
targets (name, address, whether the address is "local" to it) to every peer
listed in `MESHPING_PEERS`. The receiving node adds any target it doesn't
already know about, marks it `is_foreign`, and pings it itself.

This works, but has several shortcomings:

1. **No lifecycle.** A foreign target, once added, stays forever - even if
   the peer that advertised it is long gone.
2. **No authentication.** Anything that can reach `/peer` can inject targets.
3. **Single-hop only.** Foreign targets are never re-advertised
   (`if not target.is_foreign`), so a target only spreads to nodes that are
   directly peered with its origin.
4. **No data redundancy.** If a node dies, its measurement history (and the
   ability to monitor its targets) dies with it.

This spec addresses all four, with an emphasis on (4): being able to log into
a surviving peer and see a dead node's recent history.

## Goals

* When a node goes down, an operator can log into any of its peers and view
  that node's recent targets and histogram/loss data, clearly marked as
  "last known data from `<node>`, as of `<time>`".
* Foreign targets that are no longer advertised by any peer eventually
  disappear on their own (no manual cleanup).
* `/peer` only accepts data from peers it recognizes and trusts.
* The above without requiring a leader, a quorum, or any kind of
  cluster-wide agreement - meshping should keep working in whatever
  fragments remain reachable during an outage.

## Non-Goals

* Building a general-purpose distributed database. Replicated data is a
  best-effort, read-only backup for human inspection - not a system other
  components depend on for correctness.
* Automatic topology/peer discovery. `MESHPING_PEERS` remains an explicit,
  operator-managed list.
* Strong consistency or write availability guarantees of any kind.
* Authenticating meshping's UI/`/api/*` endpoints. See "Threat Model" below
  for why this matters even though it's out of scope.

## Threat Model

Meshping's UI and `/api/*` endpoints have **no authentication of their
own**, and this spec doesn't change that. Anyone who can reach an
instance's HTTP port can already open its UI and add/remove targets,
browse all data, etc. - the same access a malicious `/peer` payload would
try to achieve.

This shapes what "peer auth" (section 1) actually buys:

* **What it protects**: the *federation's* identity integrity - that data
  attributed to a given `node_key` (a target advertisement, a tombstone, a
  replica) really came from the instance holding that key's private half,
  not from something impersonating it. This starts to matter once
  tombstones and replicated histories carry attribution that *other* nodes
  act on (delete data, label a UI view "data from node Y").
* **What it does not protect**: the instance itself. If MP-B's HTTP port is
  reachable by an attacker, they can already do most of what a forged
  `/peer` payload could via MP-B's open UI/`/api/targets` - regardless of
  how `/peer` is locked down.

**Practical implication**: every meshping instance (UI, `/peer`, and
`/peer/replicate` alike) must be deployed on a network the operator already
trusts - private LAN, VPN, etc. This was already implicitly required by the
wide-open UI; this spec doesn't raise or lower that bar. Peer auth keeps the
*federation's bookkeeping* honest between mutually-trusted instances, it is
not perimeter security for an individual one.

One consequence worth calling out up front: this is also why a
"trust-on-first-use" pairing flow (see section 1) is an acceptable
trade-off here, even though TOFU is normally considered weak - anyone who
could interfere with pairing on this network could already reach
`/peer`/`/api/targets` directly and do worse.

## Terminology

* **node_id** - a short, human-chosen label identifying a meshping instance
  (default: its hostname, overridable via `MESHPING_NODE_ID`). Like OSPF's
  router_id, it's meant to be meaningful to the operator - shown in the UI,
  logs, and "data from node `<node_id>`" views. Can be changed any time.
* **node_key** - a stable, machine-generated identifier that never changes
  for the lifetime of an instance. Unlike `node_id`, it can't collide or be
  renamed, so it's what `origin`, replication watermarks, and tombstone
  `seq` tracking key off internally. See section 1 for what it actually is.
* **origin** - the `node_key` of the instance that "owns" a piece of data
  (a target it pings itself, or a measurement it produced).
* **foreign target** - a target we ping ourselves because a peer told us
  about it (existing concept, `is_foreign`).
* **replica** - a read-only copy of another node's *own* data (its targets
  and their histograms/loss stats), stored so it survives that node's
  death. We don't ping replica targets ourselves (unless they're *also* a
  foreign target we independently picked up).

---

## 1. Node Identity & Peer Authentication

### Two kinds of identity

Borrowing from OSPF's router_id (which operators routinely set to something
memorable rather than its auto-selected default), this spec splits identity
into two pieces, both persisted in a new small `node` table (one row):

* **`node_id`** - a human-chosen label, defaulting to `socket.gethostname()`,
  overridable via `MESHPING_NODE_ID`. Purely for humans - shown in the UI,
  in logs, and in "data from node `<node_id>`, last seen `<time>`" views
  (section 4). Can be changed at any time without affecting trust or data
  attribution.
* **`node_key`** - a stable, machine-generated identifier, generated once on
  first start and never changed. This is what `origin`, replication
  watermarks, and tombstone `seq` tracking key off internally, since
  `node_id` labels can collide or be renamed but `node_key` can't.

`/peer` advertisements include both. If a node's `node_id` label changes,
peers update their stored label for that `node_key` on the next
advertisement with a higher `seq` ("newer wins", same rule as everywhere
else) - renaming a node doesn't require re-establishing trust or losing its
history.

What `node_key` actually *is* depends on the auth mechanism:

### Auth Option A: Pre-Shared Key (PSK)

* `node_key` = random UUID4, generated on first start.
* `MESHPING_PEER_TOKEN` env var holds a secret shared by the whole mesh.
  Outgoing `/peer` requests send it as `X-Meshping-Peer-Token: <token>`;
  the endpoint rejects requests with a missing/incorrect token (`401`).
* **Pros**: zero new dependencies, trivial setup (copy one string to every
  instance), easy to test with `curl`.
* **Cons**: one secret protects the whole mesh - leaking it anywhere
  compromises every peer relationship at once. No way to tell *which* peer
  sent a request beyond "someone who knows the token". Revoking a single
  peer means rotating the secret everywhere.

### Auth Option B: Ed25519 keypairs (libsodium / PyNaCl)

* `node_key` = the instance's Ed25519 public key (`crypto_sign_keypair`),
  generated on first start; the private key is persisted alongside the
  database and never transmitted.
* Outgoing `/peer` / `/peer/replicate` requests are signed
  (`crypto_sign_detached` over the request body + `seq`); the endpoint
  looks up the sender's `node_key` in its trusted-peers list and verifies
  with `crypto_sign_verify_detached`.
* Trust is established out-of-band, the same way as a WireGuard peer: the
  operator copies each side's `node_key` (its pubkey) into the other's peer
  config.
* **Pros**: per-peer identity and revocation (drop one `node_key` from the
  trust list without affecting anyone else); replay protection comes for
  free by combining the signature with the `seq` counter the lifecycle
  design (section 2) already needs (reject `seq <=` last seen for that
  `node_key`); `node_key` *is* what `origin` needs to be anyway, so there's
  no separate UUID to manage.
* **Cons**: new dependency (PyNaCl); slightly more setup (exchanging
  pubkeys instead of one shared string); losing the private key (e.g. a
  container redeployed without its volume) makes the instance look like a
  brand-new, untrusted peer until re-trusted.

### Recommendation

Go with **Option B**. The data model needs a stable `node_key` for `origin`
tracking from Phase 2 onward regardless of how auth is done - if Option A's
UUID were used now, adding keypairs later would mean carrying two parallel
identifiers. Doing keypairs from the start means `node_key` and the auth
identity are the same value, and replay protection falls out of `seq` for
free.

PSK isn't wasted, though - it's worth keeping as an optional **outer gate**
in front of `/peer`: if `MESHPING_PEER_TOKEN` is set, it's checked *before*
signature verification, letting an operator shut the endpoint to
internet-wide scanners/noise with one shared string while signatures still
provide per-peer identity for everything the protocol cares about. The two
are independent and can be combined.

### UI-Assisted Trust Establishment ("Pairing")

Manually exchanging `node_key`s (copy A's pubkey into B's trusted-peer list
and vice versa) has the same friction as exchanging SSH host keys or
WireGuard pubkeys: doable, but tedious enough that people skip it. Since
meshping already knows about a peer as soon as it's listed in
`MESHPING_PEERS`, the UI can do this exchange itself.

* `GET /peer/identity` - unauthenticated, returns the instance's own
  `{node_id, node_key}`. This isn't secret (it's a public key plus a label),
  same as an SSH host key, so reading it needs no auth.
* `POST /peer/identity` - registers a peer's identity as trusted. To bound
  the TOFU window, this is only accepted for a source `addr:port` that's
  (a) listed in this instance's own `MESHPING_PEERS`, and (b) doesn't
  already have a `node_key` on file. Re-keying an existing peer (e.g. after
  it lost its private key) requires the operator to explicitly "forget"
  that peer first - silently accepting a new key for an already-trusted
  peer would be a downgrade-to-impersonation vector.
* The UI shows configured peers with no `node_key` on file as **Unpaired**,
  with a **Pair** button. Clicking it makes the local instance:
  1. `GET <peer>/peer/identity` and store the returned `node_key` as
     trusted, then
  2. `POST` its own `{node_id, node_key}` to `<peer>/peer/identity`, so the
     other side trusts it back in the same click.
* The UI displays the newly-learned `node_key` (or a short fingerprint,
  SSH-style) so the operator can eyeball it against what the peer's own UI
  shows for itself, if they want a sanity check.

This is deliberately TOFU - per the threat model, whoever can click "Pair"
on this UI could already reach the peer directly on this trusted network, so
automating the key exchange doesn't open a new door, it just removes
copy-pasting from a step that was always going to succeed or fail based on
network reachability.

Note this only applies to **Option B**. Under **Option A** (PSK), there's
nothing to pair - `MESHPING_PEER_TOKEN` is the same value across the whole
mesh, set once by the operator out-of-band (e.g. the same env var in every
instance's compose file).

## 2. Target Advertisement Lifecycle (LSA-inspired)

Borrowing OSPF's LSA aging, but without the flooding/SPF machinery: each
advertised target carries its origin and a freshness marker.

```jsonc
{
  "node_key": "5e1b...",         // advertiser's node_key (its pubkey)
  "node_id":  "fra-edge-1",      // advertiser's human label
  "targets": [
    {
      "origin": "5e1b...",       // node_key that owns this target
      "name": "raspi",
      "addr": "192.168.0.123",
      "local": true,
      "seq": 1234                // monotonically increasing per origin
    }
  ]
}
```

* `seq` is a counter the *origin* increments each time it (re-)advertises
  its own targets (every `MESHPING_PEERING_INTERVAL`). It is **not** a
  vector clock or a Lamport clock across the mesh - it's purely
  "origin says: this is still alive, as of generation N".
* When a node receives a target, it stores `(origin, seq, last_seen=now)`
  in `meta` alongside the existing `is_foreign` flag.
* A background sweep removes foreign targets whose `last_seen` is older
  than e.g. `5 * MESHPING_PEERING_INTERVAL`. A node that's merely had a
  blip won't lose its targets everywhere; a node that's gone for good
  eventually does.
* `seq` itself isn't strictly required for single-hop (timestamps would
  do), but it becomes useful once re-advertisement (multi-hop, see below)
  is involved, so a receiver can tell "is this newer than what I already
  have from this origin" without relying on clock sync.

This directly fixes shortcoming (1) with no new endpoints and minimal state.

### Tombstones: propagating explicit deletes

Aging handles *implicit* disappearance (a peer died, was removed from
`MESHPING_PEERS`, etc.), but takes up to `5 * MESHPING_PEERING_INTERVAL` to
converge, and can't distinguish "the peer is just being slow" from "this
target is gone for good".

For *explicit* deletes - a user removing a target on its origin node - we can
do better, borrowing BGP's withdrawal idea on top of the `seq` field:

* When a user deletes target T on its origin node MP-A, MP-A doesn't drop
  the row immediately. It sets `meta.deleted_at = now()`, bumps `seq`, and
  stops pinging T itself right away (it's gone from MP-A's *active*
  perspective).
* MP-A keeps including T in its advertisements for a grace period
  (`MESHPING_TOMBSTONE_GRACE`, suggest defaulting to the same value as the
  aging timeout, `5 * MESHPING_PEERING_INTERVAL`), but with `"deleted": true`:

  ```jsonc
  {
    "origin": "5e1b...", "addr": "192.168.0.123", "name": "raspi",
    "seq": 1235, "deleted": true
  }
  ```

* MP-B/MP-C, on receiving `deleted: true` for `(origin, addr)` with a `seq`
  newer than what they have stored, immediately stop pinging T (if it was
  foreign) and mark their own copy as deleted with the same `seq`. In a
  multi-hop world (section 5) they'd re-advertise the tombstone onward for
  their own grace period; in the single-hop case there's nothing further to
  forward it to.
* After its grace period elapses, MP-A purges T (row, histograms, loss
  stats, meta) entirely and stops mentioning it at all. MP-B/MP-C, having
  already marked T deleted on first sight of the tombstone, purge their own
  copies on the same schedule (counted from when *they* first saw the
  tombstone, not MP-A's clock).

The grace period exists so that a peer offline for a short blip still gets to
see the tombstone at least once, rather than the entry just silently vanishing
from advertisements (which aging would eventually clean up anyway, just more
slowly and with less information - see below).

**Why this is worth the extra state**: a tombstone tells receivers *why* a
target disappeared, which is exactly the distinction Phase 3 replication
needs:

* Target disappears *with* a prior tombstone -> deletion was intentional ->
  purge any replica data for it too.
* Target disappears *without* a tombstone (origin just goes silent) ->
  origin is presumably dead -> keep replica data, since that's the whole
  point of Phase 3.

Without tombstones, both cases look identical (the target just stops being
advertised), forcing a choice between delete-happy (losing backups during a
long outage) or hoard-happy (never cleaning up after real deletes).

**Recreated targets**: if a user later re-adds a target at the same
`(origin, addr)`, it gets a fresh `seq` with `deleted: false`. Since `seq`
always increases, "newer wins" means peers just pick this up as a normal
update - no special-casing needed.

## 3. Data Replication for Resilience

This is the new piece. Separate from target *advertisement* (small, frequent,
"here's what to ping"), add a *replication* sync that copies each node's own
measurement data to its peers, so it survives that node dying.

### What gets replicated

For each of its own (non-foreign, non-replica) targets, a node replicates:

* the target's identity (`origin`, `addr`, `name`)
* `histogram` buckets (from `histograms` table)
* `loss_stats` (from `loss_stats` table)
* current `statistics` (sent/recv/lost/sum) and `meta` (state, route_loop
  etc.)

Replicas are **not** re-replicated by default (a replica of node A's data,
held by node B, is not forwarded by B to node C) - this avoids unbounded
fan-out and keeps the replication graph equal to the peering graph. See
"Future Work" for relaxing this.

### Transport

A new endpoint, `POST /peer/replicate`, separate from `/peer`:

```jsonc
{
  "node_key": "5e1b...",
  "node_id":  "fra-edge-1",
  "targets": [
    {
      "origin": "5e1b...", "addr": "192.168.0.123", "name": "raspi",
      "statistics": {"sent": 120, "recv": 118, "lost": 2, "sum": 1234.5},
      "meta": {"state": "up", "route_loop": "false"},
      "histogram": [ {"timestamp": 1234, "bucket": 3, "count": 5}, ... ],
      "loss_stats": [ {"timestamp": 1234, "sent": 30, "lost": 1}, ... ]
    }
  ],
  "since": 1700000000   // watermark used to build this payload
}
```

* Run on a longer interval than target advertisement (e.g. 5 minutes,
  `MESHPING_REPLICATION_INTERVAL`), since payloads are bigger.
* Each node tracks, per peer, the watermark (`since`) up to which it has
  successfully replicated. Only `histogram`/`loss_stats` rows newer than
  the watermark are sent (`statistics`/`meta` are small and always sent in
  full - latest write wins).
* On success, advance the local watermark for that peer. On failure,
  retry next interval with the same (or older) watermark - this is
  at-least-once, idempotent thanks to the existing `ON CONFLICT ... DO
  UPDATE` upsert queries.

### Storage

Replicated data needs to live alongside, but distinct from, our own data -
the same `addr` might be a target we ping ourselves *and* something a peer
also pings and replicates to us. The `targets` table's `UNIQUE (addr, name)`
constraint needs to become origin-aware, e.g. `UNIQUE (addr, origin)`, with
`origin = <our own node_key>` for everything we manage today (locally
configured *and* foreign-but-pinged-by-us targets keep their existing
meaning; replicas get the remote node's `node_key` as `origin`).

`histograms`, `loss_stats`, `statistics`, `meta` already key off
`target_id`, so they need no schema change beyond `targets` gaining
`origin`.

### Interaction with tombstones

If a replicated target's origin advertises a tombstone for it (see
"Tombstones" above), the holding node purges the corresponding replica (row
+ histograms + loss stats) on the same schedule as the origin - the user
asked for it to be gone, full stop. Replicas are only retained for targets
whose origin has gone *silent without a tombstone*, which is the actual
"node died" case Phase 3 is meant to cover.

## 4. Accessing a Dead Peer's Data

* Track peer liveness: if `/peer` (advertisement) to a configured peer fails
  for `N` consecutive intervals, mark that peer's `node_key` as `dead` (with
  a "last seen" timestamp) in a small `nodes` table.
* New UI view / API endpoint, e.g. `GET /api/nodes` listing known origins
  (`node_key`, `node_id` label, alive/dead, last_seen) and
  `GET /api/nodes/<node_key>/targets` listing that origin's replicated
  targets - reusing the existing histogram/graph rendering, but sourced
  from replica rows. The UI displays the `node_id` label, not the raw
  `node_key`.
* The UI marks these views read-only and stamps them with "as of
  `<last replication timestamp>`" so it's clear this is a backup, not live
  data.

This satisfies the core goal: log into any surviving peer, find the dead
node in a node list, and see its targets/graphs as they were last
replicated.

## 5. Future Work: Multi-Hop Propagation & Re-Replication

Out of scope for the initial implementation, but the `origin`/`seq` fields
above are designed to make this an additive change later:

* **Target re-advertisement**: forward foreign targets to other peers too,
  carrying a hop-count or visited-node list (path-vector style) to bound
  propagation and prevent loops (a node drops anything that already has its
  own `node_key` in the path).
* **Re-replication**: replicate replicas onward, bounded the same way, so a
  node's data survives even if *all* its direct peers die too. Replication
  factor would then be "number of hops", not "number of direct peers".

Both are deferred because they turn the replication/propagation graph from
"exactly the peering graph" (which the operator already configured and can
reason about) into something with non-obvious blast radius. Worth revisiting
once the single-hop version is in use and the storage/traffic costs are
understood.

---

## Considered and Rejected: Consensus Algorithms

**Raft** (or similar leader-based replicated logs) was considered for the
replication piece, but doesn't fit:

* Raft assumes a single writer (the leader) per log and majority-quorum
  writes. Meshping's data is inherently multi-writer - every node is the
  sole authority for its own measurements - so there's no "log" to elect a
  leader for.
* Quorum requirements mean writes (and in some configurations reads) stall
  when less than a majority is reachable. That's the opposite of what we
  want from monitoring infrastructure during an outage - it should keep
  working in whatever fragments remain reachable, even if that's "two nodes
  that can still see each other out of ten".
* Cluster membership changes (a node permanently leaving, a new node
  joining) require their own protocol on top of Raft (joint consensus) -
  more machinery for a problem we don't have, since `MESHPING_PEERS` is
  already an explicit, operator-managed list.

**OSPF DR/BDR** is not actually a consensus algorithm - it's an election
that reduces O(n²) adjacencies on a broadcast segment to O(n) by routing all
synchronization through one elected node (with a backup for failover). The
*idea* (elect a relay to cut down redundant traffic) could matter if the
peering mesh grows large enough that full-mesh replication traffic becomes
expensive, but:

* it adds an election protocol and DR/BDR failover handling for a problem
  that doesn't exist at the scale meshping is typically deployed at (a
  handful to perhaps a few dozen peers, explicitly configured);
* it would make the replication graph *not* match the peering graph,
  re-introducing the "non-obvious blast radius" problem from section 5.

What *is* borrowed from OSPF is the **LSA aging model** (section 2): origin +
sequence number + timeout-based expiry, without flooding or SPF. That's the
genuinely useful, low-complexity piece.

---

## Rollout Plan

1. **Phase 0** (done): fix IPv6 handling in `/peer` (`Ifaces` helper).
2. **Phase 1**: `node_id`/`node_key` generation, Ed25519-based peer auth on
   `/peer` (with optional `MESHPING_PEER_TOKEN` outer gate), `/peer/identity`
   + UI pairing flow.
3. **Phase 2**: origin/seq/age fields on advertised targets, deletion
   tombstones, and expiry sweeps for stale/tombstoned foreign targets.
4. **Phase 3**: `/peer/replicate` endpoint, origin-aware `targets` schema,
   per-peer watermarks, `nodes` table + UI view for dead-peer data.
5. **Phase 4** (future, re-evaluate after Phase 3 ships): multi-hop
   propagation and re-replication, if needed.

## Open Questions

* **Retention**: how long do we keep replica data for a node that's been
  dead for a long time? Same `MESHPING_HISTOGRAM_DAYS` policy, or longer
  (it's the only copy left)?
* **Resurrection**: if a "dead" node comes back with its own (diverging)
  data, do we just let it resume advertising and let replicas get
  overwritten on next sync (last-write-wins via `seq`/timestamp), or is
  reconciliation needed? Given the "best-effort backup" framing, last-write-
  wins seems sufficient.
* **Storage growth**: replication roughly multiplies disk usage by
  `(1 + number of peers)`. Worth surfacing via `/metrics` so operators can
  see it coming.
* **Local deletes of foreign targets**: if a user deletes a foreign target
  on MP-B (true origin is MP-A), MP-B isn't the origin, so no tombstone is
  generated - MP-A keeps advertising it, and MP-B would just re-add it as
  foreign on the next sync. Do we need a local "ignore this `(origin, addr)`
  even if still advertised" suppression list, or is unpeering the intended
  way to opt out of a peer's whole target set?
* **Payload size**: histogram replication payloads could get large for
  busy/long-running targets. May need chunking/pagination in
  `/peer/replicate` rather than one big POST per interval.
* **`node_id` collisions**: two peers could pick the same human label (e.g.
  both default to a hostname like `meshping`). Harmless protocol-wise since
  `node_key` is the real identity, but could be confusing in the UI's node
  list. Worth deduping the *display* (e.g. append a short `node_key`
  fragment when labels collide) without touching the underlying data.
* **UI/`/api/*` write protection**: the Threat Model section treats the open
  UI as a given and explicitly out of scope, but it might be worth a
  minimal, opt-in guard rather than leaving it open forever - without going
  anywhere near full user/group/role management. One lightweight option:
  `MESHPING_TOTP=1` generates a TOTP secret on first start (persisted like
  `node_key`), prints its provisioning URI/QR code to the log once, and
  then requires a valid TOTP code for mutating `/api/*` calls
  (add/remove/rename targets etc.) - read-only views and graphs stay open.
  This is orthogonal to peer auth: `/peer`/`/peer/replicate` already carry
  their own Ed25519/PSK credential and wouldn't need a TOTP code, since
  there's no human typing one in for a periodic machine-to-machine
  exchange. Given meshping is realistically only ever deployed on trusted
  networks, this is defense-in-depth, not a blocker - it could land
  independently of the phases above.
* **Viewing targets**: The UI should not only allow to see a list of peers
  and view the world from their (last known) perspective, but it should
  also amend our own view of all our targets to point out that some of our
  peers are monitoring the same target as well, so that we can offer to
  compare both measurements in a single graph.
