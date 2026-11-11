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
| `sun` | Optional: an Axis. Its world position is the direction towards the sun, and it wins over the atmos sun under **sun from: Auto**. |

## Outputs

rgba is the env render, or whatever **view** picks. Two layers are added:

| Layer | Contents |
| --- | --- |
| `shafts.rgb` | Sunlit in-scatter of the beams, coloured by the sun: an RGB colour matte for grading, or plus it over the comp. |
| `shafts.a` | The same beams without colour, 0 to 1. |
| `cloudshadow.a` | Sun visibility on the ground: 1 lit, 0 under cloud, with soft edges. Multiply the sun light group by it, or use it as a grade matte. |
| `cloudshadow.rgb` | The gobo at the ground from the sun's centre, unsoftened (the **Gobo Check** view), for lining it up. |

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
