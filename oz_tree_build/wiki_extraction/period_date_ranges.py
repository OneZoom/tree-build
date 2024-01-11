"""
Maps periods/ages/stages/etc names to their date ranges.
Ranges come from https://en.wikipedia.org/wiki/Geologic_time_scale
"""

import logging

PERIOD_LOOKUP = {
    "carboniferous": [358.9, 298.9],  # Period
    "early carboniferous": [358.9, 330.9],  # subperiod (==Mississippian)
    "mississippian": [358.9, 323.2],  # subperiod (==Early Carboniferous)
    "tournaisian": [358.9, 346.7],
    "viséan": [346.7, 330.9],
    "serpukhovian": [330.9, 323.2],
    "late carboniferous": [323.2, 298.9],  # subperiod (==Pennsylvanian)
    "pennsylvanian": [323.2, 298.9],  # subperiod (==Late Carboniferous)
    "bashkirian": [323.2, 315.2],
    "moscovian": [315.2, 307],
    "kasimovian": [307, 303.7],
    "gzhelian": [303.7, 298.9],
    "permian": [298.9, 251.9],  # Period
    "early permian": [298.9, 273.01],  # subperiod (==Cisuralian)
    "cisuralian": [298.9, 273.01],  # subperiod (==Early Permian)
    "asselian": [298.9, 293.52],
    "sakmarian": [293.52, 290.1],
    "artinskian": [290.1, 283.5],
    "kungurian": [283.5, 273.01],
    "middle permian": [273.01, 259.51],  # subperiod (Guadalupian)
    "roadian": [273.01, 266.9],
    "wordian": [266.9, 264.28],
    "capitanian": [264.28, 259.51],
    "late permian": [259.51, 251.9],  # subperiod (Lopingian)
    "wuchiapingian": [259.51, 254.14],
    "changhsingian": [254.14, 251.9],
    "triassic": [251.9, 201.4],  # Period
    "early triassic": [251.9, 247.2],  # subperiod
    "induan": [251.9, 251.2],
    "olenekian": [251.2, 247.2],
    "middle triassic": [247.2, 237],  # subperiod
    "anisian": [247.2, 242],
    "ladinian": [242, 237],
    "late triassic": [237, 201.4],  # subperiod
    "carnian": [237, 227],
    "norian": [227, 208.5],
    "rhaetian": [208.5, 201.4],
    "jurassic": [201.4, 145],  # Period
    "early jurassic": [201.4, 174.7],  # subperiod
    "hettangian": [201.4, 199.5],
    "sinemurian": [199.5, 192.9],
    "pliensbachian": [192.9, 184.2],
    "toarcian": [184.2, 174.7],
    "middle jurassic": [174.7, 161.5],  # subperiod
    "aalenian": [174.7, 170.9],
    "bajocian": [170.9, 168.2],
    "bathonian": [168.2, 165.3],
    "callovian": [165.3, 161.5],
    "late jurassic": [161.5, 145],  # subperiod
    "oxfordian": [161.5, 154.8],
    "kimmeridgian": [154.8, 149.2],
    "tithonian": [149.2, 145],
    "cretaceous": [145, 66],  # Period
    "early cretaceous": [145, 100.5],
    "lower cretaceous": [145, 100.5],
    "berriasian": [145, 139.8],
    "valanginian": [139.8, 132.6],
    "hauterivian": [132.6, 125.77],
    "barremian": [125.77, 121.4],
    "aptian": [121.4, 113],
    "albian": [113, 100.5],
    "late cretaceous": [100.5, 66],
    "upper cretaceous": [100.5, 66],
    "cenomanian": [100.5, 93.9],
    "turonian": [93.9, 89.8],
    "coniacian": [89.8, 86.3],
    "santonian": [86.3, 83.6],
    "campanian": [83.6, 72.1],
    "maastrichtian": [72.1, 66],
    "paleogene": [66, 23.03],
    "paleocene": [66, 56],
    "danian": [66, 61.6],
    "selandian": [61.6, 59.2],
    "thanetian": [59.2, 56],
    "eocene": [56, 33.9],
    "ypresian": [56, 47.8],
    "lutetian": [47.8, 41.2],
    "bartonian": [41.2, 37.71],
    "priabonian": [37.71, 33.9],
    "oligocene": [33.9, 23.03],
    "rupelian": [33.9, 27.82],
    "chattian": [27.82, 23.03],
    "neogene": [23.03, 2.588],
    "miocene": [23.03, 5.333],
    "aquitanian": [23.03, 20.44],
    "burdigalian": [20.44, 15.97],
    "langhian": [15.97, 13.82],
    "serravallian": [13.82, 11.63],
    "tortonian": [11.63, 7.246],
    "messinian": [7.246, 5.333],
    "pliocene": [5.333, 2.58],
    "zanclean": [5.333, 3.6],
    "piacenzian": [3.6, 2.58],
    "quaternary": [2.58, 0],
    "pleistocene": [2.58, 0.0117],
    "gelasian": [2.58, 1.8],
    "calabrian": [1.8, 0.774],
    "chibanian": [0.774, 0.129],
    "late pleistocene": [0.129, 0.0117],
    "holocene": [0.0117, 0],
    "recent": [0, 0],
}


def map_period_name_to_range(period_name):
    period_name = period_name.lower()
    if period_name in PERIOD_LOOKUP:
        return PERIOD_LOOKUP[period_name]

    logging.warning(f"Unknown period name: {period_name}")
    return None
