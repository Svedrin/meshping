#!/bin/bash

set -e
set -u

ROOTDIR="$PWD"

cd "$ROOTDIR/oping-py"
python3 setup.py build
ln -sf "$ROOTDIR"/oping-py/build/lib.*/oping.so "$ROOTDIR/src/oping.so"
