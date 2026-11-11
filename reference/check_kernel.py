"""NumPy port of blink/EzCloudShafts.blink, checked on a synthetic scene. No Nuke needed.

    python3 reference/check_kernel.py

The scene: a camera 30 m up looking towards a ridge, a cloud sheet at 1500 m whose holes are
known in world space, and a clouds "render" made by ray-casting that sheet through the same
camera (alpha = cloud). The kernel only sees the render, P and the camera; the check compares
its ground matte with the shadow worked out directly from the holes, and checks that the
shafts are brighter under the holes than under cloud. It prints a text report, no images.
"""

import numpy as np

W, H = 480, 270
SCALE = 0.1                      # scene units to metres (decimetres)
FOCAL, HAP = 35.0, 36.0
VAP = HAP * H / W
CLOUD_H = 1500.0                 # metres
SUN = np.array([0.35, 0.6, -0.72])


def look_rotation(pitch_deg):
    """Camera rotation (columns = camera x, y, z in world): looks down -Z, pitched up."""
    a = np.radians(pitch_deg)
    return np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])


R = look_rotation(4.0)
CAM_POS = np.array([0.0, 30.0, 0.0]) / SCALE     # in scene units, like Nuke's camera


def view_dirs(w, h, ovs=0):
    """World view rays of every pixel of a w x h image whose central (w-2ovs) x (h-2ovs) is the
    camera frame (overscan around it)."""
    x = (np.arange(w) + 0.5 - ovs) / (w - 2 * ovs)
    y = (np.arange(h) + 0.5 - ovs) / (h - 2 * ovs)
    u, v = np.meshgrid(x, y)
    c = np.stack([(u - 0.5) * HAP / FOCAL, (v - 0.5) * VAP / FOCAL, -np.ones_like(u)], -1)
    d = c @ R.T
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def terrain_height(x, z):
    """Ground at 0 with a ridge 3 to 8 km out, up to 600 m."""
    return 600.0 * np.exp(-((z + 5500.0) / 1500.0) ** 2) * (0.7 + 0.3 * np.cos(x / 900.0))


def hole_pattern(x, z):
    """Cloud opacity on the sheet, by world x, z: round gaps of 400 m on an 1100 m grid."""
    gx = (x / 1100.0) % 1.0 - 0.5
    gz = (z / 1100.0) % 1.0 - 0.5
    r = np.sqrt(gx ** 2 + gz ** 2) * 1100.0
    return np.clip((r - 200.0) / 40.0 + 0.5, 0.0, 1.0)


def render_scene():
    origin = CAM_POS * SCALE
    d = view_dirs(W, H)
    # March to the terrain.
    t = np.full(d.shape[:2], np.nan)
    for step in np.geomspace(5.0, 60000.0, 4000):
        p = origin + d * step
        below = (p[..., 1] <= terrain_height(p[..., 0], p[..., 2])) & np.isnan(t)
        t[below] = step
    P = origin + d * t[..., None]
    P[np.isnan(t)] = 0.0
    return P / SCALE, d          # P in scene units, 0 for sky


def render_clouds(ovs):
    """The clouds 'render': alpha where the camera sees cloud on the sheet."""
    origin = CAM_POS * SCALE
    d = view_dirs(W + 2 * ovs, H + 2 * ovs, ovs)
    t = (CLOUD_H - origin[1]) / np.maximum(d[..., 1], 1e-6)
    hit = origin + d * t[..., None]
    a = hole_pattern(hit[..., 0], hit[..., 2])
    a[d[..., 1] <= 1e-3] = 0.0
    return a


TALL_H = 2600.0


def tall_pattern(x, z):
    """A second, higher layer: a few wide clouds, by world x, z."""
    gx = (x / 4000.0) % 1.0 - 0.5
    gz = (z / 4000.0) % 1.0 - 0.5
    return np.clip((900.0 - np.sqrt(gx ** 2 + gz ** 2) * 4000.0) / 40.0 + 0.5, 0.0, 1.0)


def render_tall_clouds(ovs):
    """Clouds at 1500 m with taller ones at 2600 m in front of them where they overlap in view:
    alpha, and Planar Z in scene units."""
    origin = CAM_POS * SCALE
    d = view_dirs(W + 2 * ovs, H + 2 * ovs, ovs)
    up = np.maximum(d[..., 1], 1e-6)
    t1 = (CLOUD_H - origin[1]) / up
    t2 = (TALL_H - origin[1]) / up
    h1 = origin + d * t1[..., None]
    h2 = origin + d * t2[..., None]
    a1 = hole_pattern(h1[..., 0], h1[..., 2]) * 0.0
    a2 = tall_pattern(h2[..., 0], h2[..., 2])
    a = np.maximum(a1, a2)
    fwd = (d @ R)[..., 2] * -1.0
    z = np.where(a2 >= 0.5, t2 * fwd, 0.0) / SCALE
    a[d[..., 1] <= 1e-3] = 0.0
    return a, z


def tall_truth(surf, sun):
    hit = surf + sun * ((TALL_H - surf[:, 1]) / sun[1])[:, None]
    return tall_pattern(hit[:, 0], hit[:, 2])


def bilinear(img, x, y):
    h, w = img.shape
    x = np.clip(x - 0.5, 0, w - 1)
    y = np.clip(y - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) +
            img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


class Kernel(object):
    """The kernel's cloudOpacity / sunThrough, vectorised over points."""

    def __init__(self, clouds, ovs, density=1.0, strength=1.0, outside_lit=True, height=CLOUD_H, depth=None):
        self.clouds, self.ovs, self.height, self.depth = clouds, ovs, height, depth
        self.density, self.strength, self.outside_lit = density, strength, outside_lit

    def sun_through(self, p, sun):
        origin = CAM_POS * SCALE
        ch, cw = self.clouds.shape
        height = np.full(p.shape[:-1], float(self.height))
        above = p[..., 1] >= self.height
        passes = 3 if self.depth is not None else 1
        for i in range(passes):
            hit = p + sun * ((height - p[..., 1]) / sun[1])[..., None]
            c = (hit - origin) @ R          # transpose of the rotation
            behind = c[..., 2] > -1e-3
            u = 0.5 + (c[..., 0] / -c[..., 2]) * FOCAL / HAP
            v = 0.5 + (c[..., 1] / -c[..., 2]) * FOCAL / VAP
            x = self.ovs + u * (cw - 2 * self.ovs)
            y = self.ovs + v * (ch - 2 * self.ovs)
            out = behind | (x < 0) | (x >= cw) | (y < 0) | (y >= ch)
            a = bilinear(self.clouds, np.nan_to_num(x), np.nan_to_num(y))
            if i + 1 < passes:
                z = bilinear(self.depth, np.nan_to_num(x), np.nan_to_num(y)) * SCALE
                ux = (u - 0.5) * HAP / FOCAL
                vy = (v - 0.5) * VAP / FOCAL
                nxt = origin[1] + z * (R[1, 0] * ux + R[1, 1] * vy - R[1, 2])
                ok = (z > 0) & (a >= 0.5) & (nxt > p[..., 1] + 1.0)
                height = np.where(ok, nxt, height)
        o = np.clip(a * self.density, 0, 1)
        lit = 1.0 - self.strength * o
        lit = np.where(out, 1.0 if self.outside_lit else 1.0 - self.strength, lit)
        lit = np.where(above, 1.0, lit)
        return lit, ~out


def shafts(kernel, P, d, steps=48, density=1e-4, haze_h=1200.0, sky_distance=20000.0):
    origin = CAM_POS * SCALE
    sky = np.all(P == 0, axis=-1)
    surf = P * SCALE
    dist = np.where(sky, sky_distance, np.linalg.norm(surf - origin, axis=-1))
    up = d[..., 1] > 1e-4
    dist = np.where(up, np.minimum(dist, (CLOUD_H - origin[1]) / np.where(up, d[..., 1], 1)), dist)
    T = np.ones(dist.shape)
    lit = np.zeros(dist.shape)
    free = np.zeros(dist.shape)
    t_prev = np.zeros(dist.shape)
    for i in range(1, steps + 1):
        f = (i - 0.5) / steps
        t = dist * f * f if i < steps else dist
        mid = 0.5 * (t_prev + t)
        p = origin + d * mid[..., None]
        sigma = density * np.exp(-(p[..., 1] - origin[1]) / haze_h) * (t - t_prev)
        sc = T * (1 - np.exp(-sigma))
        l, _ = kernel.sun_through(p, SUN / np.linalg.norm(SUN))
        lit += sc * l
        free += sc
        T *= np.exp(-sigma)
        t_prev = t
    return lit, free


def main():
    sun = SUN / np.linalg.norm(SUN)
    P, d = render_scene()
    ground = ~np.all(P == 0, axis=-1)
    print("Scene %dx%d, ground %.0f%% of frame, cloud sheet %.0f m, sun %s" %
          (W, H, 100 * ground.mean(), CLOUD_H, np.round(sun, 3)))

    surf = P[ground] * SCALE
    hit = surf + sun * ((CLOUD_H - surf[:, 1]) / sun[1])[:, None]
    truth = 1.0 - hole_pattern(hit[:, 0], hit[:, 2])

    for ovs in (0, 64, 160):
        clouds = render_clouds(ovs)
        k = Kernel(clouds, ovs)
        lit, inside = k.sun_through(surf, sun)
        err = np.abs(lit - truth)[inside]
        print("overscan %3d px: gobo covers %5.1f%% of the ground, matte vs truth: mean err %.3f, "
              "within 0.1 on %5.1f%%" % (ovs, 100 * inside.mean(), err.mean(), 100 * (err < 0.1).mean()))

    # Wrong-height check: the sheet put 30% too low should be clearly worse.
    clouds = render_clouds(160)
    lit, inside = Kernel(clouds, 160, height=CLOUD_H * 0.7).sun_through(surf, sun)
    err = np.abs(lit - truth)[inside]
    print("sheet 30%% too low:  mean err %.3f, within 0.1 on %5.1f%% (should be worse)"
          % (err.mean(), 100 * (err < 0.1).mean()))

    k = Kernel(clouds, 160)
    lit, free = shafts(k, P, d)
    ratio = np.where(free > 0, lit / np.maximum(free, 1e-9), 1.0)
    print("shafts: lit share of the in-scatter %.2f to %.2f (mean %.2f); max alpha %.3f"
          % (ratio.min(), ratio.max(), ratio.mean(), lit.max()))
    # Beams: the lit share varies across the frame (not uniform) and stays in 0..1.
    print("shafts in range: %s, beam contrast (p90 - p10 of lit share): %.2f"
          % (bool((lit <= free + 1e-9).all() and (lit >= 0).all()),
             np.percentile(ratio, 90) - np.percentile(ratio, 10)))

    # Thickness: clouds at two heights, cast from a flat sheet and from their real heights.
    clouds2, depth2 = render_tall_clouds(160)
    truth2 = 1.0 - tall_truth(surf, sun)
    for name, dep in (("flat sheet", None), ("cloud depth", depth2)):
        lit, inside = Kernel(clouds2, 160, depth=dep).sun_through(surf, sun)
        err = np.abs(lit - truth2)[inside]
        print("tall clouds, %-11s: mean err %.3f, within 0.1 on %5.1f%%" % (name, err.mean(), 100 * (err < 0.1).mean()))

    # Coverage: the share of the ground whose sun ray meets the sheet inside the clouds render.
    for name, s in (("ahead", [0.0, 0.6, -0.8]), ("side", [0.8, 0.6, 0.0]), ("behind", [0.0, 0.6, 0.8]),
                    ("high", [0.1, 0.98, -0.1])):
        s = np.array(s) / np.linalg.norm(s)
        row = []
        for ovs in (0, 160, 400):
            _, inside = Kernel(render_clouds(ovs), ovs).sun_through(surf, s)
            row.append("%3d px %5.1f%%" % (ovs, 100 * inside.mean()))
        print("coverage, sun %-6s: %s" % (name, ", ".join(row)))


if __name__ == "__main__":
    main()
