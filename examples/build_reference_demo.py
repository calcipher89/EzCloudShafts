"""Build examples/EzCloudShafts_reference_demo.nk: crepuscular rays over layered mountain ridges.

    Nuke15.1.exe --nukex -i --gpu -t examples/build_reference_demo.py --render

The env and clouds "renders" are BlinkScript ray casts (examples/reference_scene.blink), compiled
into the script, so the .nk reads no files. The scene is in decimetres (units to metres 0.1).
"""

import math
import os
import re
import sys
import time

import nuke

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_demo as bd  # noqa: E402

KERNEL_FILE = os.path.join(bd.HERE, "reference_scene.blink").replace("\\", "/")
OUT_NK = os.path.join(bd.HERE, "EzCloudShafts_reference_demo.nk").replace("\\", "/")
UNIT, FRAME, WIDTH, HEIGHT = 10.0, 1001, 1920, 1080

# ---- The scene, in metres -----------------------------------------------------------------
CAM_Y, PITCH, FOCAL, HAP, VAP = 1200.0, 1.5, 40.0, 36.0, 20.25
CLOUD_H = 3000.0
SUN_ELEV, SUN_AZ = 15.0, 3.0
SUN = (math.cos(math.radians(SUN_ELEV)) * math.sin(math.radians(SUN_AZ)),
       math.sin(math.radians(SUN_ELEV)),
       -math.cos(math.radians(SUN_ELEV)) * math.cos(math.radians(SUN_AZ)))
GAP_BIAS, CLOUD_SCALE = 0.0, 1.0

SETTINGS = {"view": "Comp", "scene_scale": 0.1, "cloud_height": CLOUD_H, "shaft_density": 0.12,
            "haze_height": 1.3, "sky_distance": 45.0, "max_distance": 45.0, "march_steps": 128, "samples": 8,
            "penumbra": 0.4, "shaft_intensity": 0.24, "shafts_resolution": "Same",
            "shaft_color": [0.9, 0.95, 1.1], "soften": 5,
            # The built-in Comp view.
            "use_sun_layer": True, "sun_layer": "light_sun", "comp_shadow": 1.0, "comp_haze": 1.0,
            "comp_haze_color": [0.06, 0.13, 0.33], "comp_haze_falloff": [0.75, 1.0, 1.4],
            "comp_haze_shadow": 0.35, "comp_haze_lit": 1.5, "comp_shafts": 1.0}


def blink(name, src, mode):
    n = nuke.nodes.BlinkScript(name=name)
    n["kernelSourceFile"].setValue(KERNEL_FILE)
    n["reloadKernelSourceFile"].execute()
    n["recompile"].execute()
    n.setInput(0, src)
    k = "RefScene_"
    n[k + "mode"].setValue(mode)
    n[k + "cam_y"].setValue(CAM_Y)
    n[k + "pitch"].setValue(PITCH)
    n[k + "focal"].setValue(FOCAL)
    n[k + "haperture"].setValue(HAP)
    n[k + "vaperture"].setValue(VAP)
    n[k + "frame_size"].setValue([WIDTH, HEIGHT])
    n[k + "sun_dir"].setValue(list(SUN))
    n[k + "cloud_h"].setValue(CLOUD_H)
    n[k + "unit"].setValue(UNIT)
    n[k + "gap_bias"].setValue(GAP_BIAS)
    n[k + "cloud_scale"].setValue(CLOUD_SCALE)
    return n


def copy3(name, b, a, layer, label=""):
    n = nuke.nodes.Copy(name=name, label=label, from0="rgba.red", to0=layer + ".red", from1="rgba.green",
                        to1=layer + ".green", from2="rgba.blue", to2=layer + ".blue")
    n.setInput(0, b)
    n.setInput(1, a)
    return n


def build():
    nuke.scriptClear()
    root = nuke.root()
    root["format"].setValue("HD_1080")
    root["first_frame"].setValue(FRAME)
    root["last_frame"].setValue(FRAME)
    nuke.frame(FRAME)
    nuke.Layer("P", ["P.red", "P.green", "P.blue"])
    nuke.Layer("light_sun", ["light_sun.red", "light_sun.green", "light_sun.blue"])

    # Env: col 0 trunk; sun light on col 1.
    env_fmt = bd.place(nuke.nodes.Constant(name="EnvFormat", channels="rgba"), 0, 0)
    terrain_p = bd.place(blink("TerrainP", env_fmt, 0), 0, 1)
    terrain_dot = bd.dot(terrain_p, 1, 1)
    ambient = bd.place(blink("LightAmbient", terrain_p, 1), 0, 3)
    sunlight = bd.place(blink("LightSun", terrain_dot, 2), 1, 3)
    p_copy = copy3("EnvP", ambient, bd.dot(terrain_dot, 2, 5), "P", "world position, sky 0")
    bd.place(p_copy, 0, 5)
    sun_dot = bd.dot(sunlight, 1, 7)
    sun_copy = copy3("EnvSunLayer", p_copy, sun_dot, "light_sun", "the sun light group")
    bd.place(sun_copy, 0, 7)
    # The beauty: the sum of its light groups, as a render would give it.
    beauty = bd.expression("EnvBeauty", sun_copy,
                           ["r+light_sun.red", "g+light_sun.green", "b+light_sun.blue", None],
                           label="beauty = ambient + sun")
    bd.place(beauty, 0, 8)
    env_raw = bd.dot(beauty, -1, 8, label="raw env")

    # Clouds render.
    cl_fmt = bd.place(nuke.nodes.Constant(name="CloudFormat", channels="rgba"), 3, 0)
    cl_over = nuke.nodes.Crop(name="Overscan", label="overscan in the bbox, generous at the top", crop=False)
    cl_over["box"].setValue([-240, -160, WIDTH + 240, HEIGHT + 420])
    cl_over.setInput(0, cl_fmt)
    bd.place(cl_over, 3, 1)
    cl_rgba = bd.place(blink("CloudRGBA", cl_over, 3), 3, 3)
    cl_depth_dot = bd.dot(cl_over, 4, 1)
    cl_depth = bd.place(blink("CloudDepth", cl_depth_dot, 4), 4, 3)
    cl_copy = nuke.nodes.Copy(name="CloudDepthZ", from0="rgba.red", to0="depth.Z",
                              label="depth.Z, Planar Z in scene units")
    cl_copy.setInput(0, cl_rgba)
    cl_copy.setInput(1, bd.dot(cl_depth, 4, 5))
    bd.place(cl_copy, 3, 5)

    cl_dot = bd.dot(cl_copy, 3, 10)
    # Clouds only over sky: the terrain's alpha holds them out.
    over = nuke.nodes.Merge2(name="CloudsOverSky", operation="over", bbox="B", maskChannelInput="rgba.alpha",
                             invert_mask=True, label="clouds over sky; env alpha holds them out")
    over.setInput(0, beauty)
    over.setInput(1, cl_dot)
    mask_dot = bd.dot(beauty, 1, 10)
    over.setInput(2, mask_dot)
    bd.place(over, 0, 10)

    # Camera, sun, atmos.
    camera = nuke.nodes.Camera3(name="ShotCamera", label="1200 m up, 40 mm, pitched 1.5 deg up")
    camera["translate"].setValue([0, CAM_Y * UNIT, 0])
    camera["rotate"].setValue([PITCH, 0, 0])
    camera["focal"].setValue(FOCAL)
    camera["haperture"].setValue(HAP)
    camera["vaperture"].setValue(VAP)
    camera["far"].setValue(2000000)
    bd.place(camera, 6, 4)
    axis = nuke.nodes.Axis3(name="Sun", label="15 deg up, 3 deg right, top of frame")
    axis["translate"].setValue([s * 10000 for s in SUN])
    bd.place(axis, 10, 4)
    hdri_fmt = nuke.nodes.Constant(name="HDRIFormat", channels="rgba")
    hdri_fmt["format"].setValue(nuke.addFormat("2048 1024 1 EzCloudShafts_demo_latlong"))
    bd.place(hdri_fmt, 8, 0)
    v = "(y+0.5)/height"
    hdri = bd.expression("DummyHDRI", hdri_fmt,
                         ["%s<0.5?0.15:mix(1.0,0.25,%s*2-1)" % (v, v), "%s<0.5?0.14:mix(0.8,0.42,%s*2-1)" % (v, v),
                          "%s<0.5?0.10:mix(0.6,0.85,%s*2-1)" % (v, v), "1"], label="gradient sky lat-long, with alpha")
    bd.place(hdri, 8, 1)
    atmos = bd.paste(bd.ATMOS_GROUP, "Atmos")
    atmos["passes"].setValue("Depth Haze")
    atmos["output_mapping"].setValue("Lat-long")
    atmos["sun_from"].setValue("Axis")
    atmos["light_from_hdri"].setValue(False)
    atmos["scene_scale"].setValue(0.1)
    atmos["units_confirmed"].setValue(True)
    atmos["camera_height"].setValue(CAM_Y)
    atmos["haze_distance"].setValue(45)
    atmos["render_resolution"].setValue("Half")
    atmos.setInput(0, hdri)
    axis_dot = bd.dot(axis, 10, 8)
    atmos.setInput(1, axis_dot)
    bd.place(atmos, 8, 8)

    shafts = bd.paste(bd.SHAFTS_GROUP, "EzCloudShafts")
    for knob, value in SETTINGS.items():
        shafts[knob].setValue(value)
    bd.place(shafts, 0, 13)
    shafts.setInput(0, over)
    clouds_dot = bd.dot(cl_dot, 3, 13)
    shafts.setInput(1, clouds_dot)
    shafts.setInput(2, bd.dot(camera, 6, 12))
    shafts.setInput(3, bd.dot(atmos, 8, 11))
    shafts.setInput(4, bd.dot(axis_dot, 10, 10.5))

    # The node's Comp view does the comp; only a finish after it.
    glow = nuke.nodes.Glow(name="Halation", tolerance=1.4, brightness=0.2, size=16, effect_only=False)
    glow.setInput(0, shafts)
    bd.place(glow, 0, 18)
    grade = nuke.nodes.Grade(name="Finish", label="print-like shoulder")
    grade["white"].setValue(1.0)
    grade.setInput(0, glow)
    bd.place(grade, 0, 19)
    clip = nuke.nodes.SoftClip(name="Shoulder", conversion="logarithmic compress", softclip_min=0.7, softclip_max=1.6)
    clip.setInput(0, grade)
    bd.place(clip, 0, 20)

    fan = bd.dot(clip, 0, 22)
    views = [("Shafts_RGB", "shafts", ("red", "green", "blue"), "shafts.rgb"),
             ("LitShare", "shafts_lit", ("red", "red", "red"), "shafts_lit.rgb"),
             ("CloudShadow_Alpha", "cloudshadow", ("alpha",) * 3, "cloudshadow.a"),
             ("Gobo_Check", "cloudshadow", ("red", "green", "blue"), "Gobo Check")]
    checks, last = [], fan
    src_views = bd.dot(shafts, 1, 16)
    last = src_views
    for i, (name, layer, chans, label) in enumerate(views):
        d = bd.dot(last, i + 1, 21) if i else bd.dot(src_views, 1, 21)
        checks.append(bd.place(bd.to_rgb(name, d, layer, chans, label=label), i + 1, 23))
        last = d
    plate_a = bd.dot(clouds_dot, 3, 14)
    plate_b = bd.dot(plate_a, 5, 14, label="clouds plate")
    plate = nuke.nodes.Crop(name="CloudsPlateFrame", label="clouds plate, cropped to the frame")
    plate["box"].setValue([0, 0, WIDTH, HEIGHT])
    plate.setInput(0, plate_b)
    bd.place(plate, 5, 23)
    env_tile_dot = bd.dot(env_raw, -1, 23)

    panels = [("Final", fan), ("Env raw", env_tile_dot), ("Clouds", plate), ("shafts.rgb", checks[0]),
              ("shafts_lit", checks[1]), ("cloudshadow.a", checks[2]), ("Gobo Check", checks[3])]
    sheet_nodes, labelled = [], []
    cols = [0, -1, 5, 1, 2, 3, 4]
    for i, (title, src) in enumerate(panels):
        c = cols[i]
        rf = nuke.nodes.Reformat(name="Panel%d" % (i + 1), type="to box", box_width=720, box_height=405,
                                 box_fixed=True, resize="distort", black_outside=True)
        rf.setInput(0, src)
        bd.place(rf, c, 25)
        bar = nuke.nodes.Rectangle(name="LabelBar%d" % (i + 1), color=0, opacity=0.7)
        bar["area"].setValue([0, 357, 720, 405])
        bar.setInput(0, rf)
        bd.place(bar, c, 26)
        tx = nuke.nodes.Text2(name="Label%d" % (i + 1), message=title)
        tx["box"].setValue([18, 360, 700, 402])
        tx["yjustify"].setValue("center")
        tx["global_font_scale"].setValue(0.26)
        tx.setInput(0, bar)
        bd.place(tx, c, 27)
        labelled.append(tx)
        sheet_nodes += [rf, bar, tx]
    sheet = nuke.nodes.ContactSheet(name="ContactSheet", width=2880, height=810, rows=2, columns=4, gap=0,
                                    roworder="TopBottom", colorder="LeftRight", center=True)
    for i, tx in enumerate(labelled):
        sheet.setInput(i, tx)
    bd.place(sheet, 0, 29)
    w_sheet = nuke.nodes.Write(name="WriteSheet", file_type="jpeg", channels="rgb")
    w_sheet["file"].fromUserText("[file dirname [value root.name]]/EzCloudShafts_reference_demo_sheet.jpg")
    w_sheet["_jpeg_quality"].setValue(0.93)
    w_sheet.setInput(0, sheet)
    bd.place(w_sheet, 0, 30)
    w_final = nuke.nodes.Write(name="WriteFinal", file_type="jpeg", channels="rgb")
    w_final["file"].fromUserText("[file dirname [value root.name]]/EzCloudShafts_reference_demo_final.jpg")
    w_final["_jpeg_quality"].setValue(0.95)
    w_final.setInput(0, bd.dot(fan, -2, 22))
    bd.place(w_final, -2, 24)
    viewer = nuke.nodes.Viewer(name="Viewer1")
    viewer.setInput(0, clip)
    bd.place(viewer, -3, 20)

    bd.backdrop([env_fmt, terrain_p, ambient, sunlight, p_copy, sun_copy], "Env render (light groups + P)", bd.SLATE)
    bd.backdrop([cl_fmt, cl_over, cl_rgba, cl_depth, cl_copy], "Clouds render (rgba + depth.Z)", bd.SLATE)
    bd.backdrop([camera], "Shot camera", bd.OCHRE)
    bd.backdrop([hdri_fmt, hdri, atmos], "HDRI + atmos colour", bd.OCHRE)
    bd.backdrop([axis], "Sun", bd.OCHRE)
    bd.backdrop([shafts, glow, grade, clip], "EzCloudShafts (Comp view) + finish", bd.GREEN)
    bd.backdrop(checks + [plate], "Layer checks", bd.RED)
    bd.backdrop(sheet_nodes, "Contact sheet", bd.GREY)
    note = nuke.nodes.StickyNote(name="ReadMe", note_font_size=16, label=readme())
    note.setXYpos(-6 * bd.COL - 240, 0)
    bd.check_layout()
    return shafts, w_sheet, w_final


def readme():
    return "\n".join([
        "EzCloudShafts reference demo: crepuscular rays over ridges. Synthetic, no files read. Decimetres.",
        "",
        "EzCloudShafts view Comp does the recipe; press its 'layer breakout' to see it as nodes:",
        "  land = env - light_sun * (1 - cloudshadow.a) * cloud shadow",
        "  T = (1 - shafts_lit.a) ^ (haze amount * haze falloff)",
        "  final = land * T  +  haze colour * (1-T) * grade(shafts_lit)  +  shafts.rgb",
        "  Comp knobs: cloud shadow %g, haze amount %g, haze colour %g %g %g," % (
            SETTINGS["comp_shadow"], SETTINGS["comp_haze"], *SETTINGS["comp_haze_color"]),
        "  haze falloff %g %g %g, haze in shadow %g, haze in sun %g, shafts %g." % (
            *SETTINGS["comp_haze_falloff"], SETTINGS["comp_haze_shadow"], SETTINGS["comp_haze_lit"],
            SETTINGS["comp_shafts"]),
        "",
        "EzCloudShafts: cloud height %g m, haze %g /km, haze height %g km," % (
            CLOUD_H, SETTINGS["shaft_density"], SETTINGS["haze_height"]),
        "  steps %d, softness %g deg, intensity %g, soften 5, shafts at Same." % (
            SETTINGS["march_steps"], SETTINGS["penumbra"], SETTINGS["shaft_intensity"]),
        "",
        "What makes the look: a high camera over valleys, the sun ahead and in frame, many gaps",
        "around the sun's point on the deck, and dark land for the beams to read against.",
        "The env and clouds are BlinkScript ray casts: heavy on CPU, and moving ShotCamera",
        "does not re-render them.",
    ])


def strip_source_paths(path):
    """The kernels are inlined in kernelSource; drop the path they were loaded from."""
    with open(path) as f:
        text = f.read()
    text = re.sub(r"^ kernelSourceFile .*\n", "", text, flags=re.M)
    with open(path, "w") as f:
        f.write(text)


if __name__ == "__main__":
    shafts_node, sheet_write, final_write = build()
    nuke.scriptSaveAs(OUT_NK, overwrite=1)
    strip_source_paths(OUT_NK)
    print("saved", OUT_NK)
    if "--render" in sys.argv:
        nuke.message = print
        shafts_node["analyze"].execute()
        shafts_node["cloud_height"].setValue(CLOUD_H)
        start = time.time()
        nuke.execute(final_write, FRAME, FRAME)
        print("final frame seconds", round(time.time() - start, 1))
        nuke.execute(sheet_write, FRAME, FRAME)
