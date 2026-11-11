"""Write groups/EzCloudShafts_group.nk and gizmos/EzCloudShafts.gizmo from blink/EzCloudShafts.blink.

Plain Python, no Nuke needed:

    python3 python/build_group.py

The node is self-contained: the kernel source, the Analyze button's code and every expression
live on the node, so it needs no init.py, menu.py or Python module. The graph inside is laid
out with node_layout.py (layout_hints.py says how).

Inputs: 0 env (the environment render with a world position layer), 1 clouds (the flattened
clouds render: rgba + depth), 2 camera, 3 atmos (an EzAtmosScatter, optional: sun direction
and colour), 4 sun (an Axis, optional: overrides the sun direction), 5 sunclouds (optional: the
clouds' opacity from an orthographic camera along the sun), 6 suncam (that camera).
"""

import base64
import hashlib
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import layout_hints  # noqa: E402
import node_layout  # noqa: E402

# Shown on the node; bump it with each tagged release.
VERSION = "1.0.0"
KERNEL = "EzCloudShafts"
# Nuke's own hash of the kernel, as it saves it in KernelDescription. With a wrong one the node
# loads with no error, but every render through it is silently cancelled, so the viewer sits
# on "computing". The hash can't be worked out without Nuke, so it's pinned to the source it
# came from. After editing the kernel: load the .blink in a BlinkScript in NukeX, recompile,
# take the 5th word of its KernelDescription, and update both of these.
KERNEL_SOURCE_SHA256 = "bf934147338fcaf467521dde28d1072dabcf42a78be024b2875ca7f58d99e4a8"
KERNEL_NUKE_HASH = "73c6fc51b82e395f1a211ae8c60f3ace8e4f20478ec0258b84c0109ae9e26207"
# The soften kernel, pinned the same way.
SOFTEN_KERNEL = "EzCloudShaftsSoften"
SOFTEN_SOURCE_SHA256 = "ab1c6cd45fdaa9f53d370f2a251842258cbc01eddfe4d7c824f9181d74c11d38"
SOFTEN_NUKE_HASH = "45d6b9fcdb620d134d7c21f16e3359242015a6d6f3a519bfa44e366588cd1567"
SOFTEN_PARAMS = [("radius", "radius", "Float", 1, 4.0), ("edge", "edge", "Float", 1, 0.03),
                 ("cam_position", "camPosition", "Float", 3, (0, 0, 0))]
SOFTEN_IMAGES = [("src", "Read", "Random"), ("pos", "Read", "Random"), ("dst", "Write", "Point")]
GROUP_PATH = os.path.join(ROOT, "groups", "EzCloudShafts_group.nk")
GIZMO_PATH = os.path.join(ROOT, "gizmos", "EzCloudShafts.gizmo")

LAYERS = {"P": ["red", "green", "blue"],
          "shafts": ["red", "green", "blue", "alpha"],
          "cloudshadow": ["red", "green", "blue", "alpha"],
          "shafts_lit": ["red", "green", "blue", "alpha"],
          "atmos_haze_sun": ["red", "green", "blue"],
          "atmos_haze_sky": ["red", "green", "blue"],
          "shafts_haze": ["red", "green", "blue"]}

# Kernel parameters, in the kernel's order: (name, variable, type, count, default).
PARAMS = [
    ("output", "output", "Int", 1, 0),
    ("cam_row0", "camRow0", "Float", 3, (1, 0, 0)),
    ("cam_row1", "camRow1", "Float", 3, (0, 1, 0)),
    ("cam_row2", "camRow2", "Float", 3, (0, 0, 1)),
    ("cam_position", "camPosition", "Float", 3, (0, 0, 0)),
    ("focal", "focal", "Float", 1, 35.0),
    ("haperture", "haperture", "Float", 1, 36.0),
    ("vaperture", "vaperture", "Float", 1, 20.25),
    ("frame_size", "frameSize", "Float", 2, (1920, 1080)),
    ("scene_scale", "sceneScale", "Float", 1, 0.1),
    ("clouds_size", "cloudsSize", "Float", 2, (1920, 1080)),
    ("clouds_overscan", "cloudsOverscan", "Float", 2, (0, 0)),
    ("sun_direction", "sunDirection", "Float", 3, (0, 0.5, -1)),
    ("sun_rotation", "sunRotation", "Float", 1, 0.0),
    ("cloud_height", "cloudHeight", "Float", 1, 2000.0),
    ("cloud_density", "cloudDensity", "Float", 1, 1.0),
    ("shadow_strength", "shadowStrength", "Float", 1, 1.0),
    ("outside_lit", "outsideLit", "Int", 1, 1),
    ("drift", "drift", "Float", 2, (0, 0)),
    ("penumbra", "penumbra", "Float", 1, 0.5),
    ("samples", "samples", "Int", 1, 8),
    ("shaft_density", "shaftDensity", "Float", 1, 0.0001),
    ("haze_height", "hazeHeight", "Float", 1, 1200.0),
    ("shaft_start", "shaftStart", "Float", 1, 0.0),
    ("max_distance", "maxDistance", "Float", 1, 0.0),
    ("sky_distance", "skyDistance", "Float", 1, 20000.0),
    ("march_steps", "marchSteps", "Int", 1, 48),
    ("use_env", "useEnv", "Int", 1, 0),
    ("env_screen", "envScreen", "Int", 1, 0),
    ("env_rotation", "envRotation", "Float", 1, 0.0),
    ("shaft_color", "shaftColor", "Float", 3, (1, 0.9, 0.75)),
    ("shaft_intensity", "shaftIntensity", "Float", 1, 1.0),
    ("seed", "seed", "Float", 1, 1.0),
    ("use_depth", "useDepth", "Int", 1, 0),
    ("use_sun_view", "useSunView", "Int", 1, 0),
    ("sun_row0", "sunRow0", "Float", 3, (1, 0, 0)),
    ("sun_row1", "sunRow1", "Float", 3, (0, 1, 0)),
    ("sun_row2", "sunRow2", "Float", 3, (0, 0, 1)),
    ("sun_position", "sunPosition", "Float", 3, (0, 0, 0)),
    ("sun_width", "sunWidth", "Float", 1, 100000.0),
]
LOCALS = [("pi", 1), ("sunWorld", 3), ("sunX", 3), ("sunY", 3)]
IMAGES = [("pos", "Read", "Point"), ("clouds", "Read", "Random"), ("envSun", "Read", "Random"),
          ("sunClouds", "Read", "Random"), ("dst", "Write", "Point")]


def q(text):
    """A string quoted for a .nk file (TCL): brackets and braces escaped so nothing runs."""
    out = text.replace("\\", "\\\\").replace('"', '\\"').replace("[", "\\[")
    out = out.replace("{", "\\{").replace("}", "\\}").replace("\n", "\\n")
    return '"%s"' % out


def _b64(kind, count, value):
    values = list(value) if isinstance(value, (tuple, list)) else [value]
    if kind == "Int":
        raw = struct.pack("<%di" % len(values), *values)
    else:
        if count == 3:
            values = values + [0.0]     # float3 is stored padded to four floats
        raw = struct.pack("<%df" % len(values), *values)
    return base64.b64encode(raw).decode()


def describe(name, nuke_hash, images, params, local_vars):
    """What a saved BlinkScript node carries about its compiled kernel, so Nuke can make the
    parameter knobs before it compiles the source again."""
    parts = ["3", '"%s"' % name, "iterate", "pixelWise", nuke_hash, str(len(images))]
    for image, mode, access in images:
        parts += ['"%s"' % image, mode, access]
    parts.append(str(len(params)))
    for pname, _, kind, count, default in params:
        parts += ['"%s"' % pname, kind, str(count), _b64(kind, count, default)]
    parts.append(str(len(params)))
    for _, var, _, count, _ in params:
        parts += ['"%s"' % var, str(count), "1", "Default"]
    parts.append(str(len(local_vars)))
    for var, count in local_vars:
        parts += ['"%s"' % var, "Float", str(count), "1", _b64("Float", count, [0.0] * count)]
    return q(" ".join(parts))


def kernel_description(source):
    if hashlib.sha256(source.encode()).hexdigest() != KERNEL_SOURCE_SHA256 or KERNEL_NUKE_HASH == "PENDING":
        sys.exit("The kernel changed: update KERNEL_NUKE_HASH and KERNEL_SOURCE_SHA256 (see their comment).")
    return describe(KERNEL, KERNEL_NUKE_HASH, IMAGES, PARAMS, LOCALS)


def soften_node():
    """The edge-aware soften's BlinkScript body."""
    with open(os.path.join(ROOT, "blink", SOFTEN_KERNEL + ".blink")) as f:
        source = f.read()
    if hashlib.sha256(source.encode()).hexdigest() != SOFTEN_SOURCE_SHA256:
        sys.exit("The soften kernel changed: update SOFTEN_NUKE_HASH and SOFTEN_SOURCE_SHA256.")
    return ["inputs 2", "recompileCount 1",
            "KernelDescription " + describe(SOFTEN_KERNEL, SOFTEN_NUKE_HASH, SOFTEN_IMAGES, SOFTEN_PARAMS, []),
            "kernelSource " + q(source), 'rebuild ""',
            "%s_radius {{parent.soften}}" % SOFTEN_KERNEL,
            "%s_edge 0.03" % SOFTEN_KERNEL,
            "%s_cam_position {{parent.cam_world_matrix.3} {parent.cam_world_matrix.7} {parent.cam_world_matrix.11}}"
            % SOFTEN_KERNEL,
            'rebuild_finalise ""']

# ---- Python run from expressions on the group's hidden knobs ------------------------------
# Each finds its node through any Dots or NoOps in the input.

def _find(var, index, knob):
    return ("%s = nuke.thisNode().input(%d)\n"
            "while %s is not None and not %s.knob('%s'):\n"
            "    %s = %s.input(0) if %s.inputs() else None\n"
            % (var, index, var, var, knob, var, var, var))


FIND_CAMERA = _find("c", 2, "focal")
FIND_ATMOS = _find("a", 3, "haze_density")
FIND_AXIS = _find("x", 4, "world_matrix")
FIND_SUNCAM = _find("c", 6, "world_matrix")


def py_expr(code):
    return "[python -execlocal {%s}]" % code


# ---- The Analyze button -------------------------------------------------------------------
ANALYZE = r'''
import math
n = nuke.thisNode()
frame = nuke.frame()
notes = []


def up(i, knob):
    node = n.input(i)
    while node is not None and not node.knob(knob):
        node = node.input(0) if node.inputs() else None
    return node


atmos = up(3, 'haze_density')
cam = up(2, 'focal')
clouds = n.input(1)
env = n.input(0)
if atmos is not None and atmos.knob('scene_scale'):
    n['scene_scale'].setValue(atmos['scene_scale'].value())
    notes.append('Units to metres %g, from %s.' % (atmos['scene_scale'].value(), atmos.name()))
scale = n['scene_scale'].value()
if cam is None:
    notes.append('No camera in the camera input: connect the shot camera.')
if env is None:
    notes.append('Nothing in the env input.')
if clouds is None:
    notes.append('Nothing in the clouds input.')

# warns: (rank, text), the most important first; the top one becomes the status line.
warns = []
if cam is None or env is None or clouds is None:
    warns.append((0, 'An input is missing: connect env, clouds and camera.'))

# Find the world position and sun light layers by their usual names.
if env is not None:
    layers = set()
    for c in env.channels():
        layers.add(c.split('.')[0])
    if n['position_layer'].value() not in layers or n['position_layer'].value() == 'rgba':
        found = None
        for want in ('p', 'pworld', 'p_world', 'pw', 'p_w', 'worldp', 'position', 'world_position', 'worldposition',
                     'position_world', 'pos', 'wp'):
            for have in sorted(layers):
                if found is None and have.lower() == want:
                    found = have
        if found is not None:
            n['position_layer'].setValue(found)
            notes.append('Position layer: found "%s".' % found)
    if not n['use_sun_layer'].value():
        found = None
        for want in ('light_sun', 'sun', 'sunlight', 'sun_light', 'rgba_sun', 'c_sun', 'lgt_sun', 'lg_sun', 'key',
                     'key_light', 'light_key', 'rgba_key', 'lgt_key'):
            for have in sorted(layers):
                if found is None and have.lower() == want:
                    found = have
        if found is not None:
            n['sun_layer'].setValue(found)
            n['use_sun_layer'].setValue(True)
            n['comp_shadow'].setValue(1)
            notes.append('Sun light layer: found "%s", cloud shadow set to 1.' % found)

if cam is not None and clouds is not None:
    m = [cam['world_matrix'].getValueAt(frame, i) for i in range(16)]
    focal = cam['focal'].getValueAt(frame)
    hap = cam['haperture'].getValueAt(frame)
    vap = cam['vaperture'].getValueAt(frame)
    fmt = clouds.format()
    efmt = env.format() if env is not None else fmt
    ox = max(0.0, (fmt.width() - efmt.width()) / 2.0)
    oy = max(0.0, (fmt.height() - efmt.height()) / 2.0)
    depth = n['clouds_depth'].value()
    if depth not in clouds.channels():
        notes.append('The clouds input has no %s channel: set "clouds depth".' % depth)
    else:
        heights = []
        nx, ny = 64, 36
        for j in range(ny):
            for i in range(nx):
                px = (i + 0.5) * fmt.width() / nx
                py = (j + 0.5) * fmt.height() / ny
                a = clouds.sample('rgba.alpha', px, py)
                if a < 0.5:
                    continue
                z = clouds.sample(depth, px, py)
                if z <= 0:
                    continue
                u = (px - ox) / (fmt.width() - 2 * ox)
                v = (py - oy) / (fmt.height() - 2 * oy)
                cx = (u - 0.5) * hap / focal * z
                cy = (v - 0.5) * vap / focal * z
                cz = -z
                heights.append((m[4] * cx + m[5] * cy + m[6] * cz + m[7]) * scale)
        if len(heights) < 10:
            notes.append('Too little cloud in the clouds alpha (%d of %d samples) to measure its height.'
                         % (len(heights), nx * ny))
        else:
            heights.sort()
            pick = lambda f: heights[min(len(heights) - 1, int(f * len(heights)))]
            if pick(0.5) <= 0:
                notes.append('The cloud measured below the ground (%.0f m): is the depth Planar Z, in scene '
                             'units?' % pick(0.5))
            else:
                n['cloud_height'].setValue(round(pick(0.5), 1))
                notes.append('Cloud height %.0f m (base %.0f m, top %.0f m, from %d samples).'
                             % (pick(0.5), pick(0.1), pick(0.9), len(heights)))

        # How much of the ground the gobo reaches, from a grid of the env's world positions.
        layer = n['position_layer'].value()
        if env is not None and layer + '.red' in env.channels():
            sun = [n['sun_in_use'].getValueAt(frame, i) for i in range(3)]
            rot = math.radians(-n['sun_rotation_in_use'].getValueAt(frame))
            sun = [sun[0] * math.cos(rot) + sun[2] * math.sin(rot), sun[1],
                   -sun[0] * math.sin(rot) + sun[2] * math.cos(rot)]
            norm = math.sqrt(sum(s * s for s in sun)) or 1.0
            sun = [s / norm for s in sun]
            h = n['cloud_height'].value()
            cam_pos = [m[3] * scale, m[7] * scale, m[11] * scale]
            cz_ok = True
            ground = covered = 0
            bounds = clouds.bbox()
            short = {'left': 0.0, 'right': 0.0, 'top': 0.0, 'bottom': 0.0}
            dists = []
            for j in range(36):
                for i in range(64):
                    px = (i + 0.5) * efmt.width() / 64
                    py = (j + 0.5) * efmt.height() / 36
                    p = [env.sample(layer + '.' + c, px, py) * scale
                         for c in ('red', 'green', 'blue')]
                    if p == [0.0, 0.0, 0.0]:
                        continue
                    dists.append(math.sqrt((p[0] - cam_pos[0]) ** 2 + (p[1] - cam_pos[1]) ** 2 +
                                           (p[2] - cam_pos[2]) ** 2))
                    if p[1] >= h:
                        continue
                    ground += 1
                    if sun[1] <= 0.01:
                        continue
                    t = (h - p[1]) / sun[1]
                    d = [p[k] + sun[k] * t - cam_pos[k] for k in range(3)]
                    cx = m[0] * d[0] + m[4] * d[1] + m[8] * d[2]
                    cy = m[1] * d[0] + m[5] * d[1] + m[9] * d[2]
                    cz = m[2] * d[0] + m[6] * d[1] + m[10] * d[2]
                    if cz > -1e-3:
                        cz_ok = False
                        continue
                    x = ox + (0.5 + cx / -cz * focal / hap) * (fmt.width() - 2 * ox)
                    y = oy + (0.5 + cy / -cz * focal / vap) * (fmt.height() - 2 * oy)
                    if bounds.x() <= x < bounds.x() + bounds.w() and bounds.y() <= y < bounds.y() + bounds.h():
                        covered += 1
                    else:
                        short['left'] = max(short['left'], bounds.x() - x)
                        short['right'] = max(short['right'], x - bounds.x() - bounds.w())
                        short['bottom'] = max(short['bottom'], bounds.y() - y)
                        short['top'] = max(short['top'], y - bounds.y() - bounds.h())
            if ground:
                share = 100.0 * covered / ground
                notes.append('The gobo reaches %.0f%% of the ground; the rest uses "outside frame" (%s).'
                             % (share, n['outside_frame'].value()))
                if share < 90:
                    need = []
                    for side in ('top', 'left', 'right', 'bottom'):
                        if short[side] > 0:
                            need.append('%s %d px' % (side, short[side]))
                    text = 'Gobo reaches only %.0f%% of the ground.' % share
                    if need and cz_ok:
                        text += ' Ask CG for more overscan: ' + ', '.join(need) + '.'
                    else:
                        text += ' The sun rays land behind the camera, so overscan will not help.'
                    warns.append((3, text))

            # A first result that shows: haze from how far the scene reaches.
            if dists:
                dists.sort()
                near_km = dists[len(dists) // 2] / 1000.0
                far_km = dists[min(len(dists) - 1, int(len(dists) * 0.99))] / 1000.0
                n['scene_depth'].setValue(round(near_km, 3))
                density = min(2.0, max(0.005, 0.6 / max(near_km, 0.05)))
                reach = round(max(far_km * 1.2, 1.0), 1)
                if abs(n['shaft_density'].value() - 0.1) < 1e-6 and n['max_distance'].value() == 0:
                    n['shaft_density'].setValue(round(density, 3))
                    n['max_distance'].setValue(reach)
                    n['sky_distance'].setValue(reach)
                    notes.append('Scene reaches %.1f km (median %.1f km): haze density %.3f /km, max and sky distance '
                                 '%.1f km.' % (far_km, near_km, density, reach))
                else:
                    notes.append('Scene reaches %.1f km (median %.1f km). Haze density around %.3f /km would suit it '
                                 '(left as it is, since you have set it).' % (far_km, near_km, density))
                if near_km > 500 or far_km < 0.002:
                    warns.append((1, 'Units look wrong: the scene is %.3g km deep. Check "units to metres".' % near_km))
        else:
            notes.append('The env input has no "%s" layer: set "position layer" to its world position.' % layer)

if cam is not None:
    m = [cam['world_matrix'].getValueAt(frame, i) for i in range(16)]
    sun = [n['sun_in_use'].getValueAt(frame, i) for i in range(3)]
    rot = math.radians(-n['sun_rotation_in_use'].getValueAt(frame))
    sun = [sun[0] * math.cos(rot) + sun[2] * math.sin(rot), sun[1],
           -sun[0] * math.sin(rot) + sun[2] * math.cos(rot)]
    norm = math.sqrt(sun[0] ** 2 + sun[1] ** 2 + sun[2] ** 2) or 1.0
    sun = [v / norm for v in sun]
    elev = math.degrees(math.asin(max(-1.0, min(1.0, sun[1]))))
    fwd = [-m[2], -m[6], -m[10]]
    az = (math.degrees(math.atan2(sun[0], -sun[2]) - math.atan2(fwd[0], -fwd[2])) + 180.0) % 360.0 - 180.0
    notes.append('Sun %.0f deg up, %.0f deg %s of where the camera looks.' % (elev, abs(az), 'right' if az > 0 else 'left'))
    if elev <= 0:
        warns.append((1, 'The sun is below the horizon (%.0f deg): no beams can form.' % elev))
    elif abs(az) > 120:
        warns.append((2, 'The sun is behind the camera (%.0f deg off): beams run away from the lens and the gobo '
                         'cannot reach. A sun-view clouds render would fix it.' % abs(az)))
    elif abs(az) > 60:
        warns.append((2, 'The sun is to the side (%.0f deg off): beams will be faint and the gobo only covers '
                         'part of the frame.' % abs(az)))
    elif elev > 55:
        warns.append((2, 'The sun is high (%.0f deg): beams fall almost straight down and will not fan out.' % elev))
    height = n['cloud_height'].value()
    cam_m = m[7] * n['scene_scale'].value()
    if abs(cam_m) > 20000:
        warns.append((1, 'Units look wrong: the camera is %.0f km up. Check "units to metres".' % (cam_m / 1000.0)))
    if height <= cam_m:
        warns.append((1, 'Cloud height (%.0f m) is at or below the camera (%.0f m): nothing can cast from there.'
                         % (height, cam_m)))
    elif height > 15000:
        warns.append((1, 'Cloud height %.0f m is implausibly high. It is in metres whatever the scene units are.' % height))

if n['sun_view_on'].value():
    kept = []
    for w in warns:
        if 'gobo' not in w[1].lower():
            kept.append(w)
    warns = kept
    notes.append('Sun-view clouds in use: the gobo is not limited to the frame.')
warns.sort()
status = warns[0][1] if warns else 'OK: the sun, units and gobo all look right.'
n['status'].setValue(status)
if warns:
    notes.append('')
    for rank, text in warns:
        notes.append('Warning: ' + text)
nuke.message('EzCloudShafts analyze\n\n' + '\n'.join(notes))
'''


# ---- The breakout button -----------------------------------------------------------------
# Rebuilds the node's Comp view from its layers, next to it, as plain nodes whose values
# follow the node's Comp knobs by expression.
BREAKOUT = r'''
n = nuke.thisNode()
env = n.input(0)
if env is None:
    nuke.message('EzCloudShafts: connect the env input first.')
else:
    N = n.name()
    col, row = 180, 60
    x0, y0 = n.xpos() + 300, n.ypos() + 60
    with (n.parent() or nuke.root()):
        for other in nuke.allNodes():
            other.setSelected(False)
        made = []

        def place(node, cx, cy, src=None, src2=None):
            node.setXYpos(int(x0 + cx * col), int(y0 + cy * row))
            if src is not None:
                node.setInput(0, src)
            if src2 is not None:
                node.setInput(1, src2)
            made.append(node)
            return node

        def dot(cx, cy, src):
            d = nuke.nodes.Dot()
            d.setXYpos(int(x0 + cx * col + 34), int(y0 + cy * row + 4))
            d.setInput(0, src)
            made.append(d)
            return d

        def pick(layer, cx, src):
            sh = nuke.nodes.Shuffle2(name='%s_%s' % (n.name(), layer), label='%s to rgba' % layer)
            sh['in1'].setValue(layer)
            return place(sh, cx, 1, src)

        def expr(name, label, exprs, cx, cy, src):
            e = nuke.nodes.Expression(name='%s_%s' % (n.name(), name), label=label)
            for i, text in enumerate(exprs):
                e['expr%d' % i].setValue(text.replace('N.', N + '.'))
            return place(e, cx, cy, src)

        # Row 0: the env trunk on the left, then a row of Dots from the node, one per layer.
        trunk = dot(0, 0, env)
        heads = [dot(2, 0, n)]
        for cx in (3, 4, 5):
            heads.append(dot(cx, 0, heads[-1]))
        shadow = pick('cloudshadow', 2, heads[0])
        lit = pick('shafts_lit', 3, heads[1])
        shafts = pick('shafts', 4, heads[2])
        haze_col = pick('shafts_haze', 5, heads[3])

        # Cloud shadow: take the shadowed share of the sun light away from the env.
        if n['use_sun_layer'].value():
            sun_dot = dot(1, 0, trunk)
            sun = nuke.nodes.Shuffle2(name='%s_sunlight' % n.name(), label='sun light to rgba')
            sun['in1'].setValue(n['sun_layer'].value())
            sun = place(sun, 1, 1, sun_dot)
        else:
            sun = dot(1, 0, trunk)
        amount = expr('shadow_amount', 'sun lost under cloud',
                      ['(1-a)*N.comp_shadow'] * 3 + ['a'], 2, 3, shadow)
        lost = place(nuke.nodes.Merge2(operation='multiply', output='rgb', label='sun light x lost'),
                     1, 3, amount, sun)
        land = place(nuke.nodes.Merge2(operation='from', output='rgb', label='cloud shadow'), 0, 4, trunk, lost)

        # Haze: transmittance from shafts_lit.a, haze light graded by the lit share.
        trans = expr('haze_transmittance', 'T = (1 - haze) ^ amount',
                     ['pow(clamp(1-a,0,1), N.comp_haze*N.comp_haze_falloff.%s)' % c for c in 'rgb'] + ['r'],
                     3, 5, lit)
        hazed = place(nuke.nodes.Merge2(operation='multiply', output='rgb', label='land x T'), 0, 6, land,
                      dot(3, 6, trans))
        light = expr('haze_light', '(1 - T) x lit grade',
                     ['(1-%s)*(N.comp_haze_shadow+(N.comp_haze_lit-N.comp_haze_shadow)*a)'
                      % c for c in 'rgb'] + ['a'], 3, 7, trans)
        tinted = place(nuke.nodes.Merge2(operation='multiply', output='rgb', label='x haze colour'), 3, 8, light,
                       dot(5, 8, haze_col))
        with_haze = place(nuke.nodes.Merge2(operation='plus', output='rgb', label='+ haze'), 0, 9, hazed,
                          dot(3, 9, tinted))
        beams = place(nuke.nodes.Merge2(operation='plus', output='rgb', label='+ shafts'), 0, 10, with_haze,
                      dot(4, 10, shafts))
        beams['mix'].setExpression(N + '.comp_shafts')

        # Check against the node's own Comp view: black when 'view' is Comp.
        check_dot = dot(6, 11, dot(6, 0, heads[-1]))
        check = place(nuke.nodes.Merge2(name='%s_breakout_check' % n.name(), operation='difference', output='rgb',
                                        label='black when view is Comp'), 0, 11, beams, check_dot)
        made.append(nuke.nodes.BackdropNode(label='%s breakout' % n.name(), note_font_size=24,
                                            xpos=int(x0 - 60), ypos=int(y0 - 80),
                                            bdwidth=col * 7 + 60, bdheight=row * 12 + 100))
        for node in made:
            node.setSelected(True)
'''


# ---- The looks -----------------------------------------------------------------------------
# Haze is set from the depth Analyze measured, so a look means the same on any scene; intensity
# from how bright the atmos's sun colour is. Kept to top-level code: Nuke runs button scripts
# with separate locals.
APPLY_LOOK = r"""
import math
n = nuke.thisNode()
look = n['look'].value()
# tau: optical depth at the scene's median distance. height: haze height as a share of it.
# beam: target brightness of the beams.
looks = {
    'Soft Morning': dict(tau=0.5, height=0.7, beam=2.8, penumbra=0.8, steps=96, soften=6, gap=1.0,
                         tint=[1.0, 0.96, 0.9], haze=[0.13, 0.17, 0.26], falloff=[0.85, 1.0, 1.2],
                         shadow=0.65, lit=1.2),
    'God Rays': dict(tau=0.35, height=0.45, beam=4.0, penumbra=0.4, steps=128, soften=5, gap=1.0,
                     tint=[0.9, 0.95, 1.1], haze=[0.06, 0.13, 0.33], falloff=[0.75, 1.0, 1.4],
                     shadow=0.35, lit=1.5),
    'Storm Break': dict(tau=0.55, height=0.4, beam=4.0, penumbra=0.3, steps=128, soften=4, gap=2.5,
                        tint=[0.85, 0.93, 1.15], haze=[0.03, 0.05, 0.11], falloff=[0.9, 1.0, 1.15],
                        shadow=0.2, lit=1.8),
    'Golden Hour': dict(tau=0.4, height=0.5, beam=3.4, penumbra=0.5, steps=128, soften=5, gap=1.2,
                        tint=[1.25, 0.88, 0.55], haze=[0.2, 0.12, 0.09], falloff=[0.6, 1.0, 1.6],
                        shadow=0.45, lit=1.6),
}
if look == 'Reset':
    for knob, value in (('shaft_density', 0.1), ('haze_height', 1.2), ('penumbra', 0.5), ('march_steps', 32),
                        ('soften', 4), ('gap_contrast', 1), ('gap_threshold', 0.5), ('shaft_intensity', 1),
                        ('comp_haze', 1), ('comp_haze_shadow', 0.35), ('comp_haze_lit', 1.5), ('comp_shafts', 1)):
        n[knob].setValue(value)
    n['shaft_color'].setValue(1)
    n['comp_haze_color'].setValue([0.06, 0.13, 0.33])
    n['comp_haze_falloff'].setValue([0.75, 1.0, 1.4])
else:
    p = looks[look]
    depth = n['scene_depth'].value()
    if depth <= 0:
        depth = 3.0
        nuke.message('This look used a guessed scene depth of 3 km. Press Analyze, then apply it again.')
    # How bright the beams' colour is along the sun, so the look doesn't depend on the atmos's level.
    level = 1.0
    if int(n['color_from'].getValue()) == 0 and n['atm_found'].value():
        sun = [n['sun_in_use'].value(i) for i in range(3)]
        norm = math.sqrt(sun[0] ** 2 + sun[1] ** 2 + sun[2] ** 2) or 1.0
        with n:
            src = nuke.toNode('AtmosOrNone')
            if n['atm_screen'].value():
                u, v = 0.5, 0.9
            else:
                lon = math.atan2(sun[0], -sun[2]) - math.radians(n['atm_rotation'].value())
                u = (lon / (2 * math.pi) + 0.5) % 1.0
                v = math.asin(max(-1.0, min(1.0, sun[1] / norm))) / math.pi + 0.5
            level = max(src.sample('green', u * src.width(), v * src.height()), 1e-3)
    n['shaft_density'].setValue(round(p['tau'] / depth, 4))
    n['haze_height'].setValue(round(min(5.0, max(0.2, p['height'] * depth)), 2))
    n['penumbra'].setValue(p['penumbra'])
    n['march_steps'].setValue(p['steps'])
    n['soften'].setValue(p['soften'])
    n['gap_contrast'].setValue(p['gap'])
    n['gap_threshold'].setValue(0.5)
    n['shaft_color'].setValue(p['tint'])
    n['shaft_intensity'].setValue(round(p['beam'] / level, 4))
    n['comp_haze'].setValue(1)
    n['comp_haze_color'].setValue(p['haze'])
    n['comp_haze_falloff'].setValue(p['falloff'])
    n['comp_haze_shadow'].setValue(p['shadow'])
    n['comp_haze_lit'].setValue(p['lit'])
    n['comp_shafts'].setValue(1)
"""


# ---- Bake ----------------------------------------------------------------------------------
# The bake path: 'bake file' when set, else <folder>/<script>/<node>/<script>_<node>.####.exr.
# Both knobs may use $VAR or Tcl such as [getenv JOB]; a variable that isn't set empties the
# path, so nothing lands in a wrong place. Python inside Tcl braces: no braces, double quotes
# or backslashes in it.
BAKE_PATH = ("[python -execlocal {import os\n"
             "g = nuke.thisGroup()\n"
             "ready = g.knob('bake_file') is not None and g.knob('bake_folder') is not None\n"
             "s = nuke.root().name()\n"
             "base = os.path.splitext(os.path.basename(s))[0]\n"
             "p = g['bake_file'].value().strip() if ready else ''\n"
             "if not p:\n"
             "    d = g['bake_folder'].value().strip() if ready else ''\n"
             "    d = d or os.path.join(os.path.dirname(s), 'ezcloudshafts_cache')\n"
             "    p = d.rstrip('/') + '/' + base + '/' + g.name() + '/' + base + '_' + g.name() + '.####.exr'\n"
             "p = os.path.expandvars(p)\n"
             "if '[' in p:\n"
             "    try:\n"
             "        p = nuke.tcl('subst', p)\n"
             "    except RuntimeError:\n"
             "        p = ''\n"
             "ret = '' if '$' in p or not ready else p.replace(chr(92), '/')}]")

# The settings that shape the baked layers.
BAKE_WATCH = ["position_layer", "scene_scale", "sun_from", "sun_direction", "cloud_height", "cloud_density",
              "shadow_strength", "gap_contrast", "gap_threshold", "outside_frame", "penumbra", "samples", "drift_x",
              "drift_z", "drift_frame", "shaft_density", "haze_height", "shaft_start", "max_distance", "sky_distance",
              "march_steps", "color_from", "shaft_color", "shaft_intensity", "soften", "edge_aware",
              "use_cloud_depth", "sun_view_width",
              "render_resolution", "shafts_resolution"]

BAKE_HASH = ("import hashlib\n"
             "s = []\n"
             "for k in %r:\n"
             "    if g.knob(k):\n"
             "        s.append((k, g[k].toScript()))\n"
             "# Where the camera and sun are now, read as values since those knobs are expressions.\n"
             "s.append(repr(g['sun_in_use'].value()))\n"
             "s.append(repr(g['cam_world_matrix'].value()))\n"
             "h = hashlib.md5(repr(s).encode()).hexdigest()\n" % (BAKE_WATCH,))

# Whether the bake can be used: it exists and the settings still match. Sets the hidden
# bake_valid knob the Use_* Switches read, and a label. Run from knobChanged and onCreate.
# In its own function: a knob change inside a button's script runs this in the same Python
# namespace, and its names must not overwrite that script's variables.
BAKE_CHECK = ("def _ezcs_check(g):\n"
              "    if g.knob('bake_valid') is None:\n"
              "        return\n" + "".join("    " + line + "\n" for line in (
                  BAKE_HASH +
                  "import os, re\n"
                  "r = g.node('BakeRead')\n"
                  "p = (nuke.filename(r) or '') if r is not None else ''\n"
                  "fr = int(g['baked_first'].value())\n"
                  "m = re.search('(#+)|%(0?[0-9]*)d', p)\n"
                  "if m is not None:\n"
                  "    width = len(m.group(1)) if m.group(1) else int(m.group(2) or 1)\n"
                  "    p = p[:m.start()] + str(fr).zfill(width) + p[m.end():]\n"
                  "ok = bool(g['baked_hash'].value()) and g['baked_hash'].value() == h and os.path.exists(p)\n"
                  "if bool(g['bake_valid'].value()) != ok:\n"
                  "    g['bake_valid'].setValue(ok)\n"
                  "text = ('baked' if ok else 'bake out of date: live') if g['use_baked'].value() and g['baked_hash'].value() else ''\n"
                  "if g['label'].value() in ('', 'baked', 'bake out of date: live') and g['label'].value() != text:\n"
                  "    g['label'].setValue(text)\n").splitlines()) +
              "_ezcs_check(nuke.thisNode())\n")

KNOB_CHANGED = ("if nuke.thisKnob().name() in %r:\n" % (BAKE_WATCH + ["use_baked", "bake_file", "bake_folder", "baked_hash",
                                                                       "baked_first", "inputChange"]) +
                "".join("    " + line + "\n" for line in BAKE_CHECK.splitlines()))

ON_CREATE = ("g = nuke.thisNode()\n"
             "if g['bake_first'].value() == 0 and g['bake_last'].value() == 0:\n"
             "    g['bake_first'].setValue(int(nuke.root()['first_frame'].value()))\n"
             "    g['bake_last'].setValue(int(nuke.root()['last_frame'].value()))\n" + BAKE_CHECK)

# Stops a bake whose path didn't resolve, and makes its folders.
BAKE_PATH_CHECK = ("import os\n"
                   "path = nuke.filename(g.node('BakeRead')) or ''\n"
                   "bad = '' if path and os.path.isabs(path) else ('the bake folder uses an environment variable that '\n"
                   "    'is not set in Nuke' if path == '' else 'the bake path is not a full path: ' + path)\n"
                   "if not bad and not path.lower().endswith('.exr'):\n"
                   "    bad = 'bake file is a folder, not a file name like name.####.exr'\n"
                   "if not bad and not os.path.isdir(os.path.dirname(path)):\n"
                   "    try:\n"
                   "        os.makedirs(os.path.dirname(path))\n"
                   "    except OSError as e:\n"
                   "        bad = 'cannot create ' + os.path.dirname(path) + ' (' + str(e.strerror or e) + ')'\n"
                   "if bad:\n"
                   "    nuke.message('Not baked: ' + bad + '.')\n")

BAKE_RANGE = ("first, last = int(g['bake_first'].value()), int(g['bake_last'].value())\n"
              "if last < first:\n"
              "    first, last = last, first\n")

BAKE_NOW = ("g = nuke.thisNode()\n" + BAKE_PATH_CHECK +
            "if not bad:\n" + "".join("    " + line + "\n" for line in (
                BAKE_HASH + BAKE_RANGE +
                "use = g['use_baked'].value()\n"
                "g['use_baked'].setValue(False)\n"
                "try:\n"
                "    with g:\n"
                "        nuke.execute(nuke.toNode('BakeWrite'), first, last)\n"
                "    g['baked_hash'].setValue(h)\n"
                "    g['baked_first'].setValue(first)\n"
                "    g['baked_last'].setValue(last)\n"
                "finally:\n"
                "    g['use_baked'].setValue(use)\n" + BAKE_CHECK).splitlines()))

BAKE_FARM = ("g = nuke.thisNode()\n" + BAKE_PATH_CHECK +
             "if not bad:\n" + "".join("    " + line + "\n" for line in (
                 BAKE_HASH + BAKE_RANGE +
                 "with (g.parent() or nuke.root()):\n"
                 "    w = nuke.nodes.Write(name=g.name() + '_BakeWrite', file=path, file_type='exr', channels='all')\n"
                 "    w['create_directories'].setValue(True)\n"
                 "    w['use_limit'].setValue(True)\n"
                 "    w['first'].setValue(first)\n"
                 "    w['last'].setValue(last)\n"
                 "    w.setInput(0, g)\n"
                 "    w.setXYpos(g.xpos(), g.ypos() + 80)\n"
                 "g['baked_hash'].setValue(h)\n"
                 "g['baked_first'].setValue(first)\n"
                 "g['baked_last'].setValue(last)\n"
                 "g['bake_valid'].setValue(True)\n"
                 "if nuke.GUI:\n"
                 "    nuke.message('Render %s on the farm before the comp. It writes ' % w.name() + path)\n").splitlines()))


# ---- The group's knobs -------------------------------------------------------------------

def knob_lines():
    k = []
    add = k.append
    add('addUserKnob {20 ezcloudshafts l EzCloudShafts}')
    add('addUserKnob {22 analyze t %s T %s +STARTLINE}'
        % (q("Reads the cloud height from the clouds' depth (the median of the cloudy pixels), takes the "
             "units from the EzAtmosScatter in 'atmos', and reports how much of the ground the gobo reaches. "
             "Run it at a frame where the clouds are in view."), q(ANALYZE)))
    add('addUserKnob {4 view t %s -STARTLINE M {Passthrough "Shafts Over Env" "Shadow Matte" "Gobo Check" '
        '"Shafts Matte" "Lit Share" Comp}}'
        % q("What the main rgb shows. The passes are always written to the shafts and cloudshadow layers; "
            "Comp is the finished look (see the Comp knobs). Passthrough leaves rgba as the env render. Lit Share shows shafts_lit: 1 where the haze is sunlit, 0 under cloud."))
    add('view Comp')
    add('addUserKnob {22 layer_breakout l "layer breakout" t %s T %s -STARTLINE}'
        % (q("Builds the Comp view from this node's layers next to it, as plain nodes: cloud shadow on the sun "
             "light, haze from shafts_lit, then the shafts. Their values follow the Comp knobs, and a Difference "
             "at the bottom is black while 'view' is Comp."), q(BREAKOUT)))
    add('addUserKnob {4 look t %s M {"Soft Morning" "God Rays" "Storm Break" "Golden Hour" Reset}}'
        % q("A starting point for the haze, beams and Comp knobs. Press Analyze first, so the haze suits the "
            "scene's size, then 'apply look'. Reset puts those knobs back to their defaults."))
    add('look "God Rays"')
    add('addUserKnob {22 apply_look l "apply look" t %s T %s -STARTLINE}'
        % (q("Sets the knobs from the chosen look."), q(APPLY_LOOK)))
    add('addUserKnob {1 status t %s +DISABLED}'
        % q("The main warning from the last Analyze. It doesn't update by itself: press Analyze again."))
    add('status "Press Analyze to check the setup."')
    add('addUserKnob {7 scene_depth +INVISIBLE}')
    add('addUserKnob {4 viewer_resolution l "viewer resolution" t %s M {Full Half Quarter}}'
        % q("Size the passes are computed at in the Nuke GUI, then scaled back up. Half is about four times "
            "faster than Full. Renders from a terminal or the farm use 'render resolution'."))
    add('viewer_resolution Half')
    add('addUserKnob {4 render_resolution l "render resolution" t %s -STARTLINE M {Full Half Quarter}}'
        % q("Size the passes are computed at when rendering outside the GUI (terminal, farm)."))
    add('addUserKnob {4 shafts_resolution l "shafts at" t %s -STARTLINE M {Same Half Quarter}}'
        % q("The shafts are soft, so they can be computed smaller again than the ground matte: Half of the "
            "viewer or render resolution is four times faster and rarely shows."))
    add('shafts_resolution Half')
    add('addUserKnob {7 matte_scale +INVISIBLE}')
    add('matte_scale {{"(\\$gui ? viewer_resolution : render_resolution) == 0 ? 1 : '
        '(\\$gui ? viewer_resolution : render_resolution) == 1 ? 0.5 : 0.25"}}')
    add('addUserKnob {7 shafts_scale +INVISIBLE}')
    add('shafts_scale {{"matte_scale * (shafts_resolution == 0 ? 1 : shafts_resolution == 1 ? 0.5 : 0.25)"}}')

    add('addUserKnob {26 inputs_divider l Inputs}')
    add('addUserKnob {41 position_layer l "position layer" t %s T PositionPick.in1}'
        % q("Layer of the env render holding world position (P World), in scene units."))
    add('addUserKnob {1 clouds_depth l "clouds depth" t %s}'
        % q("Channel of the clouds input holding its depth (Planar Z, scene units). Only analyze reads it."))
    add('clouds_depth depth.Z')
    add('addUserKnob {7 scene_scale l "units to metres" t %s R 0 1}'
        % q("Scene units to metres: 0.1 for decimetres. Analyze takes it from the EzAtmosScatter in 'atmos'."))
    add('scene_scale 0.1')

    add('addUserKnob {26 sun_divider l Sun}')
    add('addUserKnob {4 sun_from l "sun from" t %s M {Auto "Sun Input (Axis)" EzAtmosScatter Manual}}'
        % q("Auto: the Axis in the 'sun' input if there is one, else the EzAtmosScatter in 'atmos', else "
            "'sun direction'. The Axis's world position is the direction towards the sun."))
    add('addUserKnob {13 sun_direction l "sun direction" t %s}'
        % q("Direction towards the sun, +Y up, used when there is no Axis or atmos (or 'sun from' is Manual)."))
    add('sun_direction {0 0.5 -1}')
    add('addUserKnob {13 sun_in_use l "sun in use" t %s +DISABLED}'
        % q("The sun direction in use, whichever 'sun from' picked. Read only."))
    add('addUserKnob {7 sun_rotation_in_use l "sun rotation" +INVISIBLE}')

    add('addUserKnob {26 clouds_divider l "Cloud gobo"}')
    add('addUserKnob {7 cloud_height l "cloud height (m)" t %s R 0 8000}'
        % q("Height of the cloud sheet above the scene's 0, in metres. Analyze measures it from the clouds' "
            "depth; raise or lower it to slide the shadows along the sun."))
    add('cloud_height 2000')
    add('addUserKnob {7 cloud_density l "cloud density" t %s R 0 3}'
        % q("Multiplies the clouds alpha: above 1 thin cloud blocks more sun."))
    add('cloud_density 1')
    add('addUserKnob {7 gap_contrast l "gap contrast" t %s R 0.1 10}'
        % q("Levels on the clouds' alpha before it is used as the gobo. Above 1 thin, soft clouds become more "
            "clearly solid or clear, for crisper beams. 1 with threshold 0.5 changes nothing."))
    add('gap_contrast 1')
    add('addUserKnob {7 gap_threshold l "gap threshold" t %s}'
        % q("The alpha that stays at 0.5 under 'gap contrast'. Higher opens more gaps; lower closes them."))
    add('gap_threshold 0.5')
    add('addUserKnob {6 use_cloud_depth l "use cloud depth" t %s +STARTLINE}'
        % q("Casts each cloud from the height its depth says, instead of one flat 'cloud height'. For clouds at "
            "clearly different heights; needs a good depth channel. Off suits a single layer."))
    add('addUserKnob {7 sun_view_width l "sun view width" t %s R 0 1000000}'
        % q("With the 'sunclouds' input: the width the sun-view render covers, in scene units (the orthographic "
            "camera's width)."))
    add('sun_view_width 100000')
    add('addUserKnob {7 shadow_strength l "shadow strength" t %s}'
        % q("How much sunlight the cloud takes away: 1 is all of it."))
    add('shadow_strength 1')
    add('addUserKnob {4 outside_frame l "outside frame" t %s M {Lit Shadowed}}'
        % q("Where the sun ray meets the cloud sheet outside the clouds render (past its overscan), as the "
            "camera sees it: count it as a gap (Lit) or as cloud (Shadowed)."))
    add('addUserKnob {7 penumbra l "softness (deg)" t %s R 0 5}'
        % q("Spreads the sun over a cone this wide, so shadow edges soften the further they fall from the "
            "cloud. The real sun is about 0.27."))
    add('penumbra 0.5')
    add('addUserKnob {3 samples l "softness samples" t %s}'
        % q("Sun directions averaged for the ground matte. More is smoother and slower."))
    add('samples 6')
    add('addUserKnob {7 drift_x l "drift x (m/frame)" t %s R -20 20}'
        % q("Moves the cloud shadows across the ground over time, for clouds rendered still."))
    add('addUserKnob {7 drift_z l "drift z (m/frame)" t %s R -20 20}'
        % q("Moves the cloud shadows across the ground over time, for clouds rendered still."))
    add('addUserKnob {3 drift_frame l "drift from frame" t %s}' % q("The frame where the drift is 0."))
    add('drift_frame 1001')

    add('addUserKnob {26 shafts_divider l Shafts}')
    add('addUserKnob {7 shaft_density l "haze density (1/km)" t %s R 0 1}'
        % q("How much the air in front of the terrain scatters the sun at camera height: more gives "
            "stronger beams. 0.1 is light haze."))
    add('shaft_density 0.1')
    add('addUserKnob {7 haze_height l "haze height (km)" t %s R 0.1 5}'
        % q("Height over which the haze thins out by a factor of e."))
    add('haze_height 1.2')
    add('addUserKnob {7 shaft_start l "start (m)" t %s R 0 2000}' % q("Air nearer than this has no beams."))
    add('addUserKnob {7 max_distance l "max distance (km)" t %s R 0 50}'
        % q("Air further than this has no beams. 0 runs to the terrain."))
    add('addUserKnob {7 sky_distance l "sky distance (km)" t %s R 1 100}'
        % q("How far the beams reach where there is no terrain (sky), if the cloud sheet is not met first."))
    add('sky_distance 20')
    add('addUserKnob {3 march_steps l steps t %s}'
        % q("Steps along each view ray. More gives cleaner beams and is slower."))
    add('march_steps 32')
    add('addUserKnob {4 color_from l "colour from" t %s M {EzAtmosScatter Color}}'
        % q("EzAtmosScatter: the sunlit haze colour of the atmos input (atmos_haze_sun along the view), "
            "times 'shaft color'. Color: 'shaft color' alone. Without an atmos input it is Color."))
    add('addUserKnob {18 shaft_color l "shaft color" t %s}' % q("Colour of the beams, or a tint on the atmos colour."))
    add('shaft_color 1')
    add('addUserKnob {7 shaft_intensity l intensity t %s R 0 10}' % q("Multiplies the beams, rgb and matte."))
    add('shaft_intensity 1')
    add('addUserKnob {7 soften l "soften (px)" t %s R 0 20}'
        % q("Blurs the shafts and shafts_lit layers to take out the sampling grain of long rays. 0 is off."))
    add('soften 4')
    add('addUserKnob {6 edge_aware l "edge aware" t %s -STARTLINE}'
        % q("Keeps the softening from blurring beams across ridge lines, using the distance to the camera from "
            "the position layer. Off is a plain blur, which is a little faster."))
    add('edge_aware true')

    add('addUserKnob {26 comp_divider l Comp}')
    add('addUserKnob {7 comp_shadow l "cloud shadow" t %s}'
        % q("How much of the sun light the cloud shadow takes off the env: 0 none, 1 all of it. Use 1 with a sun "
            "light layer; without one the whole env is darkened, so keep it lower."))
    add('comp_shadow 0.7')
    add('addUserKnob {6 use_sun_layer l "sun light layer" t %s +STARTLINE}'
        % q("On: the cloud shadow only darkens the env's sun light group, picked on the right (the beauty must be "
            "the sum of its light groups). Off: it darkens the whole env."))
    add('addUserKnob {41 sun_layer l "" t %s -STARTLINE T SunPick.in1}'
        % q("Layer of the env render holding the sun's light group."))
    add('addUserKnob {7 comp_haze l "haze amount" t %s R 0 3}'
        % q("How strongly the haze veils the env with distance. 0 is no haze: only the shadow and the shafts."))
    add('comp_haze 1')
    add('addUserKnob {18 comp_haze_color l "haze color" t %s}' % q("Colour of the haze light."))
    add('comp_haze_color {0.06 0.13 0.33}')
    add('addUserKnob {4 comp_haze_from l "haze color from" t %s M {Color EzAtmosScatter}}'
        % q("Color: 'haze color'. EzAtmosScatter: the atmos's sky haze along each view ray, times 'haze tint', so "
            "the air matches the sky. Without an atmos input it is Color."))
    add('addUserKnob {18 comp_haze_tint l "haze tint" t %s}' % q("Multiplies the atmos's sky haze."))
    add('comp_haze_tint 1')
    add('addUserKnob {18 comp_haze_falloff l "haze falloff" t %s}'
        % q("How fast each colour fades with distance: higher fades sooner. Blue above red gives the warm "
            "near, blue far of aerial perspective."))
    add('comp_haze_falloff {0.75 1 1.4}')
    add('addUserKnob {7 comp_haze_shadow l "haze in shadow" t %s R 0 2}'
        % q("Brightness of the haze where the cloud shades it: below 1 darkens the air between the beams."))
    add('comp_haze_shadow 0.35')
    add('addUserKnob {7 comp_haze_lit l "haze in sun" t %s R 0 4}'
        % q("Brightness of the haze where the sun reaches it."))
    add('comp_haze_lit 1.5')
    add('addUserKnob {7 comp_shafts l "shafts" t %s R 0 2}' % q("How much of shafts.rgb is added on top."))
    add('comp_shafts 1')

    add('addUserKnob {26 bake_divider l Bake}')
    add('addUserKnob {2 bake_folder l "bake folder" t %s}'
        % q("Where bakes go, for example on the job so the farm can read them. Each script and node gets its own "
            "subfolder. $VAR and [getenv VAR] work. Empty: an ezcloudshafts_cache folder beside the script."))
    add('bake_folder %s' % q("[getenv NUKE_TEMP_DIR]/ezCloudShafts"))
    add('addUserKnob {2 bake_file l "bake file" t %s}'
        % q("Leave empty to use 'bake folder'. A full file path with #### overrides it for this node."))
    add('addUserKnob {3 bake_first l "bake range" t %s}' % q("First frame to bake."))
    add('addUserKnob {3 bake_last l "" t %s -STARTLINE}' % q("Last frame to bake."))
    add('addUserKnob {22 bake_now l "bake now" t %s T %s +STARTLINE}'
        % (q("Writes the shafts, shafts_lit and cloudshadow layers to the bake file here and now."), q(BAKE_NOW)))
    add('addUserKnob {22 bake_farm_write l "make farm bake Write" t %s T %s -STARTLINE}'
        % (q("Adds a Write below this node with the bake path, to render on the farm before the comp."), q(BAKE_FARM)))
    add('addUserKnob {6 use_baked l "use baked" t %s +STARTLINE}'
        % q("Read the bake instead of computing, but only while it exists and the settings still match it. "
            "Otherwise the node computes live and its label says the bake is out of date. The check runs when a "
            "knob or input of this node changes and when the script opens; after changing the camera or clouds "
            "upstream, bake again."))
    add('use_baked true')
    add('addUserKnob {1 baked_hash +INVISIBLE}')
    add('addUserKnob {3 baked_first +INVISIBLE}')
    add('addUserKnob {3 baked_last +INVISIBLE}')
    add('addUserKnob {6 bake_valid -STARTLINE +INVISIBLE}')
    add('addUserKnob {22 bake_check +INVISIBLE T %s}' % q(BAKE_CHECK))

    add('addUserKnob {26 version_divider l "" +STARTLINE}')
    add('addUserKnob {26 version T "EzCloudShafts v%s"}' % VERSION)

    # Hidden: the camera, atmos and Axis, read through any Dots or NoOps in their inputs.
    add('addUserKnob {78 cam_world_matrix l "camera matrix" +INVISIBLE n 16}')
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    add('cam_world_matrix {%s}' % " ".join(
        "{%s}" % q(py_expr(FIND_CAMERA + "ret = c['world_matrix'].getValueAt(nuke.frame(), %d) "
                                         "if c is not None else %d" % (i, identity[i]))) for i in range(16)))
    for name, default in (("focal", 35), ("haperture", 36), ("vaperture", 20.25)):
        add('addUserKnob {7 cam_%s +INVISIBLE}' % name)
        add('cam_%s {{%s}}' % (name, q(py_expr(FIND_CAMERA + "ret = c['%s'].getValueAt(nuke.frame()) "
                                                             "if c is not None else %g" % (name, default)))))
    add('addUserKnob {3 atm_found +INVISIBLE}')
    add('atm_found {{%s}}' % q(py_expr(FIND_ATMOS + "ret = 1 if a is not None else 0")))
    add('addUserKnob {13 atm_sun +INVISIBLE}')
    add('atm_sun {%s}' % " ".join(
        "{%s}" % q(py_expr(FIND_ATMOS + "ret = (a.knob('sun_in_use') or a.knob('sun_direction'))"
                                        ".getValueAt(nuke.frame(), %d) if a is not None else 0" % i))
        for i in range(3)))
    add('addUserKnob {7 atm_rotation +INVISIBLE}')
    add('atm_rotation {{%s}}' % q(py_expr(FIND_ATMOS + "ret = a['hdri_rotation'].getValueAt(nuke.frame()) "
                                                       "if a is not None and a.knob('hdri_rotation') else 0")))
    # The atmos layers are in the camera's view (not lat-long) when its output is Camera.
    add('addUserKnob {3 atm_screen +INVISIBLE}')
    add('atm_screen {{%s}}' % q(py_expr(FIND_ATMOS + "ret = 1 if a is not None and a.knob('output_mapping') "
                                                     "and int(a['output_mapping'].getValue()) == 2 else 0")))
    add('addUserKnob {3 axis_found +INVISIBLE}')
    add('axis_found {{%s}}' % q(py_expr(FIND_AXIS + "ret = 1 if x is not None else 0")))
    add('addUserKnob {13 axis_position +INVISIBLE}')
    add('axis_position {%s}' % " ".join(
        "{%s}" % q(py_expr(FIND_AXIS + "ret = x['world_matrix'].getValueAt(nuke.frame(), %d) "
                                       "if x is not None else 0" % (3 + 4 * i))) for i in range(3)))
    # The orthographic sun-view camera.
    add('addUserKnob {3 sun_view_on +INVISIBLE}')
    add('sun_view_on {{"\\[exists input5] && \\[exists input6]"}}')
    add('addUserKnob {78 sun_world_matrix +INVISIBLE n 16}')
    add('sun_world_matrix {%s}' % " ".join(
        "{%s}" % q(py_expr(FIND_SUNCAM + "ret = c['world_matrix'].getValueAt(nuke.frame(), %d) "
                                         "if c is not None else %d" % (i, identity[i]))) for i in range(16)))
    # 0 manual, 1 Axis, 2 atmos.
    add('addUserKnob {3 sun_source +INVISIBLE}')
    add('sun_source {{"sun_from==1 ? (axis_found ? 1 : 0) : sun_from==2 ? (atm_found ? 2 : 0) : '
        'sun_from==3 ? 0 : (axis_found ? 1 : atm_found ? 2 : 0)"}}')
    return k


def group_expressions():
    """Expressions on the visible read-only sun knobs, written after the knobs exist."""
    lines = ['sun_in_use {%s}' % " ".join(
        '{"sun_source==1 ? axis_position.%s : sun_source==2 ? atm_sun.%s : sun_direction.%s"}' % (c, c, c)
        for c in "xyz")]
    lines.append('sun_rotation_in_use {{"sun_source==2 ? atm_rotation : 0"}}')
    return lines


# ---- The nodes inside --------------------------------------------------------------------

def shuffle_mappings(layer, alpha_from=None):
    """Shuffle2 mappings: the layer's rgb to rgba.rgb, alpha black (or from alpha_from)."""
    m = ["%s.%s 0 %d rgba.%s 0 %d" % (layer, c, i, c, i) for i, c in enumerate(("red", "green", "blue"))]
    m.append("black -1 -1 rgba.alpha 0 3")
    return '"4 %s"' % " ".join(m)


ALPHA_TO_RGB = '"4 %s"' % " ".join(
    ["rgba.alpha 0 3 rgba.%s 0 %d" % (c, i) for i, c in enumerate(("red", "green", "blue"))] +
    ["rgba.alpha 0 3 rgba.alpha 0 3"])


def blink_node(name, output, source, work, overrides=None):
    links = {
        "output": str(output),
        "frame_size": "{%s.width} {%s.height}" % (work, work),
        "cam_row0": "{parent.cam_world_matrix.0} {parent.cam_world_matrix.1} {parent.cam_world_matrix.2}",
        "cam_row1": "{parent.cam_world_matrix.4} {parent.cam_world_matrix.5} {parent.cam_world_matrix.6}",
        "cam_row2": "{parent.cam_world_matrix.8} {parent.cam_world_matrix.9} {parent.cam_world_matrix.10}",
        "cam_position": "{parent.cam_world_matrix.3} {parent.cam_world_matrix.7} {parent.cam_world_matrix.11}",
        "focal": "{parent.cam_focal}",
        "haperture": "{parent.cam_haperture}",
        "vaperture": "{parent.cam_vaperture}",
        "scene_scale": "{parent.scene_scale}",
        "clouds_size": "{CloudsOrNone.width} {CloudsOrNone.height}",
        # Overscan baked into a bigger format than the env's sits evenly around the frame.
        "clouds_overscan": '{"max(0, (CloudsOrNone.width - PositionPick.width) / 2)"} '
                           '{"max(0, (CloudsOrNone.height - PositionPick.height) / 2)"}',
        "sun_direction": "{parent.sun_in_use.x} {parent.sun_in_use.y} {parent.sun_in_use.z}",
        "sun_rotation": "{parent.sun_rotation_in_use}",
        "cloud_height": "{parent.cloud_height}",
        "cloud_density": "{parent.cloud_density}",
        "shadow_strength": "{parent.shadow_strength}",
        "outside_lit": '{"parent.outside_frame==0"}',
        "drift": '{"parent.drift_x * (frame - parent.drift_frame)"} {"parent.drift_z * (frame - parent.drift_frame)"}',
        "penumbra": "{parent.penumbra}",
        "samples": "{parent.samples}",
        "shaft_density": '{"parent.shaft_density / 1000"}',
        "haze_height": '{"parent.haze_height * 1000"}',
        "shaft_start": "{parent.shaft_start}",
        "max_distance": '{"parent.max_distance * 1000"}',
        "sky_distance": '{"parent.sky_distance * 1000"}',
        "march_steps": "{parent.march_steps}",
        "use_env": '{"parent.color_from==0 && parent.atm_found"}',
        "env_screen": "{parent.atm_screen}",
        "env_rotation": "{parent.atm_rotation}",
        "shaft_color": "{parent.shaft_color.r} {parent.shaft_color.g} {parent.shaft_color.b}",
        "shaft_intensity": "{parent.shaft_intensity}",
        "seed": "{frame}",
        "use_depth": "{parent.use_cloud_depth}",
        "use_sun_view": "{parent.sun_view_on}",
        "sun_row0": "{parent.sun_world_matrix.0} {parent.sun_world_matrix.1} {parent.sun_world_matrix.2}",
        "sun_row1": "{parent.sun_world_matrix.4} {parent.sun_world_matrix.5} {parent.sun_world_matrix.6}",
        "sun_row2": "{parent.sun_world_matrix.8} {parent.sun_world_matrix.9} {parent.sun_world_matrix.10}",
        "sun_position": "{parent.sun_world_matrix.3} {parent.sun_world_matrix.7} {parent.sun_world_matrix.11}",
        "sun_width": "{parent.sun_view_width}",
    }
    links.update(overrides or {})
    assert set(links) == set(p[0] for p in PARAMS), set(p[0] for p in PARAMS) ^ set(links)
    body = ["recompileCount 1",
            "KernelDescription " + kernel_description(source),
            "kernelSource " + q(source),
            'rebuild ""']
    for pname, _, _, _, _ in PARAMS:
        value = links[pname]
        body.append("%s_%s %s" % (KERNEL, pname, value if pname == "output" else "{%s}" % value))
    body.append('rebuild_finalise ""')
    return body


def work_reformat(scale):
    return ["type scale", "scale {{%s} {%s}}" % (scale, scale), "filter impulse"]


def full_reformat():
    return ["type \"to box\"", "box_width {{PositionPick.width}}", "box_height {{PositionPick.height}}",
            "box_fixed true", "resize distort", "filter cubic"]


def depth_pick():
    """Shuffle2 knobs: the clouds' depth into red, for the kernel, when 'use cloud depth' is on."""
    return ["fromInput1 {{0} B}", "in1 depth", "fromInput2 {{0} B}", "in2 rgba",
            'mappings "4 depth.Z 0 0 rgba.red 0 0 rgba.green 1 1 rgba.green 0 1 rgba.blue 1 2 rgba.blue 0 2 '
            'rgba.alpha 1 3 rgba.alpha 0 3"', 'disable {{"!parent.use_cloud_depth"}}']


def haze_layer_copy():
    return ["inputs 2"] + ["from%d rgba.%s\n  to%d shafts_haze.%s" % (i, c, i, c)
                           for i, c in enumerate(("red", "green", "blue"))]


def layer_copy(layer):
    """Copy knobs: rgba into the four channels of a layer."""
    return ["inputs 2"] + ["from%d rgba.%s\n  to%d %s.%s" % (i, c, i, layer, c)
                           for i, c in enumerate(("red", "green", "blue", "alpha"))]


def layer_pick(layer):
    """Shuffle2 knobs: a four-channel layer to rgba."""
    maps = " ".join("%s.%s 0 %d rgba.%s 0 %d" % (layer, c, i, c, i)
                    for i, c in enumerate(("red", "green", "blue", "alpha")))
    return ["fromInput1 {{0} B}", "in1 " + layer, "fromInput2 {{0} B}", 'mappings "4 %s"' % maps]


def use_baked():
    return ["inputs 2", 'which {{"parent.use_baked && parent.bake_valid"}}']


def nodes(source):
    """(name, class, [input names], [knob lines]) in creation order."""
    tiny = '"8 4 0 0 8 4 1 EzCloudShafts_tiny"'
    return [
        ("env", "Input", [], ["inputs 0"]),
        ("clouds", "Input", [], ["inputs 0", "number 1"]),
        ("camera", "Input", [], ["inputs 0", "number 2"]),
        ("atmos", "Input", [], ["inputs 0", "number 3"]),
        ("sun", "Input", [], ["inputs 0", "number 4"]),
        ("sunclouds", "Input", [], ["inputs 0", "number 5"]),
        ("suncam", "Input", [], ["inputs 0", "number 6"]),
        ("PositionPick", "Shuffle2", ["env"], ["fromInput1 {{0} B}", "in1 P", "fromInput2 {{0} B}",
                                               "mappings " + shuffle_mappings("P")]),
        ("NoClouds", "Constant", [], ["inputs 0", "format " + tiny]),
        ("CloudsOrNone", "Switch", ["NoClouds", "clouds"], ["inputs 2", 'which {{"\\[exists parent.input1]"}}']),
        # Levels on the gobo: the render itself isn't touched, only what the passes read.
        ("GoboDepth", "Shuffle2", ["CloudsOrNone"], depth_pick()),
        ("GoboLevels", "Expression", ["GoboDepth"],
         ["channel0 none", "channel1 none", "channel2 none", "channel3 alpha",
          'expr3 "clamp(0.5+(a-parent.gap_threshold)*parent.gap_contrast,0,1)"']),
        ("NoSunClouds", "Constant", [], ["inputs 0", "format " + tiny]),
        ("SunCloudsOrNone", "Switch", ["NoSunClouds", "sunclouds"], ["inputs 2", 'which {{"\\[exists parent.input5]"}}']),
        ("SunGoboLevels", "Expression", ["SunCloudsOrNone"],
         ["channel0 none", "channel1 none", "channel2 none", "channel3 alpha",
          'expr3 "clamp(0.5+(a-parent.gap_threshold)*parent.gap_contrast,0,1)"']),
        ("AtmosSkyPick", "Shuffle2", ["atmos"], ["fromInput1 {{0} B}", "in1 atmos_haze_sky", "fromInput2 {{0} B}",
                                                 "mappings " + shuffle_mappings("atmos_haze_sky")]),
        ("NoAtmosSky", "Constant", [], ["inputs 0", "format " + tiny]),
        ("AtmosSkyOrNone", "Switch", ["NoAtmosSky", "AtmosSkyPick"], ["inputs 2", 'which {{"\\[exists parent.input3]"}}']),
        ("AtmosSunPick", "Shuffle2", ["atmos"], ["fromInput1 {{0} B}", "in1 atmos_haze_sun", "fromInput2 {{0} B}",
                                                 "mappings " + shuffle_mappings("atmos_haze_sun")]),
        ("NoAtmos", "Constant", [], ["inputs 0", "format " + tiny]),
        ("AtmosOrNone", "Switch", ["NoAtmos", "AtmosSunPick"], ["inputs 2", 'which {{"\\[exists parent.input3]"}}']),
        # The passes run on a scaled-down P (impulse, so no position is ever blended across an
        # edge), then are scaled back up to the env's format.
        ("WorkPosMatte", "Reformat", ["PositionPick"], work_reformat("parent.matte_scale")),
        ("WorkPosShafts", "Reformat", ["PositionPick"], work_reformat("parent.shafts_scale")),
        ("Pass_Shafts", "BlinkScript", ["WorkPosShafts", "GoboLevels", "AtmosOrNone", "SunGoboLevels"],
         ["inputs 4"] + blink_node("Pass_Shafts", 0, source, "WorkPosShafts")),
        ("Pass_Ground", "BlinkScript", ["WorkPosMatte", "GoboLevels", "AtmosOrNone", "SunGoboLevels"],
         ["inputs 4"] + blink_node("Pass_Ground", 1, source, "WorkPosMatte")),
        ("Full_Shafts", "Reformat", ["Pass_Shafts"], full_reformat()),
        ("Full_Ground", "Reformat", ["Pass_Ground"], full_reformat()),
        ("Pass_LitShare", "BlinkScript", ["WorkPosShafts", "GoboLevels", "AtmosOrNone", "SunGoboLevels"],
         ["inputs 4"] + blink_node("Pass_LitShare", 2, source, "WorkPosShafts")),
        ("Full_LitShare", "Reformat", ["Pass_LitShare"], full_reformat()),
        # The atmos's sky haze as the camera sees it, for the Comp's haze colour.
        ("Pass_ViewSky", "BlinkScript", ["WorkPosShafts", "GoboLevels", "AtmosSkyOrNone", "SunGoboLevels"],
         ["inputs 4"] + blink_node("Pass_ViewSky", 3, source, "WorkPosShafts", overrides={
             "use_env": '{"parent.atm_found"}', "shaft_color": "1 1 1"})),
        ("Full_ViewSky", "Reformat", ["Pass_ViewSky"], full_reformat()),
        # Softened, to take the march's sampling grain out of the layers.
        ("Soft_Shafts_Blur", "Blur", ["Full_Shafts"], ["channels rgba", "size {{parent.soften}}"]),
        ("Soft_Shafts_Edge", "BlinkScript", ["Full_Shafts", "PositionPick"], soften_node()),
        ("Soft_Shafts", "Switch", ["Soft_Shafts_Blur", "Soft_Shafts_Edge"], ["inputs 2", "which {{parent.edge_aware}}"]),
        ("Soft_LitShare_Blur", "Blur", ["Full_LitShare"], ["channels rgba", "size {{parent.soften}}"]),
        ("Soft_LitShare_Edge", "BlinkScript", ["Full_LitShare", "PositionPick"], soften_node()),
        ("Soft_LitShare", "Switch", ["Soft_LitShare_Blur", "Soft_LitShare_Edge"],
         ["inputs 2", "which {{parent.edge_aware}}"]),
        # The bake: what the passes make, written out, read back, and picked between.
        ("Bake_Shafts", "Copy", ["env", "Soft_Shafts"], layer_copy("shafts")),
        ("Bake_Ground", "Copy", ["Bake_Shafts", "Full_Ground"], layer_copy("cloudshadow")),
        ("Bake_LitShare", "Copy", ["Bake_Ground", "Soft_LitShare"], layer_copy("shafts_lit")),
        ("BakeKeep", "Remove", ["Bake_LitShare"], ["operation keep", "channels shafts", "channels2 cloudshadow",
                                                   "channels3 shafts_lit"]),
        ("BakeWrite", "Write", ["BakeKeep"], ["channels all", "file " + q(BAKE_PATH), "file_type exr",
                                              "first_part rgba", "create_directories true"]),
        ("BakeRead", "Read", [], ["inputs 0", "file " + q(BAKE_PATH), "first {{parent.baked_first}}",
                                  "last {{parent.baked_last}}", "origfirst {{parent.baked_first}}",
                                  "origlast {{parent.baked_last}}", "on_error black"]),
        ("Baked_Shafts", "Shuffle2", ["BakeRead"], layer_pick("shafts")),
        ("Baked_Ground", "Shuffle2", ["BakeRead"], layer_pick("cloudshadow")),
        ("Baked_LitShare", "Shuffle2", ["BakeRead"], layer_pick("shafts_lit")),
        ("Use_Shafts", "Switch", ["Soft_Shafts", "Baked_Shafts"], use_baked()),
        ("Use_Ground", "Switch", ["Full_Ground", "Baked_Ground"], use_baked()),
        ("Use_LitShare", "Switch", ["Soft_LitShare", "Baked_LitShare"], use_baked()),
        ("Layer_Shafts", "Copy", ["env", "Use_Shafts"],
         ["inputs 2"] + ["from%d rgba.%s\n  to%d shafts.%s" % (i, c, i, c)
                         for i, c in enumerate(("red", "green", "blue", "alpha"))]),
        ("Layer_CloudShadow", "Copy", ["Layer_Shafts", "Use_Ground"],
         ["inputs 2"] + ["from%d rgba.%s\n  to%d cloudshadow.%s" % (i, c, i, c)
                         for i, c in enumerate(("red", "green", "blue", "alpha"))]),
        ("Layer_LitShare", "Copy", ["Layer_CloudShadow", "Use_LitShare"],
         ["inputs 2"] + ["from%d rgba.%s\n  to%d shafts_lit.%s" % (i, c, i, c)
                         for i, c in enumerate(("red", "green", "blue", "alpha"))]),
        ("ShaftsOver", "Merge2", ["Layer_LitShare", "Use_Shafts"], ["inputs 2", "operation plus", "output rgb"]),
        ("ShadowView", "Shuffle2", ["Use_Ground"], ["fromInput1 {{0} B}", "in1 rgba", "fromInput2 {{0} B}",
                                                    "mappings " + ALPHA_TO_RGB]),
        ("ShaftsMatteView", "Shuffle2", ["Use_Shafts"], ["fromInput1 {{0} B}", "in1 rgba", "fromInput2 {{0} B}",
                                                          "mappings " + ALPHA_TO_RGB]),
        # The Comp view: cloud shadow on the sun light, haze from shafts_lit, then the shafts.
        ("SunPick", "Shuffle2", ["env"], ["fromInput1 {{0} B}", "in1 rgba", "fromInput2 {{0} B}",
                                          "mappings " + shuffle_mappings("rgba")]),
        ("SunOrBeauty", "Switch", ["env", "SunPick"], ["inputs 2", "which {{parent.use_sun_layer}}"]),
        ("Comp_ShadowAmount", "Expression", ["Use_Ground"],
         ['expr%d "(1-a)*parent.comp_shadow"' % i for i in range(3)]),
        ("Comp_SunLost", "Merge2", ["Comp_ShadowAmount", "SunOrBeauty"],
         ["inputs 2", "operation multiply", "output rgb"]),
        ("Comp_Land", "Merge2", ["env", "Comp_SunLost"], ["inputs 2", "operation from", "output rgb"]),
        ("Comp_Transmittance", "Expression", ["Use_LitShare"],
         ['expr%d "pow(clamp(1-a,0,1), parent.comp_haze*parent.comp_haze_falloff.%s)"' % (i, c)
          for i, c in enumerate("rgb")] + ["expr3 r"]),
        ("Comp_LandHazed", "Merge2", ["Comp_Land", "Comp_Transmittance"],
         ["inputs 2", "operation multiply", "output rgb"]),
        ("Comp_HazeLight", "Expression", ["Comp_Transmittance"],
         ['expr%d "(1-%s)*(parent.comp_haze_shadow+'
          '(parent.comp_haze_lit-parent.comp_haze_shadow)*a)"' % (i, c) for i, c in enumerate("rgb")]),
        ("Comp_HazeColor", "Expression", ["Full_ViewSky"],
         ['expr%d "parent.comp_haze_from==1&&parent.atm_found ? %s*parent.comp_haze_tint.%s : parent.comp_haze_color.%s"'
          % (i, c, c, c) for i, c in enumerate("rgb")]),
        ("Comp_HazeTinted", "Merge2", ["Comp_HazeLight", "Comp_HazeColor"],
         ["inputs 2", "operation multiply", "output rgb"]),
        ("Comp_LayerHaze", "Copy", ["Layer_LitShare", "Comp_HazeColor"], haze_layer_copy()),
        ("Comp_PlusHaze", "Merge2", ["Comp_LandHazed", "Comp_HazeTinted"],
         ["inputs 2", "operation plus", "output rgb"]),
        ("Comp_PlusShafts", "Merge2", ["Comp_PlusHaze", "Use_Shafts"],
         ["inputs 2", "operation plus", "output rgb", "mix {{parent.comp_shafts}}"]),
        ("ViewOutput", "Switch", ["Comp_LayerHaze", "ShaftsOver", "ShadowView", "Use_Ground", "ShaftsMatteView",
                                  "Use_LitShare", "Comp_PlusShafts"],
         ["inputs 7", "which {{parent.view}}"]),
        ("MainRGB", "Copy", ["Comp_LayerHaze", "ViewOutput"], ["inputs 2", "channels rgb"]),
        ("Output1", "Output", ["MainRGB"], []),
    ]


def write(path, kind):
    with open(os.path.join(ROOT, "blink", KERNEL + ".blink")) as f:
        source = f.read()
    out = ["version 15.1 v3"]
    for layer, chans in LAYERS.items():
        out.append("add_layer {%s %s}" % (layer, " ".join("%s.%s" % (layer, c) for c in chans)))
    out.append("%s {" % kind)
    out.append(" name EzCloudShafts1")
    out.append(" onCreate " + q(ON_CREATE))
    out.append(" knobChanged " + q(KNOB_CHANGED))
    out.append(" tile_color 0xb08a4aff")
    out += [" " + line for line in knob_lines() + group_expressions()]
    out.append("}")
    var = {}
    for name, cls, ins, knobs in nodes(source):
        for i in reversed(ins):
            out.append("push $" + var[i])
        out.append(" %s {" % cls)
        for line in knobs:
            out.append("  " + line)
        out.append("  name " + name)
        out.append("  xpos 0")
        out.append("  ypos 0")
        out.append(" }")
        var[name] = "N%08x" % (0x1b700000 + len(var))
        out.append("set %s [stack 0]" % var[name])
    out.append("end_group")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    problems = node_layout.apply_nk(path, **layout_hints.HINTS)
    for p in problems:
        print("%s: %s" % (path, p))
    print("wrote %s (%d layout problems)" % (os.path.relpath(path, ROOT), len(problems)))
    return problems


if __name__ == "__main__":
    bad = write(GROUP_PATH, "Group") + write(GIZMO_PATH, "Gizmo")
    sys.exit(1 if bad else 0)
