"""Pin Nuke's own hash of the EzCloudShafts kernel in build_group.py, after a kernel edit.

Run it with NukeX (it compiles the kernel in a BlinkScript; the GPU is fastest):

    Nuke15.1.exe --nukex -i --gpu -t python/update_kernel_hash.py

It loads blink/EzCloudShafts.blink into a BlinkScript, recompiles it, takes the 5th word of its
KernelDescription (Nuke's hash), and writes it with the source's sha256 into KERNEL_NUKE_HASH
and KERNEL_SOURCE_SHA256. Then run python/build_group.py to write the Group and gizmo.
"""

import hashlib
import os
import re
import tempfile

import nuke

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLINK = os.path.join(ROOT, "blink", "EzCloudShafts.blink")
BUILD = os.path.join(ROOT, "python", "build_group.py")

# The source exactly as build_group.py embeds it: read as text, so with \n line ends even when
# git checked the file out with \r\n. Nuke hashes the text it compiles.
with open(BLINK) as f:
    source = f.read()
source_hash = hashlib.sha256(source.encode()).hexdigest()
tmp = os.path.join(tempfile.gettempdir(), "EzCloudShafts_hash.blink")
with open(tmp, "w", newline="\n") as f:
    f.write(source)

node = nuke.nodes.BlinkScript()
node["kernelSourceFile"].setValue(tmp.replace("\\", "/"))
node["reloadKernelSourceFile"].execute()
node["recompile"].execute()
description = node["KernelDescription"].toScript().split()
nuke_hash = description[4].strip('"{}')
if not re.match(r"^[0-9a-f]{64}$", nuke_hash):
    raise RuntimeError("Unexpected KernelDescription: %r" % description[:6])
with open(BUILD) as f:
    text = f.read()
text = re.sub(r'KERNEL_SOURCE_SHA256 = "[^"]*"', 'KERNEL_SOURCE_SHA256 = "%s"' % source_hash, text, count=1)
text = re.sub(r'KERNEL_NUKE_HASH = "[^"]*"', 'KERNEL_NUKE_HASH = "%s"' % nuke_hash, text, count=1)
with open(BUILD, "w") as f:
    f.write(text)
print("KERNEL_NUKE_HASH", nuke_hash)
print("KERNEL_SOURCE_SHA256", source_hash)
