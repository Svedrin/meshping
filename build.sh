#!/bin/bash

ROOTDIR="$(hg root)"

cd "$ROOTDIR/oping-py"
python setup.py build
ln -sf "$ROOTDIR/oping-py/build/lib.linux-x86_64-2.7/oping.so" "$ROOTDIR/src/oping.so"
