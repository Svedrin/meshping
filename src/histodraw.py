#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import socket

from PIL import Image, ImageDraw, ImageFont

def render(target, histograms_df):
    # Normalize Buckets by transforming the number of actual pings sent
    # into a float [0..1] indicating the grayness of that bucket.
    biggestbkt = histograms_df.max().max()
    normalized_df = histograms_df.div(biggestbkt, axis="index")
    # prune outliers -> keep only values > 0.05%
    pruned_df = normalized_df[normalized_df > 0.05]
    # drop columns that contain only NaNs now
    dropped_df = pruned_df.dropna(axis="columns", how="all")
    # replace all the _remaining_ NaNs with 0
    histograms_df = dropped_df.fillna(0)

    # detect dynamic range, and round to the nearest multiple of 10.
    # this ensures that the ticks are drawn at powers of 2, which makes
    # the graph more easily understandable. (I hope.)
    # Btw:  27 // 10 * 10   # =  20
    #      -27 // 10 * 10   # = -30
    # hmax needs to be nearest power of 10 + 1 for the top tick to be drawn.
    hmin = histograms_df.columns.min() // 10 * 10
    hmax = histograms_df.columns.max() // 10 * 10 + 11

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

    graph = graph.resize((width, height), Image.NEAREST)

    # position of the graph
    graph_x = 70
    graph_y = 40

    # im will hold the output image
    im = Image.new("RGB", (graph_x + width + 20, graph_y + height + 100), "white")
    im.paste(graph, (graph_x, graph_y))

    # draw a rect around the graph
    draw = ImageDraw.Draw(im)
    draw.rectangle((graph_x, graph_y, graph_x + width - 1, graph_y + height - 1), outline=0x333333)

    try:
        font   = ImageFont.truetype("DejaVuSansMono.ttf", 10)
        lgfont = ImageFont.truetype("DejaVuSansMono.ttf", 16)
    except IOError:
        font   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 10)
        lgfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)

    # Headline
    if target.name == target.addr:
        headline_text = u"%s → %s" % (socket.gethostname(), target.name)
    else:
        headline_text = u"%s → %s (%s)" % (socket.gethostname(), target.name, target.addr)

    headline_width, headline_height = draw.textsize(headline_text, font=lgfont)
    draw.text(
        ((graph_x + width + 20 - headline_width) // 2,
         (graph_y - headline_height) // 2 - 1),
        headline_text, 0x000000, font=lgfont
    )

    # Y axis ticks and annotations
    for hidx in range(hmin, hmax, 5):
        bottomrow = (hidx - hmin)
        offset_y = height + graph_y - bottomrow * sqsz - 1
        draw.line((graph_x - 2, offset_y, graph_x + 2, offset_y), fill=0xAAAAAA)

        ping = 2 ** (hidx / 10.)
        label = "%.2f" % ping
        draw.text((graph_x - len(label) * 6 - 10, offset_y - 5), label, 0x333333, font=font)

    # X axis ticks
    for col, (tstamp, _) in list(enumerate(histograms_df.iterrows()))[::3]:
        offset_x = graph_x + col * 8
        draw.line((offset_x, height + graph_y - 2, offset_x, height + graph_y + 2), fill=0xAAAAAA)

    # X axis annotations
    # Create a temp image for the bottom label that we then rotate by 90° and attach to the other one
    # since this stuff is rotated by 90° while we create it, all the coordinates are inversed...
    tmpim = Image.new("RGB", (80, width + 20), "white")
    tmpdraw = ImageDraw.Draw(tmpim)

    for col, (tstamp, _) in list(enumerate(histograms_df.iterrows()))[::6]:
        offset_x = col * 8
        tmpdraw.text(( 6, offset_x + 0), tstamp.strftime("%Y-%m-%d"), 0x333333, font=font)
        tmpdraw.text((18, offset_x + 8), tstamp.strftime("%H:%M:%S"), 0x333333, font=font)

    im.paste( tmpim.rotate(90, expand=1), (graph_x - 10, height + graph_y + 1) )

    # This worked pretty well for Tobi Oetiker...
    tmpim = Image.new("RGB", (170, 13), "white")
    tmpdraw = ImageDraw.Draw(tmpim)
    tmpdraw.text((0, 0), "Meshping by Michael Ziegler", 0x999999, font=font)
    im.paste( tmpim.rotate(270, expand=1), (width + graph_x + 7, graph_y) )

    return im
