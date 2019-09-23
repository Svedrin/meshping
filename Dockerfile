FROM debian:buster-slim

WORKDIR /opt/meshping

# Install and build dependencies first
RUN apt-get update && apt-get install -y build-essential mercurial liboping-dev cython python-flask python-redis && rm -rf /var/lib/apt/lists/*
COPY build.sh /opt/meshping/build.sh
COPY oping-py /opt/meshping/oping-py
RUN mkdir src && ./build.sh

# Now install the rest of the application
COPY . /opt/meshping/

CMD ["/opt/meshping/docker/run.sh"]
