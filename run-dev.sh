#!/bin/bash

set -e
set -u

if [ -z "$(docker image ls -q meshping:latest-dev)" ]; then
    docker build -t meshping:latest-dev .
fi

mkdir -p /tmp/statistico

function parse_result () {
    if [ -e "/tmp/statistico/profile.bin" ]; then
        echo "Parsing results..."
        python3 \
            -c 'import pstats; pstats.Stats("/tmp/statistico/profile.bin").sort_stats("cumulative").print_stats()' \
            > /tmp/statistico/profile.txt
        cat /tmp/statistico/profile.txt
        echo "Results are available in /tmp/statistico/profile.txt."
    fi
}

trap parse_result exit

echo "Running meshping with profiling enabled. Hit ^c to stop."

docker run --rm -it --net=host \
    -v /tmp/statistico:/tmp/statistico \
    -v $PWD/src:/opt/meshping/src \
    -v $PWD/ui/src:/opt/meshping/ui/src \
    meshping:latest-dev \
    python3 -m cProfile -o /tmp/statistico/profile.bin src/meshping.py
