"""Write groups/EzCloudShafts_group.nk and gizmos/EzCloudShafts.gizmo from blink/EzCloudShafts.blink.

Plain Python, no Nuke needed:

    python3 python/build_group.py

The node is self-contained: the kernel source, the Analyze button's code and every expression
live on the node, so it needs no init.py, menu.py or Python module. The graph inside is laid
out with node_layout.py (layout_hints.py says how).

Inputs: 0 env (the environment render with a world position layer), 1 clouds (the flattened
clouds render: rgba + depth), 2 camera, 3 atmos (an EzAtmosScatter, optional: sun direction
and colour), 4 sun (an Axis, optional: overrides the sun direction).
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
GROUP_PATH = os.path.join(ROOT, "groups", "EzCloudShafts_group.nk")
GIZMO_PATH = os.path.join(ROOT, "gizmos", "EzCloudShafts.gizmo")

LAYERS = {"P": ["red", "green", "blue"],
          "shafts": ["red", "green", "blue", "alpha"],
          "cloudshadow": ["red", "green", "blue", "alpha"],
          "atmos_haze_sun": ["red", "green", "blue"]}

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
    ("samples", "samples", "Int", 1, 6),
    ("shaft_density", "shaftDensity", "Float", 1, 0.0001),
    ("haze_height", "hazeHeight", "Float", 1, 1200.0),
    ("shaft_start", "shaftStart", "Float", 1, 0.0),
    ("max_distance", "maxDistance", "Float", 1, 0.0),
    ("sky_distance", "skyDistance", "Float", 1, 20000.0),
    ("march_steps", "marchSteps", "Int", 1, 32),
    ("use_env", "useEnv", "Int", 1, 0),
    ("env_screen", "envScreen", "Int", 1, 0),
    ("env_rotation", "envRotation", "Float", 1, 0.0),
    ("shaft_color", "shaftColor", "Float", 3, (1, 0.9, 0.75)),
    ("shaft_intensity", "shaftIntensity", "Float", 1, 1.0),
    ("seed", "seed", "Float", 1, 1.0),
]
LOCALS = [("pi", 1), ("sunWorld", 3), ("sunX", 3), ("sunY", 3)]
IMAGES = [("pos", "Read", "Point"), ("clouds", "Read", "Random"), ("envSun", "Read", "Random"),
          ("dst", "Write", "Point")]


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


def kernel_description(source):
    """What a saved BlinkScript node carries about its compiled kernel, so Nuke can make the
    parameter knobs before it compiles the source again."""
    parts = ["3", '"%s"' % KERNEL, "iterate", "pixelWise", hashlib.sha256(source.encode()).hexdigest(),
             str(len(IMAGES))]
    for name, mode, access in IMAGES:
        parts += ['"%s"' % name, mode, access]
    parts.append(str(len(PARAMS)))
    for name, _, kind, count, default in PARAMS:
        parts += ['"%s"' % name, kind, str(count), _b64(kind, count, default)]
    parts.append(str(len(PARAMS)))
    for _, var, _, count, _ in PARAMS:
        parts += ['"%s"' % var, str(count), "1", "Default"]
    parts.append(str(len(LOCALS)))
    for var, count in LOCALS:
        parts += ['"%s"' % var, "Float", str(count), "1", _b64("Float", count, [0.0] * count)]
    return q(" ".join(parts))


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
            ground = covered = 0
            bounds = clouds.bbox()
            for j in range(36):
                for i in range(64):
                    px = (i + 0.5) * efmt.width() / 64
                    py = (j + 0.5) * efmt.height() / 36
                    p = [env.sample(layer + '.' + c, px, py) * scale
                         for c in ('red', 'green', 'blue')]
                    if p == [0.0, 0.0, 0.0] or p[1] >= h:
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
                        continue
                    x = ox + (0.5 + cx / -cz * focal / hap) * (fmt.width() - 2 * ox)
                    y = oy + (0.5 + cy / -cz * focal / vap) * (fmt.height() - 2 * oy)
                    if bounds.x() <= x < bounds.x() + bounds.w() and bounds.y() <= y < bounds.y() + bounds.h():
                        covered += 1
            if ground:
                notes.append('The gobo reaches %.0f%% of the ground; the rest uses "outside frame" (%s). '
                             'More overscan on the clouds render raises it.'
                             % (100.0 * covered / ground, n['outside_frame'].value()))
        else:
            notes.append('The env input has no "%s" layer: set "position layer" to its world position.' % layer)

nuke.message('EzCloudShafts analyze\n\n' + '\n'.join(notes))
'''


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
        '"Shafts Matte"}}'
        % q("What the main rgb shows. The passes are always written to the shafts and cloudshadow layers; "
            "Passthrough leaves rgba as the env render."))
    add('view "Shafts Over Env"')
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


def blink_node(name, output, source, work):
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
    }
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


def nodes(source):
    """(name, class, [input names], [knob lines]) in creation order."""
    tiny = '"8 4 0 0 8 4 1 EzCloudShafts_tiny"'
    return [
        ("env", "Input", [], ["inputs 0"]),
        ("clouds", "Input", [], ["inputs 0", "number 1"]),
        ("camera", "Input", [], ["inputs 0", "number 2"]),
        ("atmos", "Input", [], ["inputs 0", "number 3"]),
        ("sun", "Input", [], ["inputs 0", "number 4"]),
        ("PositionPick", "Shuffle2", ["env"], ["fromInput1 {{0} B}", "in1 P", "fromInput2 {{0} B}",
                                               "mappings " + shuffle_mappings("P")]),
        ("NoClouds", "Constant", [], ["inputs 0", "format " + tiny]),
        ("CloudsOrNone", "Switch", ["NoClouds", "clouds"], ["inputs 2", 'which {{"\\[exists parent.input1]"}}']),
        ("AtmosSunPick", "Shuffle2", ["atmos"], ["fromInput1 {{0} B}", "in1 atmos_haze_sun", "fromInput2 {{0} B}",
                                                 "mappings " + shuffle_mappings("atmos_haze_sun")]),
        ("NoAtmos", "Constant", [], ["inputs 0", "format " + tiny]),
        ("AtmosOrNone", "Switch", ["NoAtmos", "AtmosSunPick"], ["inputs 2", 'which {{"\\[exists parent.input3]"}}']),
        # The passes run on a scaled-down P (impulse, so no position is ever blended across an
        # edge), then are scaled back up to the env's format.
        ("WorkPosMatte", "Reformat", ["PositionPick"], work_reformat("parent.matte_scale")),
        ("WorkPosShafts", "Reformat", ["PositionPick"], work_reformat("parent.shafts_scale")),
        ("Pass_Shafts", "BlinkScript", ["WorkPosShafts", "CloudsOrNone", "AtmosOrNone"],
         ["inputs 3"] + blink_node("Pass_Shafts", 0, source, "WorkPosShafts")),
        ("Pass_Ground", "BlinkScript", ["WorkPosMatte", "CloudsOrNone", "AtmosOrNone"],
         ["inputs 3"] + blink_node("Pass_Ground", 1, source, "WorkPosMatte")),
        ("Full_Shafts", "Reformat", ["Pass_Shafts"], full_reformat()),
        ("Full_Ground", "Reformat", ["Pass_Ground"], full_reformat()),
        ("Layer_Shafts", "Copy", ["env", "Full_Shafts"],
         ["inputs 2"] + ["from%d rgba.%s\n  to%d shafts.%s" % (i, c, i, c)
                         for i, c in enumerate(("red", "green", "blue", "alpha"))]),
        ("Layer_CloudShadow", "Copy", ["Layer_Shafts", "Full_Ground"],
         ["inputs 2"] + ["from%d rgba.%s\n  to%d cloudshadow.%s" % (i, c, i, c)
                         for i, c in enumerate(("red", "green", "blue", "alpha"))]),
        ("ShaftsOver", "Merge2", ["Layer_CloudShadow", "Full_Shafts"], ["inputs 2", "operation plus", "output rgb"]),
        ("ShadowView", "Shuffle2", ["Full_Ground"], ["fromInput1 {{0} B}", "in1 rgba", "fromInput2 {{0} B}",
                                                    "mappings " + ALPHA_TO_RGB]),
        ("ShaftsMatteView", "Shuffle2", ["Full_Shafts"], ["fromInput1 {{0} B}", "in1 rgba", "fromInput2 {{0} B}",
                                                          "mappings " + ALPHA_TO_RGB]),
        ("ViewOutput", "Switch", ["Layer_CloudShadow", "ShaftsOver", "ShadowView", "Full_Ground", "ShaftsMatteView"],
         ["inputs 5", "which {{parent.view}}"]),
        ("MainRGB", "Copy", ["Layer_CloudShadow", "ViewOutput"], ["inputs 2", "channels rgb"]),
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
