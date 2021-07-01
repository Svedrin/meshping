#!/bin/bash

set -e
set -u

PROFILE=false

if [ "${1:-}" = "--help" ]; then
    echo "Usage: $0 [--help|--profile|<command>]"
    exit 0
elif [ "${1:-}" = "--profile" ]; then
    PROFILE=true
fi

if [ "${1:-}" = "clean" ]; then
    docker image rm --no-prune meshping:latest-dev
    exit 0
fi

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


if [ "$PROFILE" = "true" ]; then
    echo "Running meshping with profiling enabled. Hit ^c to stop."
    COMMAND="python3 -m cProfile -o /tmp/statistico/profile.bin src/meshping.py"
else
    echo "Running meshping. Hit ^c to stop."
    COMMAND="$@"
fi

docker run --rm -it --net=host \
    -v /tmp/statistico:/tmp/statistico \
    -v $PWD/db:/opt/meshping/db \
    -v $PWD/src:/opt/meshping/src \
    -v $PWD/ui/src:/opt/meshping/ui/src \
    meshping:latest-dev \
    $COMMAND
