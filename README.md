# EzCloudShafts

A small Nuke tool that uses the CG clouds render as a gobo for the sun. It gives you sun
shafts in the air and a cloud-shadow matte on the ground, ready to grade the environment
render's AOVs. It is a sibling of EzAtmosScatter and EzDepthHaze, and reads its sun from
either of them or from an Axis.

## Install

There's nothing to install. Import `groups/EzCloudShafts_group.nk` into a script. It's a
plain Group with the kernel and all its code on the node. `gizmos/EzCloudShafts.gizmo` is
the same node as a gizmo.

## Inputs

| Input | What to plug in |
| --- | --- |
| `env` (B pipe) | The environment render with its world position layer (P World, scene units). Pick it in **position layer**. |
| `clouds` | The flattened clouds render (rgba + depth), from the shot camera. Overscan in its bbox works as is. Overscan baked into a bigger format is assumed to sit evenly around the frame. |
| `camera` | The shot camera. |
| `atmos` | Optional: an EzAtmosScatter. Gives the sun direction, the units, and the sunlit haze colour (`atmos_haze_sun`; output Lat-long or Camera). |
| `sunclouds` | Optional: the clouds' opacity from an orthographic camera looking along the sun (see *Sun-view clouds*). |
| `suncam` | That orthographic camera. |
| `sun` | Optional: an Axis. Its world position is the direction towards the sun, and it wins over the atmos sun under **sun from: Auto**. |

## Outputs

rgba is the env render, or whatever **view** picks. Two layers are added:

| Layer | Contents |
| --- | --- |
| `shafts.rgb` | Sunlit in-scatter of the beams, coloured by the sun: an RGB colour matte for grading, or plus it over the comp. |
| `shafts.a` | The same beams without colour, 0 to 1. |
| `shafts_lit.rgb` | The share of the haze along each pixel's view that is sunlit: 1 all lit, 0 all under cloud, whatever the haze amount. Grade the env's haze (or atmos layers) up where it's 1 and down where it's 0, so the air between the beams goes dark as in nature. |
| `shafts_lit.a` | How much haze in-scatter the view ray has (0 to 1), lit or not. |
| `cloudshadow.a` | Sun visibility on the ground: 1 lit, 0 under cloud, with soft edges. Multiply the sun light group by it, or use it as a grade matte. |
| `cloudshadow.rgb` | The gobo at the ground from the sun's centre, unsoftened (the **Gobo Check** view), for lining it up. |

## Comp view and breakout

**view: Comp** (the default) is the finished look, built inside the node from its own layers:

1. **Cloud shadow.** The env loses its sun light under cloud: `env - sun light x (1 - cloudshadow.a) x cloud shadow`. With **sun light layer** on, only that light group is shadowed; off, the whole env is.
2. **Haze.** `T = (1 - shafts_lit.a) ^ (haze amount x haze falloff)`, then `land x T + haze color x (1 - T) x grade`. The grade runs from **haze in shadow** to **haze in sun** by `shafts_lit.rgb`, which darkens the air between the beams.
3. **Shafts.** `shafts.rgb x shafts` is added on top.

**layer breakout** builds the same comp next to the node as plain Shuffles, Expressions and Merges. Their values follow the node's Comp knobs, and a Difference at the bottom is black while **view** is Comp. Use it to re-comp over the full-res image or to change the recipe.

**haze color from** picks the haze colour: **Color** uses **haze color**; **EzAtmosScatter** reads the atmos's sky haze along each view ray, times **haze tint**, so the air matches the sky.

**soften (px)** blurs the shafts and shafts_lit layers to take out the sampling grain of long rays. With **edge aware** on (the default), pixels only average with neighbours at about the same distance from the camera, so beams do not bleed across ridge lines.

## Bake

**bake now** writes the shafts, shafts_lit and cloudshadow layers to EXRs for the **bake range**, and **use baked** reads them back instead of computing, so the node is cheap in the comp. **make farm bake Write** adds a Write for a farm job instead. Set **bake folder** to somewhere on the job, for example `/data/jobs/[getenv JOB]/sequences/[getenv SEQ]/shots/[getenv SHOT]/nuke/comp/ezCloudShafts/cache`; each script and node gets its own subfolder.

If a setting changes after the bake, the node computes live and its label says the bake is out of date. The Comp knobs aren't baked, so they stay live. After changing the camera or clouds upstream, bake again.

## Speed

The passes run at a reduced size and are scaled back up to the env's format.

- **viewer resolution** sets the size in the Nuke GUI (default Half).
- **render resolution** sets it for terminal and farm renders (default Full).
- **shafts at** computes the shafts smaller again (default Half), since they are soft.

At 4K, the defaults make the viewer about 4 times cheaper for the ground matte and 16 times cheaper for the shafts. **steps** and **softness samples** trade grain for speed. World position is scaled down with an impulse filter, so positions are never blended across a ridge edge.

## How it works

The clouds are a sheet at **cloud height**. From each ground point (or each step along a
view ray, for the shafts) the ray towards the sun meets the sheet. That spot is projected
through the shot camera into the clouds render, and its alpha says how much sun gets through.
**Analyze** measures the cloud height from the clouds' depth (the median of the cloudy
pixels). It also reports how much of the ground the gobo reaches.

Units are metres inside. **units to metres** turns the scene's units into metres (0.1 for
decimetres), and Analyze copies it from EzAtmosScatter.

**cast from** picks what casts the shadows. *Clouds render* is the sheet described above. *EzCloudGen volumes* reads the `cloud_sunmap` layer of an EzCloudGen plugged into `clouds` (its **sun shadow layer** and **breakout layers** on): the clouds' optical depth towards the sun from every ground point around the camera, with their mean height. Each point in the air is then shaded by the cloud that is really above it on its sun ray, so a tall cumulus casts from its whole body, clouds above or beside the frame cast too, and the air above a low deck stays lit. **cloud height**, **use cloud depth**, the gap levels and the overscan don't apply. *Auto* picks the volumes when it finds such an EzCloudGen. Both nodes must use the same sun.

**use cloud depth** casts each cloud from the height its depth says instead of one flat **cloud height**. Use it for clouds at clearly different heights, with a good `depth.Z`. Leave it off for a single layer.

**gap contrast** and **gap threshold** apply levels to the clouds' alpha before it is used, so thin or soft cloud renders give crisper beams. The defaults (1 and 0.5) change nothing, and the render itself isn't touched. Gobo Check shows the effect.

**look** and **apply look** set the haze, beams and Comp knobs to a starting point: Soft Morning, God Rays, Storm Break or Golden Hour, or Reset. Press Analyze first, so the haze suits the scene's size.

**Analyze** also finds the position and sun light layers by their usual names, sets the haze density and distances from how deep the scene is (only while those knobs are at their defaults), and warns in plain words about a sun behind or beside the camera, a high sun, short gobo coverage (naming the side to extend), an implausible cloud height or wrong units. The main warning stays in the **status** line.

### Coverage: what the camera doesn't see can't cast

The gobo only knows the clouds the camera sees. The cloud that shades a patch of ground lies
up the sun's ray from it, which is often above or beside the frame. On the synthetic test
scene (`reference/check_kernel.py`: camera 30 m up, pitched 4 degrees up, clouds at 1500 m),
this is the share of the visible ground the gobo reaches:

| Sun | No overscan | 160 px overscan | 400 px overscan |
| --- | --- | --- | --- |
| Ahead, shooting into the sun | 30% | 100% | 100% |
| To the side | 9% | 26% | 33% |
| Behind the camera | 0% | 15% | 24% |
| High (near noon) | 15% | 31% | 36% |

Ground past the gobo takes **outside frame** (Lit or Shadowed). Shots towards the sun work
best. For other shots, more overscan (especially at the top of frame) helps. A clouds pass
rendered from the sun would remove the limit, if a shot needs it.

### Sun-view clouds: no in-frame limit

For a shot where the sun isn't ahead of the camera, ask CG for one extra render:

- The clouds' opacity in alpha, from an **orthographic** camera looking along the sun (its -Z towards the ground, along the sun direction).
- Wide enough to cover the ground in shot and the air above it. Note that width in scene units.
- That camera exported too.

Plug the render into `sunclouds` and the camera into `suncam`, and set **sun view width** to the width. The gobo then reads that render everywhere, and the plate's overscan no longer matters.

## Files

| Path | What it is |
| --- | --- |
| `blink/EzCloudShafts.blink` | The kernel: gobo lookup, ground matte (output 1), shafts march (output 0). |
| `python/build_group.py` | Writes the Group and gizmo from the kernel. Plain Python, no Nuke: `python3 python/build_group.py`. |
| `python/node_layout.py`, `python/layout_hints.py` | Lay out the graph inside the Group (shared with EzDepthHaze). |
| `reference/check_kernel.py` | NumPy port of the kernel, checked on a synthetic scene against the true shadow. Prints a text report. |

Bump `VERSION` in `python/build_group.py` for each tagged release.

**After editing the kernel:** the build stops until you update `KERNEL_NUKE_HASH` and `KERNEL_SOURCE_SHA256` in `python/build_group.py`. Nuke silently cancels every render through a BlinkScript whose saved kernel hash is wrong, so the hash has to come from Nuke itself:

1. Load the .blink into a BlinkScript in NukeX and recompile.
2. Take the 5th word of its KernelDescription as `KERNEL_NUKE_HASH`.
3. Set `KERNEL_SOURCE_SHA256` to `sha256sum` of the .blink.
