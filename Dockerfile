# Build oping-py

FROM alpine:3.12

RUN apk add --no-cache python3 python3-dev py3-pip musl-dev liboping-dev make gcc bash nodejs npm
RUN pip3 install Cython

COPY ui/package*.json /opt/meshping/ui/
RUN cd /opt/meshping/ui && npm install

WORKDIR /opt/meshping
COPY oping-py /opt/meshping/oping-py
RUN cd /opt/meshping/oping-py && python3 setup.py build && python3 setup.py install

# Build meshping

FROM alpine:3.12

RUN apk add --no-cache python3 py3-pip liboping bash py3-netifaces py3-pillow dumb-init ttf-dejavu

# With alpine:edge, we can just apk add py3-pandas and not build it ourselves.
# Unfortunately edge is currently broken on arm due to an ongoing migration to make 32-bit Alpine year-2038-safe.
# The py3-pandas package that is currently in edge needs at least musl 1.2, the docker-hub version of edge doesn't
# have that, and upgrading is currently not possible because see above.
RUN apk add --no-cache musl-dev gcc g++ make py3-tz py3-dateutil linux-headers py3-numpy-dev python3-dev py3-setuptools cython
RUN pip3 install pandas

COPY requirements.txt /opt/meshping/requirements.txt
RUN pip3 install --no-cache-dir -r /opt/meshping/requirements.txt


WORKDIR /opt/meshping
COPY --from=0 /opt/meshping/ui/node_modules/jquery/LICENSE.txt                              /opt/meshping/ui/node_modules/jquery/
COPY --from=0 /opt/meshping/ui/node_modules/jquery/dist/jquery.slim.min.js                  /opt/meshping/ui/node_modules/jquery/dist/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/LICENSE                               /opt/meshping/ui/node_modules/bootstrap/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/dist/css/bootstrap.min.css            /opt/meshping/ui/node_modules/bootstrap/dist/css/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js       /opt/meshping/ui/node_modules/bootstrap/dist/js/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/LICENSE.md                      /opt/meshping/ui/node_modules/bootstrap-icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/graph-up.svg              /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/trash.svg                 /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/arrow-up-right-circle.svg /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/check-circle.svg          /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/exclamation-circle.svg    /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/question-circle.svg       /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/bootstrap-icons/icons/x-circle.svg              /opt/meshping/ui/node_modules/bootstrap-icons/icons/
COPY --from=0 /opt/meshping/ui/node_modules/vue/LICENSE                                     /opt/meshping/ui/node_modules/vue/
COPY --from=0 /opt/meshping/ui/node_modules/vue/dist/vue.min.js                             /opt/meshping/ui/node_modules/vue/dist/
COPY --from=0 /opt/meshping/ui/node_modules/vue-resource/LICENSE                            /opt/meshping/ui/node_modules/vue-resource/
COPY --from=0 /opt/meshping/ui/node_modules/vue-resource/dist/vue-resource.min.js           /opt/meshping/ui/node_modules/vue-resource/dist/
COPY --from=0 /usr/lib/python3.8/site-packages/oping.*.so /usr/lib/python3.8/site-packages
COPY src    /opt/meshping/src
COPY ui/src /opt/meshping/ui/src

VOLUME /opt/meshping/db

ENTRYPOINT ["dumb-init", "--"]
CMD ["/usr/bin/python3", "--", "/opt/meshping/src/meshping.py"]
