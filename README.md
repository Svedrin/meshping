# meshping #

Ping daemon that pings a number of targets at once, collecting their response times in histograms. Meant to be deployed at strategic points in your network in order to detect weak links.

## Features

* Scrapeable by [Prometheus](prometheus.io).
* Targets can be added and removed on-the-fly, without restarting or reloading anything.
* CLI tool to interact with the daemon.

## Screenshots

If you open the root URL at `http://localhost:9922`, you'll get statistics like this:

```
Target                     Sent  Recv   Succ    Loss      Min       Avg       Max      Last
10.5.0.10                  7422  7353  99.07%   0.93%    0.10      0.82     13.87      1.30
10.5.0.98                  7422     0   0.00% 100.00%    0.00      0.00      0.00      0.00
10.5.0.122                 4203  4187  99.62%   0.38%    0.05      0.68      9.61      0.79
10.5.1.2                   7422  7390  99.57%   0.43%  608.21    917.71   3848.67   1035.10
8.8.8.8                    7422  7421  99.99%   0.01%   10.29     12.91    267.11     11.00
192.168.0.10               7422  7384  99.49%   0.51%    0.37      1.32     82.93      0.68
192.168.0.101              7422  7411  99.85%   0.15%    1.26     15.38    131.88     16.86
192.168.0.103              7422  1252  16.87%  83.13%    1.22    160.26   1720.66      1.69
192.168.0.108              7422  7329  98.75%   1.25%    0.14      0.20      0.87      0.23
192.168.0.109              7422   586   7.90%  92.10%    0.60      2.26     87.61      2.54
```

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

Then you can run queries on the data from Prometheus, e.g.

 * loss rate in %: `rate(meshping_lost{target="$target"}[2m]) / rate(meshping_sent[2m]) * 100`
 * quantiles: `histogram_quantile(0.95, rate(meshping_pings_bucket{target="$target"}[2m]))`
 * averages: `rate(meshping_pings_sum{target="10.5.1.2"}[2m]) / rate(meshping_pings_count[2m])`

Ultimate goal is to have Grafana render a [heatmap](http://docs.grafana.org/features/panels/heatmap/) with a
[histogram over time](http://docs.grafana.org/img/docs/v43/heatmap_histogram_over_time.png) that shows the pings,
but unfortunately that doesn't work [just yet](https://github.com/grafana/grafana/issues/10009).


### How do I get set up? ###

Unfortunately, this is a bit involved:

```
apt-get install mercurial cython liboping-dev python-flask python-redis redis-server
hg clone http://bitbucket.org/Svedrin/meshping
cd meshping
./build.sh
ln -s $PWD/cli.py /usr/local/bin/mpcli
cp meshping.service /etc/systemd/system
systemctl daemon-reload
service meshping start
```

Now the daemon should be running. Adding targets unfortunately sucks currently because I accidentally broke the cli.

In the meantime you can add targets using redis-cli:

```
# redis-cli
127.0.0.1:6379> sadd meshping:targets google@8.8.8.8
(integer) 1
```

and then restart meshping. (Yes, I did promise you wouldn't have to. Sorry about that.)


### Who do I talk to? ###

* If you'd like to get in touch, send me an [email](mailto:i.am@svedr.in) or talk to me (Svedrin) on the Freenode IRC network.
* I also regularly hang out at the Linux User Group or the [mag.lab](http://mag.lab.sh) in Fulda.
