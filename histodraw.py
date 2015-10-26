#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

from __future__ import division

import sys
import json
import math

from time import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

base = 2


def main():
    if len(sys.argv) != 3:
        print >> sys.stderr, "Usage: %s <logfile.txt> <output.png>" % sys.argv[0]
        return 2

    histograms = []
    hmin = None
    hmax = None

    # Parse the logfile
    for line in open(sys.argv[1], "r"):
        tstamp, data = line.strip().split(' ', 1)
        tstamp = int(tstamp)
        data   = dict([(int(x), y) for (x, y) in json.loads(data).items()])

        biggestbkt = 0
        for bktval, bktcount in data.items():
            biggestbkt = max(biggestbkt, bktcount)

        histograms.append((tstamp, data, biggestbkt))

    # prune outliers, detect dynamic range
    for (tstamp, data, biggestbkt) in histograms:
        for bktval, bktcount in data.items():
            if bktcount / biggestbkt < 0.05:
                # outliers <5% which would be barely visible in the graph anyway
                del data[bktval]
            else:
                if hmin is None:
                    hmin = bktval
                else:
                    hmin = min(hmin, bktval)
                hmax = max(hmax, bktval)

    print >> sys.stderr, "hmin =", hmin
    print >> sys.stderr, "hmax =", hmax

    rows = hmax - hmin
    print >> sys.stderr, "rows =", rows
    cols = len(histograms)

    # How big do you want the squares to be?
    sqsz = 8

    # Draw the graph in a pixels array which we then copy to an image
    width  = cols * sqsz
    height = rows * sqsz
    pixels = [(0xFF, 0xFF, 0xFF)] * (width * height)

    for col, (tstamp, histogram, biggestbkt) in enumerate(histograms):
        for bktval, bktcount in histogram.items():
            bottomrow = (bktval - hmin)
            toprow    = bottomrow + 1
            pixelval  = 0xFF - int(bktcount / biggestbkt * 0xFF)

            offset_x = col * sqsz
            offset_y = height - toprow * sqsz - 1

            for y in range(0, sqsz):
                for x in range(0, sqsz):
                    pixels[(offset_y + y) * width + (offset_x + x)] = (pixelval, ) * 3

    # X position of the graph
    graph_x = 70

    # im will hold the output image
    im = Image.new("RGB", (width + graph_x + 20, height + 100), "white")

    # copy pixels to an Image and paste that into the output image
    graph = Image.new("RGB", (width, height), "white")
    graph.putdata(pixels)
    im.paste(graph, (graph_x, 0))

    # draw a rect around the graph
    draw = ImageDraw.Draw(im)
    draw.rectangle((graph_x, 0, graph_x + width - 1, height - 1), outline=0x333333)

    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
    except IOError:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 10)

    # Y axis ticks and annotations
    for hidx in range(hmin, hmax, 5):
        bottomrow = (hidx - hmin)
        offset_y = height - bottomrow * sqsz - 1
        draw.line((graph_x - 2, offset_y, graph_x + 2, offset_y), fill=0xAAAAAA)

        ping = base ** (hidx / 10.)
        label = "%.2f" % ping
        draw.text((graph_x - len(label) * 6 - 10, offset_y - 5), label, 0x333333, font=font)

    # X axis ticks
    for col, (tstamp, _, _) in list(enumerate(histograms))[::3]:
        offset_x = graph_x + col * 8
        draw.line((offset_x, height - 2, offset_x, height + 2), fill=0xAAAAAA)

    # X axis annotations
    # Create a temp image for the bottom label that we then rotate by 90° and attach to the other one
    # since this stuff is rotated by 90° while we create it, all the coordinates are inversed...
    tmpim = Image.new("RGB", (80, width + 20), "white")
    tmpdraw = ImageDraw.Draw(tmpim)

    for col, (tstamp, _, _) in list(enumerate(histograms))[::6]:
        dt = datetime.fromtimestamp(tstamp)
        offset_x = col * 8
        tmpdraw.text(( 6, offset_x + 0), dt.strftime("%Y-%m-%d"), 0x333333, font=font)
        tmpdraw.text((18, offset_x + 8), dt.strftime("%H:%M:%S"), 0x333333, font=font)

    im.paste( tmpim.rotate(90), (graph_x - 10, height + 1) )

    # This worked pretty well for Tobi Oetiker...
    tmpim = Image.new("RGB", (170, 11), "white")
    tmpdraw = ImageDraw.Draw(tmpim)
    tmpdraw.text((0, 0), "Meshping by Michael Ziegler", 0x999999, font=font)
    im.paste( tmpim.rotate(270), (width + graph_x + 9, 0) )

    if sys.argv[2] != "-":
        im.save(sys.argv[2])
    else:
        im.save(sys.stdout, format="png")

    return 0


if __name__ == '__main__':
    sys.exit(main())
