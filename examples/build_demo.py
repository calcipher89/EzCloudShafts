"""Build examples/EzCloudShafts_demo.nk: a synthetic scene to see EzCloudShafts working.

Run with NukeX (the passes are BlinkScript):

    Nuke15.1.exe --nukex -i -t examples/build_demo.py            # build and save the script
    Nuke15.1.exe --nukex -i -t examples/build_demo.py --render   # also render the contact sheet

Everything in the script is made with Nuke nodes: the "renders" are ray casts in Expression
nodes, so the .nk reads no files. The scene is in decimetres (units to metres 0.1).
"""

import math
import os
import sys

import nuke

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.dirname(ROOT)
SHAFTS_GROUP = os.path.join(ROOT, "groups", "EzCloudShafts_group.nk")
ATMOS_GROUP = os.path.join(PLUGINS, "EzAtmosScatter", "groups", "EzAtmosScatter_group.nk")
OUT_NK = os.path.join(HERE, "EzCloudShafts_demo.nk").replace("\\", "/")

# ---- The scene, in metres (the nodes get decimetres) --------------------------------------
UNIT = 10.0                  # scene units per metre
FRAME = 1001
WIDTH, HEIGHT = 1920, 1080
OVERSCAN = 160
CAM_Y = 30.0
PITCH = 4.0                  # degrees up
FOCAL, HAP, VAP = 35.0, 36.0, 20.25
CLOUD_H = 1500.0
RIDGE_Z = 4000.0             # the ridge stands this far down -Z
SUN_ELEV = 16.0
SUN_AZ = 6.0                 # degrees to the right of where the camera looks
SUN = (math.cos(math.radians(SUN_ELEV)) * math.sin(math.radians(SUN_AZ)),
       math.sin(math.radians(SUN_ELEV)),
       -math.cos(math.radians(SUN_ELEV)) * math.cos(math.radians(SUN_AZ)))
# Where the ray from the camera to the sun meets the cloud sheet, in km: the beams fan out
# from here, so the gaps sit around it.
SX = SUN[0] / SUN[1] * (CLOUD_H - CAM_Y) / 1000.0
SZ = SUN[2] / SUN[1] * (CLOUD_H - CAM_Y) / 1000.0
# Gaps in the sheet, relative to that point, in km: (dx, dz, radius x, radius z).
HOLES = [(-1.0, 0.2, 0.35, 0.5), (0.9, 0.35, 0.3, 0.45), (-0.3, 1.0, 0.3, 0.3),
         # Inside the wedge of sheet that the visible ground looks up to, so the ground gets
         # sun patches and the air over it gets beams.
         (-0.25, -0.7, 0.22, 0.3), (0.35, -1.3, 0.25, 0.38), (-0.7, -1.9, 0.3, 0.45),
         (0.85, -2.3, 0.38, 0.5), (0.0, -3.0, 0.4, 0.55), (-1.4, -3.2, 0.45, 0.6),
         (1.6, -3.3, 0.5, 0.6),
         # Open sky either side.
         (-3.3, -1.8, 0.9, 1.0), (3.2, -1.4, 0.8, 1.0)]

# ---- EzCloudShafts settings ---------------------------------------------------------------
SETTINGS = {"view": "Shafts Over Env", "scene_scale": 0.1, "cloud_height": CLOUD_H,
            "shaft_density": 0.25, "haze_height": 1.2, "sky_distance": 20.0,
            "march_steps": 96, "samples": 8, "penumbra": 0.5, "shaft_intensity": 0.3,
            "shafts_resolution": "Same"}

# ---- Layout (nuke-node-layout grid) -------------------------------------------------------
COL, ROW = 150, 48
SLATE, OCHRE, GREEN, PURPLE, RED, GREY = (0x4a5a6aff, 0x7a6a3aff, 0x3a5a4aff, 0x5a4a6aff,
                                          0x6a4a4aff, 0x444444ff)


def place(node, col, row):
    node.setXYpos(int(col * COL), int(row * ROW))
    return node


def dot(src, col, row, label=""):
    d = nuke.nodes.Dot(label=label)
    d.setInput(0, src)
    d.setXYpos(int(col * COL + 34), int(row * ROW + 3))
    return d


def backdrop(nodes, label, color, z=0):
    xs = [n.xpos() for n in nodes]
    ys = [n.ypos() for n in nodes]
    bd = nuke.nodes.BackdropNode(label=label, tile_color=color, note_font_size=32, z_order=z)
    bd.setXYpos(min(xs) - 40, min(ys) - 70)
    bd["bdwidth"].setValue(max(xs) + 80 - min(xs) + 80)
    bd["bdheight"].setValue(max(ys) + 18 - min(ys) + 110)
    return bd


def check_layout():
    ns = [n for n in nuke.allNodes() if n.Class() not in ("BackdropNode", "StickyNote", "Viewer")]
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            if abs(a.xpos() - b.xpos()) < 86 and abs(a.ypos() - b.ypos()) < 24:
                raise RuntimeError("stacked nodes: %s, %s" % (a.name(), b.name()))
        for k in range(a.inputs()):
            src = a.input(k)
            # A Dot beside a node on its row sits 3 lower, so its pipe is still level.
            if src is not None and src.ypos() > a.ypos() + 6:
                raise RuntimeError("upward pipe: %s -> %s" % (src.name(), a.name()))


# ---- Node helpers -------------------------------------------------------------------------

def expression(name, src, exprs, temps=(), label=""):
    """exprs: the four channel expressions (None leaves that channel alone). temps: (name, expr)."""
    n = nuke.nodes.Expression(name=name, label=label)
    n.setInput(0, src)
    for i, (t, e) in enumerate(temps):
        n["temp_name%d" % i].setValue(t)
        n["temp_expr%d" % i].setValue(e)
    for i, (chan, e) in enumerate(zip(("rgba.red", "rgba.green", "rgba.blue", "rgba.alpha"), exprs)):
        if e is None:
            n["channel%d" % i].setValue("none")
        else:
            n["channel%d" % i].setValue(chan)
            n["expr%d" % i].setValue(e)
    return n


def shuffle(name, src, layer, mapping, out="rgba", label=""):
    """mapping: list of ('layer.chan', in index, 'layer.chan', out index)."""
    n = nuke.nodes.Shuffle2(name=name, label=label)
    n.setInput(0, src)
    text = " ".join("%s %d %d %s %d %d" % (a, -1 if a == "black" else 0, i, b, 0, j)
                    for a, i, b, j in mapping)
    n.readKnobs('fromInput1 {{0} B}\nin1 %s\nfromInput2 {{0} B}\nout1 %s\nmappings "%d %s"\n'
                % (layer, out, len(mapping), text))
    return n


def to_rgb(name, src, layer, chans, label=""):
    """chans: the layer's channels for rgb (one name three times for a matte)."""
    idx = {"red": 0, "green": 1, "blue": 2, "alpha": 3}
    mapping = [("%s.%s" % (layer, c), idx[c], "rgba.%s" % o, i)
               for i, (c, o) in enumerate(zip(chans, ("red", "green", "blue")))]
    mapping.append(("black", -1, "rgba.alpha", 3))
    return shuffle(name, src, layer, mapping, label=label)


def paste(path, name):
    before = set(n.name() for n in nuke.allNodes())
    nuke.nodePaste(path.replace("\\", "/"))
    new = [n for n in nuke.allNodes() if n.name() not in before]
    node = [n for n in new if n.Class() in ("Group", "Gizmo")][0]
    node.setName(name)
    node.setSelected(False)
    return node


# ---- Expressions --------------------------------------------------------------------------
# View rays are in world space but not normalised: camera-space z is -1, so the ray parameter
# at a hit is the Planar Z of the hit.
COSP, SINP = math.cos(math.radians(PITCH)), math.sin(math.radians(PITCH))
CX = "(((x+0.5)/width-0.5)*%.8f)" % (HAP / FOCAL)
CY = "(((y+0.5)/height-0.5)*%.8f)" % (VAP / FOCAL)
DY = "(%s*%.8f+%.8f)" % (CY, COSP, SINP)
DZ = "(%s*%.8f-%.8f)" % (CY, SINP, COSP)


def ridge_height(xvar):
    return ("(330+110*sin(%s/1300+0.5)+60*sin(%s/470+2)+45*fBm(%s/380,1.7,3.1,4,2,0.5))"
            % (xvar, xvar, xvar))


def ray_node(name, src):
    return expression(name, src, [CX, DY, DZ, "1"], label="world ray per pixel, z = -1 in camera")


def env_hit(src):
    is_ridge = "(yr>0&&yr<hr)"
    ground = "g<0"
    return expression(
        "EnvHit", src,
        ["%s?xr*%g:(%s?r*%g/(-g)*%g:0)" % (is_ridge, UNIT, ground, CAM_Y, UNIT),
         "%s?yr*%g:0" % (is_ridge, UNIT),
         "%s?%g:(%s?b*%g/(-g)*%g:0)" % (is_ridge, -RIDGE_Z * UNIT, ground, CAM_Y, UNIT),
         "%s?2:(%s?1:0)" % (is_ridge, ground)],
        temps=[("tr", "%g/(-b)" % RIDGE_Z), ("yr", "%g+tr*g" % CAM_Y), ("xr", "tr*r"),
               ("hr", ridge_height("xr"))],
        label="ground plane and ridge: rgb = P, a = 0 sky, 1 ground, 2 ridge")


def env_shade(src):
    hc, zc = (1.05, 0.72, 0.42), (0.22, 0.38, 0.72)
    gc, rc = (0.20, 0.23, 0.11), (0.16, 0.15, 0.15)
    glow = "(0.9*pow(max(sd,0),120)+0.25*pow(max(sd,0),12))"
    disk = "(smoothstep(0.99985,0.99995,sd)*60)"
    exprs = []
    for i, tint in enumerate((1.0, 0.86, 0.62)):
        sky = "mix(%g,%g,smoothstep(0,0.45,el))+%s*%g+%s*%g" % (hc[i], zc[i], glow, tint, disk, tint)
        solid = "mix((a>1.5?%g:%g)*tex,%g,fog)" % (rc[i], gc[i], hc[i])
        exprs.append("a<0.5?%s:%s" % (sky, solid))
    exprs.append("1")
    length = "sqrt(%s*%s+%s*%s+%s*%s)" % (CX, CX, DY, DY, DZ, DZ)
    return expression(
        "EnvShade", src, exprs,
        temps=[("el", "%s/%s" % (DY, length)),
               ("sd", "(%s*%.8f+%s*%.8f+%s*%.8f)/%s" % (CX, SUN[0], DY, SUN[1], DZ, SUN[2], length)),
               ("fog", "1-exp(-sqrt(r*r+g*g+b*b)/%g/6000)" % UNIT),
               ("tex", "0.65+0.9*(0.5+0.5*fBm(r*0.002,b*0.002+g*0.004,1,4,2,0.5))")],
        label="simple sky, ground and ridge colour")


def cloud_hit(src):
    t = "tt"
    return expression(
        "CloudHit", src,
        ["r*%s/1000" % t, "b*%s/1000" % t, "%s*%g" % (t, UNIT), "g>0.003?1:0"],
        temps=[("tt", "g>0.003?%g/g:0" % (CLOUD_H - CAM_Y))],
        label="meets the sheet: r, g = x, z in km, b = Planar Z, a = sheet in view")


def cloud_cover(src):
    return expression(
        "CloudCover", src, [None, None, "mix(cover,0.85,smoothstep(12,30,sqrt(r*r+g*g)))", None],
        temps=[("cover", "smoothstep(-0.42,-0.15,fBm(r*0.45,g*0.45,7.3,4,2,0.5))")],
        label="the sheet: nearly solid cloud, b = opacity")


def hole_term(h):
    dx, dz, rx, rz = h
    d = "sqrt(pow2((r-%.4f)/%g)+pow2((g-%.4f)/%g))+0.22*noise(r*3,g*3,%g)" % (
        SX + dx, rx, SZ + dz, rz, dx)
    return "smoothstep(0.82,1.05,%s)" % d


def cloud_holes(src):
    alpha = "*".join(["a*b"] + [hole_term(h) for h in HOLES])
    return expression("CloudHoles", src, [None, None, None, alpha], label="cuts the gaps around the sun")


def cloud_shade(src):
    # Colour is premultiplied. fBm gives the undersides some variation.
    shade = "(0.45+0.25*fBm(r*1.2,g*1.2,2.1,3,2,0.5))"
    return expression("CloudShade", src, ["a*%s*%g" % (shade, k) for k in (1.0, 0.92, 0.86)] + [None],
                      label="premultiplied cloud colour")


def build():
    nuke.scriptClear()
    root = nuke.root()
    root["format"].setValue("HD_1080")
    root["first_frame"].setValue(FRAME)
    root["last_frame"].setValue(FRAME)
    root["fps"].setValue(24)
    nuke.frame(FRAME)
    nuke.Layer("P", ["P.red", "P.green", "P.blue"])

    # Trunk: the env render.
    env_fmt = place(nuke.nodes.Constant(name="EnvFormat", channels="rgba"), 0, 0)
    env_ray = place(ray_node("EnvRay", env_fmt), 0, 1)
    env_p_hit = place(env_hit(env_ray), 0, 2)
    env_p = place(shuffle("EnvToP", env_p_hit, "rgba",
                          [("rgba.red", 0, "P.red", 0), ("rgba.green", 1, "P.green", 1),
                           ("rgba.blue", 2, "P.blue", 2)], out="P", label="rgb to the P layer"), 0, 3)
    env_rgb = place(env_shade(env_p), 0, 4)

    # Clouds render, with overscan in its bbox.
    cl_fmt = place(nuke.nodes.Constant(name="CloudFormat", channels="rgba"), 2, 0)
    cl_over = nuke.nodes.Crop(name="Overscan160", label="bbox 160 px past the format", crop=False)
    cl_over["box"].setValue([-OVERSCAN, -OVERSCAN, WIDTH + OVERSCAN, HEIGHT + OVERSCAN])
    cl_over.setInput(0, cl_fmt)
    place(cl_over, 2, 1)
    cl_ray = place(ray_node("CloudRay", cl_over), 2, 2)
    cl_hit = place(cloud_hit(cl_ray), 2, 3)
    cl_z = place(shuffle("CloudToDepth", cl_hit, "rgba", [("rgba.blue", 2, "depth.Z", 0)], out="depth",
                         label="b to depth.Z (Planar Z, scene units)"), 2, 4)
    cl_cover = place(cloud_cover(cl_z), 2, 5)
    cl_holes = place(cloud_holes(cl_cover), 2, 6)
    cl_out = place(cloud_shade(cl_holes), 2, 7)
    cl_dot_merge = dot(cl_out, 2, 9)

    env_over = nuke.nodes.Merge2(name="CloudsOverEnv", operation="over", bbox="B",
                                 label="clouds in the env's picture; P stays from B")
    env_over.setInput(0, env_rgb)
    env_over.setInput(1, cl_dot_merge)
    place(env_over, 0, 9)

    # Camera, sun, atmos.
    camera = nuke.nodes.Camera3(name="ShotCamera", label="30 m up, pitched 4 deg up")
    camera["translate"].setValue([0, CAM_Y * UNIT, 0])
    camera["rotate"].setValue([PITCH, 0, 0])
    camera["focal"].setValue(FOCAL)
    camera["haperture"].setValue(HAP)
    camera["vaperture"].setValue(VAP)
    camera["far"].setValue(1000000)
    place(camera, 4, 4)

    axis = nuke.nodes.Axis3(name="Sun", label="16 deg up, 6 deg right, ahead of the camera")
    axis["translate"].setValue([s * 10000 for s in SUN])
    place(axis, 8, 4)

    hdri_fmt = nuke.nodes.Constant(name="HDRIFormat", channels="rgba")
    hdri_fmt["format"].setValue(nuke.addFormat("2048 1024 1 EzCloudShafts_demo_latlong"))
    place(hdri_fmt, 6, 0)
    v = "(y+0.5)/height"
    hdri = expression("DummyHDRI", hdri_fmt,
                      ["%s<0.5?0.15:mix(1.0,0.25,%s*2-1)" % (v, v), "%s<0.5?0.14:mix(0.8,0.42,%s*2-1)" % (v, v),
                       "%s<0.5?0.10:mix(0.6,0.85,%s*2-1)" % (v, v), None],
                      label="gradient sky lat-long")
    place(hdri, 6, 1)

    atmos = paste(ATMOS_GROUP, "Atmos")
    atmos["passes"].setValue("Depth Haze")
    atmos["output_mapping"].setValue("Lat-long")
    atmos["sun_from"].setValue("Axis")
    atmos["light_from_hdri"].setValue(False)
    atmos["scene_scale"].setValue(0.1)
    atmos["units_confirmed"].setValue(True)
    atmos["camera_height"].setValue(CAM_Y)
    atmos["haze_distance"].setValue(20)
    atmos["render_resolution"].setValue("Half")
    atmos.setInput(0, hdri)
    sun_dot = dot(axis, 8, 8)
    atmos.setInput(1, sun_dot)
    place(atmos, 6, 8)

    # The tool.
    shafts = paste(SHAFTS_GROUP, "EzCloudShafts")
    for knob, value in SETTINGS.items():
        shafts[knob].setValue(value)
    place(shafts, 0, 12)
    shafts.setInput(0, env_over)
    clouds_dot = dot(cl_dot_merge, 2, 12)
    shafts.setInput(1, clouds_dot)
    shafts.setInput(2, dot(camera, 4, 11))
    shafts.setInput(3, dot(atmos, 6, 10))
    shafts.setInput(4, dot(sun_dot, 8, 9.5))

    # What it makes.
    fan = dot(shafts, 0, 14)
    checks = []
    views = [("Shafts_RGB", "shafts", ("red", "green", "blue"), "shafts.rgb"),
             ("Shafts_Alpha", "shafts", ("alpha",) * 3, "shafts.alpha"),
             ("CloudShadow_Alpha", "cloudshadow", ("alpha",) * 3, "cloudshadow.alpha"),
             ("Gobo_Check", "cloudshadow", ("red", "green", "blue"), "Gobo Check (cloudshadow.rgb)")]
    last = fan
    for i, (name, layer, chans, label) in enumerate(views):
        d = dot(last, i + 1, 14)
        checks.append(place(to_rgb(name, d, layer, chans, label=label), i + 1, 16))
        last = d
    plate_dot = dot(clouds_dot, 2, 13)
    plate_dot2 = dot(plate_dot, 5, 13, label="clouds plate")
    plate = nuke.nodes.Crop(name="CloudsPlateFrame", label="clouds plate, cropped to the frame")
    plate["box"].setValue([0, 0, WIDTH, HEIGHT])
    plate.setInput(0, plate_dot2)
    place(plate, 5, 16)

    # Contact sheet.
    panels = [("Shafts Over Env", fan), ("shafts.rgb", checks[0]), ("shafts.alpha", checks[1]),
              ("cloudshadow.alpha", checks[2]), ("Gobo Check", checks[3]), ("Clouds plate", plate)]
    sheet_nodes = []
    labelled = []
    for i, (title, src) in enumerate(panels):
        rf = nuke.nodes.Reformat(name="Panel%d" % (i + 1), type="to box", box_width=960, box_height=540,
                                 box_fixed=True, resize="distort", black_outside=True)
        rf.setInput(0, src)
        place(rf, i, 18)
        bar = nuke.nodes.Rectangle(name="LabelBar%d" % (i + 1), color=0, opacity=0.7)
        bar["area"].setValue([0, 476, 960, 540])
        bar.setInput(0, rf)
        place(bar, i, 19)
        tx = nuke.nodes.Text2(name="Label%d" % (i + 1), message=title)
        tx["box"].setValue([24, 480, 936, 530])
        tx["yjustify"].setValue("center")
        tx["global_font_scale"].setValue(0.34)
        tx.setInput(0, bar)
        place(tx, i, 20)
        labelled.append(tx)
        sheet_nodes += [rf, bar, tx]
    sheet = nuke.nodes.ContactSheet(name="ContactSheet", width=2880, height=1080, rows=2, columns=3, gap=0,
                                    roworder="TopBottom", colorder="LeftRight", center=True)
    for i, tx in enumerate(labelled):
        sheet.setInput(i, tx)
    place(sheet, 0, 22)
    write = nuke.nodes.Write(name="WriteSheet", file_type="jpeg", channels="rgb")
    write["file"].fromUserText("[file dirname [value root.name]]/EzCloudShafts_demo_sheet.jpg")
    write["_jpeg_quality"].setValue(0.92)
    write.setInput(0, sheet)
    place(write, 0, 23)
    viewer = nuke.nodes.Viewer(name="Viewer1")
    viewer.setInput(0, shafts)
    place(viewer, -2, 14)

    # Backdrops and the note.
    backdrop([env_fmt, env_ray, env_p_hit, env_p, env_rgb], "Env render (P + rgb)", SLATE, 0)
    backdrop([cl_fmt, cl_over, cl_ray, cl_hit, cl_z, cl_cover, cl_holes, cl_out], "Clouds render (rgba + depth.Z, overscan)", SLATE, 0)
    backdrop([camera], "Shot camera", OCHRE, 0)
    backdrop([hdri_fmt, hdri, atmos], "HDRI + atmos colour", OCHRE, 0)
    backdrop([axis], "Sun", OCHRE, 0)
    backdrop([shafts], "EzCloudShafts", GREEN, 0)
    backdrop(checks + [plate], "Layer checks", RED, 0)
    backdrop(sheet_nodes, "Contact sheet", GREY, 0)

    note = nuke.nodes.StickyNote(name="ReadMe", note_font_size=16, label=readme())
    note.setXYpos(-4 * COL - 200, 0)

    check_layout()
    return shafts, write


def readme():
    return "\n".join([
        "EzCloudShafts demo: synthetic scene, no files read.",
        "",
        "Decimetres: units to metres 0.1. Camera 30 m up, pitched 4 deg up, 35 mm on 36 mm back.",
        "Sun Axis 16 deg up, 6 deg right: AHEAD of the camera and inside the frame, so the",
        "beams fan out towards the lens. Cloud sheet at 1500 m, gaps cut around the sun.",
        "",
        "EzCloudShafts:",
        "  cloud height 1500 m (Analyze measures it from depth.Z)",
        "  haze density %g /km, haze height %g km" % (SETTINGS["shaft_density"], SETTINGS["haze_height"]),
        "  steps %d, softness %g deg" % (SETTINGS["march_steps"], SETTINGS["penumbra"]),
        "  intensity %g, shafts at Same, view Shafts Over Env" % SETTINGS["shaft_intensity"],
        "",
        "What matters for beams:",
        "  1. The sun must be ahead of the camera. Behind it, beams run away from you.",
        "  2. Haze density is per km: light haze over a short view shows almost nothing.",
        "  3. The gaps must be in the clouds render near where the sun ray meets the sheet.",
        "     Check with Gobo Check and press Analyze for the gobo coverage.",
        "",
        "The env and clouds are Expression ray casts with the numbers baked in:",
        "moving ShotCamera here does not re-render them. The Sun Axis can move freely.",
    ])


def report(shafts):
    print("sun_in_use", [shafts["sun_in_use"].getValue(i) for i in range(3)])
    print("clouds bbox", shafts.input(1).bbox().x(), shafts.input(1).bbox().y(),
          shafts.input(1).bbox().w(), shafts.input(1).bbox().h())
    print("atm_found", shafts["atm_found"].value(), "axis_found", shafts["axis_found"].value())
    nuke.message = print  # Analyze reports through a dialog; print it here.
    shafts["analyze"].execute()
    print("cloud_height after analyze", shafts["cloud_height"].value())


if __name__ == "__main__":
    shafts_node, write_node = build()
    nuke.scriptSaveAs(OUT_NK, overwrite=1)
    print("saved", OUT_NK)
    if "--render" in sys.argv:
        report(shafts_node)
        shafts_node["cloud_height"].setValue(CLOUD_H)
        nuke.execute(write_node, FRAME, FRAME)
        print("rendered", write_node["file"].evaluate())
        for name in ("Shafts_RGB", "Shafts_Alpha", "CloudShadow_Alpha"):
            n = nuke.toNode(name)
            print(name, [round(n.sample("red", px, py), 4) for px, py in
                         ((960, 150), (960, 450), (600, 700), (1500, 800), (300, 950))])
