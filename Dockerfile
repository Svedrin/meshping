FROM debian:buster-slim

COPY . /opt/meshping
WORKDIR /opt/meshping

RUN apt-get update && apt-get install -y build-essential mercurial liboping-dev cython python-flask python-redis && rm -rf /var/lib/apt/lists/*
RUN cd /opt/meshping && ./build.sh

CMD ["/opt/meshping/docker/run.sh"]
