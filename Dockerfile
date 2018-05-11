FROM debian:stretch-slim

COPY . /opt/meshping

RUN apt-get update
RUN apt-get install -y build-essential mercurial liboping-dev cython python-flask python-redis
RUN rm -rf /var/lib/apt/lists/*
RUN cd /opt/meshping && ./build.sh

CMD ["/opt/meshping/docker/run.sh"]
