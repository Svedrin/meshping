# Build oping-py

FROM alpine:latest

RUN apk add --no-cache python3 python3-dev musl-dev liboping-dev make gcc bash
RUN pip3 install Cython redis

WORKDIR /opt/meshping
COPY build.sh /opt/meshping/build.sh
COPY oping-py /opt/meshping/oping-py
RUN mkdir src && ./build.sh

# Build meshping

FROM alpine:latest

RUN apk add --no-cache python3 liboping bash
COPY requirements.txt /opt/meshping/requirements.txt
RUN pip3 install -r /opt/meshping/requirements.txt

WORKDIR /opt/meshping
COPY --from=0 /usr/lib/python3.8/site-packages/oping.*.so /usr/lib/python3.8/site-packages
COPY cli.py /opt/meshping/cli.py
COPY src    /opt/meshping/src
COPY docker /opt/meshping/docker
CMD ["/opt/meshping/docker/run.sh"]
