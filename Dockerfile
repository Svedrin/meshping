# Build oping-py

FROM alpine:latest

RUN apk add --no-cache python3 python3-dev musl-dev liboping-dev make gcc bash
RUN pip3 install Cython

WORKDIR /opt/meshping
COPY build.sh /opt/meshping/build.sh
COPY oping-py /opt/meshping/oping-py
RUN mkdir src && ./build.sh

# Build meshping

FROM alpine:latest

RUN apk add --no-cache python3 liboping bash py3-netifaces~=0.10.9 dumb-init
COPY requirements.txt /opt/meshping/requirements.txt
RUN pip3 install -r /opt/meshping/requirements.txt

WORKDIR /opt/meshping
COPY --from=0 /usr/lib/python3.8/site-packages/oping.*.so /usr/lib/python3.8/site-packages
COPY cli.py /usr/local/bin/mpcli
COPY src    /opt/meshping/src
ENTRYPOINT ["dumb-init", "--"]
CMD ["/usr/bin/python3", "--", "/opt/meshping/src/meshping.py"]
