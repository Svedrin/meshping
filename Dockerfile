# Build oping-py

FROM alpine:latest

RUN apk add --no-cache python3 python3-dev musl-dev liboping-dev make gcc bash nodejs npm
RUN pip3 install Cython

COPY ui/package*.json /opt/meshping/ui/
RUN cd /opt/meshping/ui && npm install

WORKDIR /opt/meshping
COPY build.sh /opt/meshping/build.sh
COPY oping-py /opt/meshping/oping-py
RUN cd /opt/meshping/oping-py && python3 setup.py build && python3 setup.py install

# Build meshping

FROM alpine:latest

RUN apk add --no-cache python3 liboping bash py3-netifaces~=0.10.9 dumb-init
COPY requirements.txt /opt/meshping/requirements.txt
RUN pip3 install -r /opt/meshping/requirements.txt

WORKDIR /opt/meshping
COPY --from=0 /opt/meshping/ui/node_modules/jquery/dist/jquery.slim.min.js        /opt/meshping/ui/node_modules/jquery/dist/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/dist/css/bootstrap.min.css  /opt/meshping/ui/node_modules/bootstrap/dist/css/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/dist/js/bootstrap.min.js    /opt/meshping/ui/node_modules/bootstrap/dist/js/
COPY --from=0 /opt/meshping/ui/node_modules/vue/dist/vue.min.js                   /opt/meshping/ui/node_modules/vue/dist/
COPY --from=0 /opt/meshping/ui/node_modules/vue-resource/dist/vue-resource.min.js /opt/meshping/ui/node_modules/vue-resource/dist/
COPY --from=0 /usr/lib/python3.8/site-packages/oping.*.so /usr/lib/python3.8/site-packages
COPY cli.py /usr/local/bin/mpcli
COPY src    /opt/meshping/src
COPY ui/src /opt/meshping/ui/src
ENTRYPOINT ["dumb-init", "--"]
CMD ["/usr/bin/python3", "--", "/opt/meshping/src/meshping.py"]
