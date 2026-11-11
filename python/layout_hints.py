"""How node_layout.py arranges the inside of EzCloudShafts: its modules and their Backdrops,
and labels on the Switches."""

MODULES = [
    # (Backdrop label, tile_color, node names it holds as a regex), top to bottom
    ("Inputs", 0x4a5a6aff, r"env|clouds|camera|atmos|sun|PositionPick|NoClouds|CloudsOrNone"),
    ("Sun colour from atmos", 0x7a6a3aff, r"AtmosSunPick|NoAtmos|AtmosOrNone"),
    ("Work resolution", 0x4a5a6aff, r"WorkPos.*"),
    ("Gobo passes", 0x3a5a4aff, r"Pass_.*|Full_.*|Soft_.*"),
    ("AOV layers", 0x6a4a4aff, r"Layer_.*"),
    ("Comp", 0x3a4a6aff, r"SunPick|SunOrBeauty|Comp_.*"),
    ("Views", 0x5a4a6aff, r"ShaftsOver|ShadowView|ShaftsMatteView"),
    # Its own band, so the pipes into it come in along rails rather than across the views.
    ("View output", 0x5a4a6aff, r"ViewOutput"),
    ("Output", 0x6a4a4aff, r"MainRGB|Output\d*"),
]

LEFT = []

LABELS = {
    "CloudsOrNone": "clouds plugged in",
    "AtmosOrNone": "atmos plugged in",
    "ViewOutput": "view",
    "SunOrBeauty": "sun light layer",
}

DIRECT = []

HINTS = {"modules": MODULES, "left": LEFT, "labels": LABELS, "direct": DIRECT}
