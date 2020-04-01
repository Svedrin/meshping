#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import sys
import math

from time import time
from datetime import datetime

import pandas

from PIL import Image, ImageDraw, ImageFont

def render(prometheus_json):
    histograms_df = None

    # Parse Prometheus timeseries into a two-dimensional DataFrame.
    # Columns: t (time), plus one for every Histogram bucket.
    for result in prometheus_json["data"]["result"]:
        bucket = int(math.log(float(result["metric"]["le"]), 2) * 10) - 1
        metric_df = (
            pandas.DataFrame(result["values"], dtype=float, columns=["t", bucket])
                .set_index("t")
        )
        if histograms_df is None:
            histograms_df = metric_df
        elif bucket in histograms_df.columns:
            histograms_df[bucket].update(metric_df[bucket])
        else:
            histograms_df = histograms_df.join(metric_df)

    # Transpose (so that `le` is the first column, rather than `t`), sort and diff
    # (Prometheus uses cumulative histograms rather than absolutes)
    # then transpose back so we can continue our work
    transposed_df = histograms_df.T.sort_index().diff()
    histograms_df = transposed_df.T

    # Normalize Buckets by transforming the number of actual pings sent
    # into a float [0..1] indicating the grayness of that bucket.
    biggestbkt = transposed_df.max()
    normalized_df = histograms_df.div(biggestbkt, axis="index")
    # prune outliers -> keep only values > 0.05%
    pruned_df = normalized_df[normalized_df > 0.05]
    # drop columns that contain only NaNs now
    dropped_df = pruned_df.dropna(axis="columns", how="all")
    # replace all the _remaining_ NaNs with 0
    histograms_df = dropped_df.fillna(0)

    # detect dynamic range
    hmin = histograms_df.columns.min()
    hmax = histograms_df.columns.max()

    rows = hmax - hmin + 1
    cols = len(histograms_df)

    # How big do you want the squares to be?
    sqsz = 8

    # Draw the graph in a pixels array which we then copy to an image
    width  = cols
    height = rows
    pixels = [0xFF] * (width * height)

    for col, (tstamp, histogram) in enumerate(histograms_df.iterrows()):
        for bktval, bktgrayness in histogram.items():
            pixelval = int((1.0 - bktgrayness) * 0xFF)
            #       (     y       )            (x)
            pixels[((hmax - bktval) * width) + col] = pixelval

    # copy pixels to an Image and paste that into the output image
    graph = Image.new("L", (width, height), "white")
    graph.putdata(pixels)

    # Scale graph so each Pixel becomes a square
    width  *= sqsz
    height *= sqsz

    graph = graph.resize((width, height))

    # X position of the graph
    graph_x = 70

    # im will hold the output image
    im = Image.new("RGB", (width + graph_x + 20, height + 100), "white")
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

        ping = 2 ** (hidx / 10.)
        label = "%.2f" % ping
        draw.text((graph_x - len(label) * 6 - 10, offset_y - 5), label, 0x333333, font=font)

    # X axis ticks
    for col, (tstamp, _) in list(enumerate(histograms_df.iterrows()))[::3]:
        offset_x = graph_x + col * 8
        draw.line((offset_x, height - 2, offset_x, height + 2), fill=0xAAAAAA)

    # X axis annotations
    # Create a temp image for the bottom label that we then rotate by 90° and attach to the other one
    # since this stuff is rotated by 90° while we create it, all the coordinates are inversed...
    tmpim = Image.new("RGB", (80, width + 20), "white")
    tmpdraw = ImageDraw.Draw(tmpim)

    for col, (tstamp, _) in list(enumerate(histograms_df.iterrows()))[::6]:
        dt = datetime.fromtimestamp(tstamp)
        offset_x = col * 8
        tmpdraw.text(( 6, offset_x + 0), dt.strftime("%Y-%m-%d"), 0x333333, font=font)
        tmpdraw.text((18, offset_x + 8), dt.strftime("%H:%M:%S"), 0x333333, font=font)

    im.paste( tmpim.rotate(90, expand=1), (graph_x - 10, height + 1) )

    # This worked pretty well for Tobi Oetiker...
    tmpim = Image.new("RGB", (170, 11), "white")
    tmpdraw = ImageDraw.Draw(tmpim)
    tmpdraw.text((0, 0), "Meshping by Michael Ziegler", 0x999999, font=font)
    im.paste( tmpim.rotate(270, expand=1), (width + graph_x + 9, 0) )

    return im


def main():
    if len(sys.argv) != 5:
        print("Usage: %s <prometheus URL> <pingnode> <target> <output.png>" % sys.argv[0], file=sys.stderr)
        return 2

    _, prometheus, pingnode, target, outfile = sys.argv

    response = requests.get(prometheus + "/api/v1/query_range", timeout=2, params={
        "query": 'increase(meshping_pings_bucket{instance="%s",name="%s"}[1h])' % (pingnode, target),
        "start": time() - 3 * 24 * 60 * 60,
        "end":   time(),
        "step":  3600,
    }).json()

    assert response["status"] == "success", "Prometheus query failed"
    assert response["data"]["result"], "Result is empty"

    im = render(response)

    if sys.argv[2] != "-":
        im.save(outfile)
    else:
        im.save(sys.stdout, format="png")

    return 0


if __name__ == '__main__':
    import requests
    sys.exit(main())
