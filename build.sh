#!/bin/bash

set -e
set -u

ROOTDIR="$PWD"

cd "$ROOTDIR/oping-py"
python3 setup.py build
python3 setup.py install
