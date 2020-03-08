FROM alpine:latest

# Install and build dependencies first
RUN apk add --no-cache python3 python3-dev musl-dev liboping-dev make gcc bash
RUN pip3 install Cython redis

WORKDIR /opt/meshping
COPY build.sh /opt/meshping/build.sh
COPY oping-py /opt/meshping/oping-py
RUN mkdir src && ./build.sh

# Now install the rest of the application
COPY . /opt/meshping/

CMD ["/opt/meshping/docker/run.sh"]
