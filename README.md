# meshping #

This is a little tool to allow pinging a collection of remote hosts within a network simultaneously.

This tool is meant to be set up on various strategic points in a network, pinging different locations in order to find weak links. It has a control socket which supports querying its statistics in JSON format as well as adding and removing hosts without needing to restart the ping daemon. New hosts will simply be pinged as if they always had been.

### Features ###

* Control socket to easily query statistics / add hosts / remove hosts
* Different ping intervals
* Reports pings sent, replies received, errors received (i.e., "Host unreachable" messages), avg/min/max ping time
* Hosts can be added/removed live without restarting the daemon
* Sometime in the future, those strategic points will be able to form a cluster using [Corosync](http://corosync.github.io/corosync/) to ensure config consistency
* Tightly integrated with [FluxMon](http://fluxmon.de) for monitoring and graphing 'n stuff

### How do I get set up? ###

Easy, you just run:

```
apt-get install mercurial
hg clone http://bitbucket.org/Svedrin/meshping
cd meshping
sudo python meshping.py google.de/60 192.168.178.1 somewhere-else.net
```

### Who do I talk to? ###

* If you'd like to get in touch, send me an [email](mailto:i.am@svedr.in) or talk to me (Svedrin) on the Freenode IRC network.
* I also regularly hang out at the Linux User Group or the [mag.lab](http://mag.lab.sh) in Fulda.