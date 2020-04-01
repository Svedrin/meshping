# meshping

Ping daemon that pings a number of targets at once, collecting their response times in histograms. Meant to be deployed at strategic points in your network in order to detect weak links.

## Features

* Meshping instances can be [peered](#wide-distribution-peering) with one another and will then ping the same targets.
* Scrapeable by [Prometheus](prometheus.io).
* Targets can be added and removed on-the-fly, without restarting or reloading anything.
* CLI tool to interact with the daemon.
* IPv6 supported.
* Docker images: https://hub.docker.com/r/svedrin/meshping

## Screenshots

### Heatmaps

Grafana added Prometheus-compatible Heatmaps in version 5.1. Those let you render graphs like these, showing when your ISP failovers you to a second line:

![ISP outage](examples/heatmap.png)

Here you can nicely see that at `05/07 13:00` there was a minor outage (failover to a different router on the same line, basically), and at
`05/08 13:00` something big happened (main line went down completely and we switched to the backup line).

Or that this power converter hardware you bought recently is a bit weird:

![flaky hardware](examples/heatmap2.png)

The latter is a normal distribution, which is an indication that you're looking at too small a time frame. Let's look at this heatmap over
ninety days, and compare it to one that aggregates one day's worth of data per histogram:

![flaky hardware, weekly histogram](examples/heatmap3.png)

This is a lot less noisy.

### Summary

If you point your browser to Meshping at `http://localhost:9922`, you'll get statistics like this:

```
Target                    Address                    Sent  Recv   Succ    Loss      Min    Avg15m     Avg6h    Avg24h       Max      Last
dc.local.lan.             10.5.0.10                 22863 22669  99.15%   0.85%    0.06      0.97      0.95      0.89     13.87      1.33
alexi001.local.lan.       10.5.0.122                19644 19587  99.71%   0.29%    0.05      1.02      0.90      0.85     12.38      1.35
alexi002.local.lan.       10.5.0.123                19643 19523  99.39%   0.61%    0.06      1.21      1.18      1.14     14.97      2.38
alexi003.local.lan.       10.5.0.124                19644 19470  99.11%   0.89%    0.06      0.86      0.96      0.93     13.19      2.17
10.5.1.2                  10.5.1.2                  22863 22819  99.81%   0.19%  606.30    746.00    806.17    867.11   4245.05    713.65
inverter.local.lan.       192.168.0.101             22863 22821  99.82%   0.18%    0.49     45.01     50.59     41.06    144.25     34.96
snom370-260DFE.local.lan  192.168.0.117             22863 22812  99.78%   0.22%    0.83      1.51      1.57      1.48   1000.03      1.39
```

### Raw data

If you query the `/metrics` endpoint, you get a histogram that carries far more detail:

```
meshping_sent{target="10.5.1.2"} 7362
meshping_recv{target="10.5.1.2"} 7330
meshping_lost{target="10.5.1.2"} 32
meshping_max{target="10.5.1.2"} 3848.67
meshping_min{target="10.5.1.2"} 608.21
meshping_pings_sum{target="10.5.1.2"} 6704337.831000
meshping_pings_count{target="10.5.1.2"} 7330
meshping_pings_bucket{target="10.5.1.2",le="630.34"} 72
meshping_pings_bucket{target="10.5.1.2",le="675.58"} 1014
meshping_pings_bucket{target="10.5.1.2",le="724.07"} 2117
meshping_pings_bucket{target="10.5.1.2",le="776.04"} 2979
meshping_pings_bucket{target="10.5.1.2",le="831.74"} 3706
meshping_pings_bucket{target="10.5.1.2",le="891.43"} 4550
meshping_pings_bucket{target="10.5.1.2",le="955.42"} 5286
meshping_pings_bucket{target="10.5.1.2",le="1023.99"} 5908
meshping_pings_bucket{target="10.5.1.2",le="1097.49"} 6340
meshping_pings_bucket{target="10.5.1.2",le="1176.26"} 6565
meshping_pings_bucket{target="10.5.1.2",le="1260.68"} 6685
meshping_pings_bucket{target="10.5.1.2",le="1351.17"} 6762
meshping_pings_bucket{target="10.5.1.2",le="1448.14"} 6830
meshping_pings_bucket{target="10.5.1.2",le="1552.08"} 6903
meshping_pings_bucket{target="10.5.1.2",le="1663.48"} 6976
meshping_pings_bucket{target="10.5.1.2",le="1782.88"} 7050
meshping_pings_bucket{target="10.5.1.2",le="1910.84"} 7125
meshping_pings_bucket{target="10.5.1.2",le="2047.99"} 7176
meshping_pings_bucket{target="10.5.1.2",le="2194.98"} 7217
meshping_pings_bucket{target="10.5.1.2",le="2352.52"} 7255
meshping_pings_bucket{target="10.5.1.2",le="2521.37"} 7281
meshping_pings_bucket{target="10.5.1.2",le="2702.34"} 7301
meshping_pings_bucket{target="10.5.1.2",le="2896.30"} 7311
meshping_pings_bucket{target="10.5.1.2",le="3104.18"} 7320
meshping_pings_bucket{target="10.5.1.2",le="3326.98"} 7323
meshping_pings_bucket{target="10.5.1.2",le="3565.77"} 7327
meshping_pings_bucket{target="10.5.1.2",le="3821.69"} 7329
meshping_pings_bucket{target="10.5.1.2",le="4095.99"} 7330
```

This endpoint is meant to be scraped by Prometheus.

## Querying from Prometheus

You can run queries on the data from Prometheus, e.g.

 * loss rate in %: `rate(meshping_lost{target="$target"}[2m]) / rate(meshping_sent[2m]) * 100`
 * quantiles: `histogram_quantile(0.95, rate(meshping_pings_bucket{target="$target"}[2m]))`
 * averages: `rate(meshping_pings_sum{target="10.5.1.2"}[2m]) / rate(meshping_pings_count[2m])`

## Heatmaps in Grafana

Grafana added [Heatmap support](https://github.com/grafana/grafana/issues/10009) in v5.1, so we now can produce graphs like the images above,
that contain a [histogram over time](http://docs.grafana.org/img/docs/v43/heatmap_histogram_over_time.png) that shows the pings.

To do that, add a Heatmap panel to Grafana, and configure it with:

* Query: `increase(meshping_pings_bucket{target=\"$target\"}[1h])`
* Legend format: `{{ le }}`
* Unit: `ms`
* Min step: `1h`

For a one-histogram-per-day panel, use these settings:

* Query: `increase(meshping_pings_bucket{target=\"$target\"}[1d])`
* Min step: `1d`


Meshping is meant to look at pings over a long time range (e.g. two days or a week), so be sure not to make those time frames too short.
Otherwise you'll lose the heatmap effect because every data point will be its own histogram.

In the examples directory, there's also a [json dashboard definition](examples/grafana.json) that you can import.


## Built-in heatmaps

Meshping also has a built-in heatmaps feature. These do not look as pretty as the ones from Grafana, but I find they are better readable and more useful. They look like this:

![built-in heatmap](examples/heatmap4.png)

To enable these, configure the `MESHPING_PROMETHEUS_URL` environment variable to point to your prometheus instance, like so:

```
MESHPING_PROMETHEUS_URL="http://192.168.0.1:9090"
```

Then Meshping will enable buttons in the UI to view these graphs.

The default query that Meshping sends to Prometheus to fetch the data is this one:

```
increase(meshping_pings_bucket{instance="%(pingnode)s",name="%(name)s",target="%(addr)s"}[1h])
```

Names get substituted with the respective values before sending the query. If you need to modify it, you can override it via the `MESHPING_PROMETHEUS_QUERY` environment variable.


# Deploying

Deploying meshping is easiest using `docker-compose`:

```yaml
version: '2'

services:
  meshping:
    # for x86_64 and amd64:
    # image: "svedrin/meshping:latest"
    # for raspberry Pi 3 or other ARMv7-based things (see `uname -m`):
    image: "svedrin/meshping:latest-armv7l"
    network_mode: "host"
    restart: always
    labels:
      "com.centurylinklabs.watchtower.enable": "true"
    # If you want to add other Meshping instances to peer with, uncomment this:
    #environment:
    #  MESHPING_PEERS: 10.10.10.1:9922,10.10.20.1:9922

  redis:
    image: "redis:alpine"
    network_mode: "host"
    restart: always
    volumes:
      - "meshping-redis-data:/data"

  watchtower:
    image: "containrrr/watchtower:latest"
    command: "--label-enable --cleanup --debug --interval 60"
    restart: always
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
```

This will deploy meshping and redis, along with a [Watchtower](https://hub.docker.com/r/containrrr/watchtower) instance that keeps Meshping up-to-date. It can be deployed as-is by adding a Stack through Portainer, or using `docker-compose`:

    mkdir meshping
    cd meshping
    $EDITOR docker-compose.yml
    (paste in the file)
    docker-compose up --detach

I also highly recommend adding these two aliases to your `.bashrc` file:

    alias redis-cli="docker run --net=host --rm -it redis:alpine redis-cli"
    alias mpcli='docker run --rm -it --net=host svedrin/meshping:latest-armv7l mpcli'

You can reload `.bashrc` in a live shell session using:

    source ~/.bashrc

Meshping should now be reachable at `http://<your-ip>:9922`, and `mpcli` should work.


## Adding targets

To add targets, run `mpcli -a <target name>[@<target IP address>]`. Examples:

```
mpcli -a google.com@8.8.8.8
mpcli -a google.com@8.8.4.4
mpcli -a google.com
mpcli -a 8.8.8.8
mpcli -a example.com
mpcli -a 192.168.0.1
```

Meshping will pick up updates to the target list before the next ping iteration.


# Configuration options

Meshping is configured through environment variables. These exist:

* `MESHPING_REDIS_HOST`: The address of your redis instance (default: `127.0.0.1`).
* `MESHPING_TIMEOUT`: Ping timeout (default: 5s).
* `MESHPING_PEERS`: Comma-separated list of other Meshping instances to peer with (only `ip:port`, no URLs).


# Distributed Meshping

Meshping can be distributed in two ways: You can point multiple instances to the same Redis DB for local distribution,
and you can configre peering to have multiple Meshping instances collaborate across WAN links.

## Local distribution: Shared Redis

Meshping supports running multiple meshping instances that ping the same targets, each reporting stats from their
point of view. To use this, set up a master instance like outlined above, and configure its Redis server to be reachable
from the slaves. Then, edit `meshping.service` on the slaves to point to the Master's redis instance, by setting the
`MESHPING_REDIS_HOST` to an IP or FQDN of your master server.

Restart Meshping, and it'll pick up on the targets immediately.

## Wide distribution: Peering

If you have set up multiple Meshping instances with WAN links in between, using a shared Redis instance is not an
option because if the WAN link is down -- the very condition you would like Meshping to detect -- access to Redis
is not possible and Meshping won't work. In such a scenario, you can run two separate Meshping instances, each using
its own Redis instance in the background, and have them exchange targets via peering. To do this, set the
`MESHPING_PEERS` env var in each instance to point to each other. That way, they will exchange target lists regularly,
and you will be able to retrieve statistics from both sides to see how your links are doing.


# Dev build

Building locally for development works like this. First build the container:

```
docker build -t meshping:latest-dev .
```

Then run it and pass in your current source code as volumes, overriding the source code from the container:

```
docker run --rm -it --net=host \
    -v $PWD/src:/opt/meshping/src \
    -v $PWD/ui/src:/opt/meshping/ui/src \
    meshping:latest-dev
```

You can now make changes in your local clone and they will become visible in the container.


# Who do I talk to?

* First and foremost: Feel free to open an [issue](https://github.com/Svedrin/meshping/issues/new) in this repository. :)
* If you'd like to get in touch, you can send me an [email](mailto:i.am@svedr.in).
* I also regularly hang out at the Linux User Group in Fulda.
