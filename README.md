# meshping #

This is a little tool to allow pinging a collection of remote hosts within a network simultaneously.

This tool is meant to be set up on various strategic points in a network, pinging different locations in order to find weak links. It has a control socket which supports querying its statistics in JSON format as well as adding and removing hosts without needing to restart the ping daemon. New hosts will simply be pinged as if they always had been.

### Features ###

* Control socket to easily query statistics / add hosts / remove hosts
* Different ping intervals
* Reports pings sent, replies received, errors received (i.e., "Host unreachable" messages), avg/min/max ping time
* Hosts can be added/removed live without restarting the daemon (btw: [isc-dhcpd can do that for you](http://blog.svedr.in/posts/fun-with-dhcpd-hooks.html))
* Sometime in the future, those strategic points will be able to form a cluster using [Corosync](http://corosync.github.io/corosync/) to ensure config consistency
* Tightly integrated with [FluxMon](http://fluxmon.de) for monitoring and graphing 'n stuff
* Provides a Prometheus interface at port 9922

### How do I get set up? ###

Easy, you just run:

```
apt-get install mercurial cython liboping-dev
hg clone http://bitbucket.org/Svedrin/meshping
cd meshping
python setup.py build
ln -s build/lib.linux-x86_64-2.7/oping.so
sudo python meshping.py google.de/60 192.168.178.1 somewhere-else.net
```

Then you'll get a statistico like this one every second:

```
Target                     Sent  Recv  Errs  Outd   Loss     Err    Outd      Avg       Min       Max      Last
8.8.8.8                     109   109     0     0   0.00%   0.00%   0.00%   14.79      0.00    159.05     10.95
37.120.162.165              626   626     0     0   0.00%   0.00%   0.00%   17.47      0.00    179.04     15.76
192.168.0.196               626   626     0     0   0.00%   0.00%   0.00%    3.40      0.00     15.84      3.35
192.168.0.1                 626   626     0     0   0.00%   0.00%   0.00%    3.08      0.00     15.55      5.44
10.5.0.1                    626   626     0     0   0.00%   0.00%   0.00%    3.39      0.00     15.61      5.38
192.168.0.108               626   626     0     0   0.00%   0.00%   0.00%    3.12      0.00     15.51      4.87
192.168.100.1                11    11     0     0   0.00%   0.00%   0.00%    3.80      0.00      7.45      2.73
192.168.0.101               626   626     0     0   0.00%   0.00%   0.00%    8.16      0.00     26.44      5.06
```

The easiest way to query the control socket is using socat:

```
echo '{"cmd": "list", "reset": false}' | socat - udp:127.0.0.1:55432  | json_pp
```

However, you can of course write your own tools that send control commands. Setting `"reset": true` will cause the statistics to be reset to 0.

Adding a host is a breeze too:

```
echo '{"cmd": "add", "name": "google.com", "itv":  5}' | socat - udp:127.0.0.1:55432  | json_pp
echo '{"cmd": "add", "addr": "8.8.8.8",    "itv": 30}' | socat - udp:127.0.0.1:55432  | json_pp
```

And you can even remove it again:

```
echo '{"cmd": "remove", "name": "google.com"}' | socat - udp:127.0.0.1:55432  | json_pp
```

Note that when adding a target, you can pass in DNS names as well. meshping will then resolve these names and add all IP addresses it gets. The `remove` command will remove all those entries again if passed a `name` parameter. To remove only a single IP address, use:

```
echo '{"cmd": "remove", "addr": "8.8.8.8"}' | socat - udp:127.0.0.1:55432  | json_pp
```

### Who do I talk to? ###

* If you'd like to get in touch, send me an [email](mailto:i.am@svedr.in) or talk to me (Svedrin) on the Freenode IRC network.
* I also regularly hang out at the Linux User Group or the [mag.lab](http://mag.lab.sh) in Fulda.
