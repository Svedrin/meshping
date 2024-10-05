# Build oping-py

FROM alpine:3.20

RUN apk add --no-cache python3 python3-dev py3-pip musl-dev liboping-dev make gcc bash nodejs npm cython tzdata

COPY ui/package*.json /opt/meshping/ui/
RUN cd /opt/meshping/ui && npm install

WORKDIR /opt/meshping
COPY oping-py /opt/meshping/oping-py
RUN cd /opt/meshping/oping-py && python3 setup.py build && python3 setup.py install

# Build meshping

FROM alpine:3.20

RUN apk add --no-cache python3 py3-pip liboping bash py3-netifaces py3-pillow dumb-init ttf-dejavu py3-pandas tzdata plantuml openjdk8-jre

COPY requirements.txt /opt/meshping/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /opt/meshping/requirements.txt

WORKDIR /opt/meshping
COPY --from=0 /opt/meshping/ui/node_modules/jquery/LICENSE.txt                              /opt/meshping/ui/node_modules/jquery/
COPY --from=0 /opt/meshping/ui/node_modules/jquery/dist/jquery.slim.min.js                  /opt/meshping/ui/node_modules/jquery/dist/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/LICENSE                               /opt/meshping/ui/node_modules/bootstrap/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/dist/css/bootstrap.min.css            /opt/meshping/ui/node_modules/bootstrap/dist/css/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js       /opt/meshping/ui/node_modules/bootstrap/dist/js/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/LICENSE                         /opt/meshping/ui/node_modules/bootstrap-icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/                          /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/vue/LICENSE                                     /opt/meshping/ui/node_modules/vue/
COPY --from=0 /opt/meshping/ui/node_modules/vue/dist/vue.min.js                             /opt/meshping/ui/node_modules/vue/dist/
COPY --from=0 /opt/meshping/ui/node_modules/vue-resource/LICENSE                            /opt/meshping/ui/node_modules/vue-resource/
COPY --from=0 /opt/meshping/ui/node_modules/vue-resource/dist/vue-resource.min.js           /opt/meshping/ui/node_modules/vue-resource/dist/
COPY --from=0 /usr/lib/python3.12/site-packages/*/oping.*.so /usr/lib/python3.12/site-packages
COPY src    /opt/meshping/src
COPY ui/src /opt/meshping/ui/src

VOLUME /opt/meshping/db

ENTRYPOINT ["dumb-init", "--"]
ENV PYTHONPATH=/opt/meshping/src
CMD ["hypercorn", "--reload", "-k", "trio", "-b", "[::]:9922", "meshping:app"]
