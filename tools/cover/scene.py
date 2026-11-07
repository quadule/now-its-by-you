"""The album cover: two seed packets leant against the edging stone of a lawn, photographed close.

    blender -b --python tools/cover/scene.py -- --preview     # 1000 px, quick, to renders/.../cover/preview.png
    blender -b --python tools/cover/scene.py -- --final       # 3000 px, 640 samples, to cover/render-3000.png
    blender -b --python tools/cover/scene.py -- --save        # only build and save cover.blend
    python3 tools/cover/send.py tools/cover/scene.py          # build it in an open Blender (blender_link.py)

Add --golf to any of these for the other setting: the same packets against a cart path's kerb, the course
behind them (a strip of rough, the fairway's mowing stripes, a green with its pin, a bunker, the tree line).

Builds everything from what face.py left in renders/review/artwork/cover/ (the printed face, its bump and
ink maps, the sheet's shape) and saves renders/review/artwork/cover.blend, which opens as the same scene.
The packet in front shows its face; the one behind it, its back and the QR. They stand on a paving stone and
lean on the kerb that edges the lawn, which runs back and up a gentle bank so grass fills the frame behind.
The light is an afternoon sun from the upper left and the sky. The camera is a 50 mm square to the front
packet's face, turned a couple of degrees off, at f/5.6.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "renders/review/artwork"
COVER = ART / "cover"
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = next((a[2:] for a in ARGS if a in ("--final", "--save", "--live", "--preview")), "preview")
GOLF = "--golf" in ARGS
SUFFIX = "-golf" if GOLF else ""
TAG = "songbird_cover" + SUFFIX.replace("-", "_")   # on everything a build makes, so a rebuild in a live
                                                    # session replaces only its own things
SCENE_NAME = "Cover golf" if GOLF else "Cover"
MADE: dict = {}                # materials this build has made, by name, to share among its objects
KINDS = ("objects", "meshes", "materials", "images", "node_groups", "lights", "cameras", "worlds", "collections",
         "textures")
SCENE = None

KERB = 0.035                   # the kerb's face, this far behind the stone's origin (m)
KERB_H = 0.065                 # and its height above the stone
ORBIT = math.radians(11.0 if GOLF else 2.0)   # the camera round to the right of square-on
GAP = 0.007                    # the joint between the paving and the kerb (m)
ROLL = math.radians(1.2)       # and not quite level
FRAME = 0.235 if GOLF else 0.205   # the frame's height at the front packet (m): wider for the course
FSTOP = 8.0 if GOLF else 5.6   # a little more of the course legible behind
EXPOSURE = -0.35
SUN = 6.5                      # W/m2; with the sky below, sunlight about five times the sky's, as in the open
SKY = 0.06
WHITE_BALANCE = 6800.0         # K: a touch warmer than daylight


def srgb(h: str, scale: float = 1.0):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(scale * (x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (1.0,)


# ---- node plumbing -------------------------------------------------------------------------------------

class Nodes:
    def __init__(self, tree):
        self.t = tree
        self.t.nodes.clear()
        self.x = 0

    def add(self, kind, **inputs):
        n = self.t.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 200
        for k, v in inputs.items():
            if hasattr(n, k) and k not in n.inputs:
                setattr(n, k, v)
            else:
                self.link_in(n, k, v)
        return n

    def link_in(self, node, name, v):
        sock = node.inputs[name]
        if isinstance(v, bpy.types.NodeSocket):
            self.t.links.new(v, sock)
        elif isinstance(v, bpy.types.Node):
            self.t.links.new(v.outputs[0], sock)
        else:
            sock.default_value = v

    def _math(self, op, a, b=0.0, clamp=False):
        n = self.t.nodes.new("ShaderNodeMath")
        n.operation, n.use_clamp = op, clamp
        n.location = (self.x, -300)
        self.x += 120
        for i, v in enumerate((a, b)):
            if isinstance(v, (bpy.types.NodeSocket, bpy.types.Node)):
                self.t.links.new(v if isinstance(v, bpy.types.NodeSocket) else v.outputs[0], n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        n = self.t.nodes.new("ShaderNodeMix")
        n.data_type, n.blend_type = "RGBA", blend
        n.location = (self.x, -500)
        self.x += 120
        for sock, v in ((n.inputs[0], fac), (n.inputs[6], a), (n.inputs[7], b)):
            if isinstance(v, (bpy.types.NodeSocket, bpy.types.Node)):
                self.t.links.new(v if isinstance(v, bpy.types.NodeSocket) else v.outputs[0], sock)
            else:
                sock.default_value = v
        return n.outputs[2]

    def ramp(self, fac, stops):
        n = self.t.nodes.new("ShaderNodeValToRGB")
        n.location = (self.x, -700)
        self.x += 200
        els = n.color_ramp.elements
        while len(els) > len(stops):
            els.remove(els[-1])
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position, el.color = pos, col
        self.t.links.new(fac if isinstance(fac, bpy.types.NodeSocket) else fac.outputs[0], n.inputs[0])
        return n.outputs[0]

    def out(self, node, name, target):
        self.t.links.new(node.outputs[name] if not isinstance(node, bpy.types.NodeSocket) else node, target)


def shared(name, make):
    if name not in MADE:
        MADE[name] = make()
    return MADE[name]


def material(name):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    return m, Nodes(m.node_tree)


def image(name, colorspace):
    img = bpy.data.images.load(str(COVER / name))
    img.colorspace_settings.name = colorspace
    return img


# ---- materials -----------------------------------------------------------------------------------------

def paper_tooth(N, coords, bump_in=None, strength=1.0):
    """The paper's own tooth, finer than the texture: a fine noise felt as bump."""
    fine = N.add("ShaderNodeTexNoise", noise_dimensions="3D", Vector=coords, Scale=9000.0, Detail=6.0,
                 Roughness=0.6)
    b = N.add("ShaderNodeBump", Strength=0.35 * strength, Distance=0.00003, Height=fine.outputs["Fac"])
    if bump_in is not None:
        N.link_in(b, "Normal", bump_in)
    return b


def face_material(side, info):
    m, N = material(f"Packet {side}")
    uv = N.add("ShaderNodeTexCoord")
    col = N.add("ShaderNodeTexImage", image=image(f"{side}-color.png", "sRGB"), interpolation="Cubic")
    ink = N.add("ShaderNodeTexImage", image=image(f"{side}-ink.png", "Non-Color"), interpolation="Linear")
    hgt = N.add("ShaderNodeTexImage", image=image(f"{side}-bump.png", "Non-Color"), interpolation="Cubic")
    for n in (col, ink, hgt):
        N.link_in(n, "Vector", uv.outputs["UV"])
    lo, hi = info[side]["bump_um"]
    press = N.add("ShaderNodeBump", Strength=1.0, Distance=(hi - lo) * 1e-6 * 1.4, Height=hgt.outputs["Color"])
    bump = paper_tooth(N, uv.outputs["Object"], press.outputs["Normal"])
    rough = N._math("ADD", N._math("MULTIPLY", ink.outputs["Color"], -0.24), 0.9)
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{
        "Base Color": col.outputs["Color"], "Roughness": rough, "Specular IOR Level": 0.32,
        "Sheen Weight": 0.3, "Sheen Roughness": 0.45, "Subsurface Weight": 0.06,
        "Subsurface Radius": (1.0, 0.75, 0.5), "Subsurface Scale": 0.0006, "Normal": bump.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def plain_paper(name, hex_col="#e9ddc4"):
    m, N = material(name)
    tc = N.add("ShaderNodeTexCoord")
    cloud = N.add("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=400.0, Detail=4.0)
    colr = N.mix(N._math("MULTIPLY", cloud.outputs["Fac"], 0.25), srgb(hex_col), srgb(hex_col, 0.9))
    bump = paper_tooth(N, tc.outputs["Object"])
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{
        "Base Color": colr, "Roughness": 0.9, "Specular IOR Level": 0.3, "Sheen Weight": 0.3,
        "Sheen Roughness": 0.45, "Normal": bump.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def concrete_material(name="Paving", kerb=False):
    """Concrete left out for years. The paving: cement and sand with the aggregate and a few pebbles showing,
    pits, weathering in broad blotches, a hairline crack or two, rosettes of pale lichen, the odd leaf's stain,
    and grime gathered toward the joint. The kerb: older and darker, green-black with algae toward its foot,
    its top edge worn pale by feet and mowers."""
    m, N = material(name)
    geo = N.add("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    sep = N.add("ShaderNodeSeparateXYZ", Vector=pos)
    broad = N.add("ShaderNodeTexNoise", Vector=pos, Scale=3.0, Detail=6.0, Roughness=0.55)
    stains = N.add("ShaderNodeTexNoise", Vector=pos, Scale=11.0, Detail=10.0, Roughness=0.62)
    mottle = N.add("ShaderNodeTexNoise", Vector=pos, Scale=70.0, Detail=8.0, Roughness=0.6)
    grit_ = N.add("ShaderNodeTexVoronoi", Vector=pos, Scale=900.0)
    stones = N.add("ShaderNodeTexVoronoi", Vector=pos, Scale=260.0)
    pebbles = N.add("ShaderNodeTexVoronoi", Vector=pos, Scale=75.0)
    pits = N.add("ShaderNodeTexVoronoi", Vector=pos, Scale=420.0)
    lichen = N.add("ShaderNodeTexVoronoi", Vector=pos, Scale=48.0)
    crack_n = N.add("ShaderNodeTexNoise", Vector=pos, Scale=5.0, Detail=3.0, Roughness=0.5)
    crack_m = N.add("ShaderNodeTexNoise", Vector=pos, Scale=2.0, Detail=1.0)
    leaf = N.add("ShaderNodeTexNoise", Vector=pos, Scale=16.0, Detail=4.0)
    fine = N.add("ShaderNodeTexNoise", Vector=pos, Scale=4000.0, Detail=3.0)
    if kerb:
        col = N.ramp(mottle.outputs["Fac"], [(0.3, srgb("#6c665c")), (0.5, srgb("#787165")), (0.7, srgb("#857d70"))])
    else:
        col = N.ramp(mottle.outputs["Fac"], [(0.3, srgb("#817a6e")), (0.5, srgb("#8e867a")), (0.7, srgb("#9c9488"))])
    col = N.mix(N._math("MULTIPLY", N._math("SUBTRACT", broad.outputs["Fac"], 0.5), 0.9, True), col, srgb("#b0a896"))
    col = N.mix(N._math("MULTIPLY", N._math("SUBTRACT", 0.5, broad.outputs["Fac"]), 0.9, True), col, srgb("#625c52"))
    agg = N._math("LESS_THAN", stones.outputs["Distance"], 0.22)
    col = N.mix(N._math("MULTIPLY", agg, 0.35), col, srgb("#a89f8f"))
    peb = N._math("MULTIPLY", N._math("LESS_THAN", pebbles.outputs["Distance"], 0.11),
                  N._math("GREATER_THAN", broad.outputs["Fac"], 0.52))
    peb_col = N.ramp(pebbles.outputs["Color"], [(0.0, srgb("#6f6558")), (0.5, srgb("#8f8577")), (0.8, srgb("#a69c8c")),
                                                (1.0, srgb("#5c554c"))])
    col = N.mix(N._math("MULTIPLY", peb, 0.25 if kerb else 0.6), col, peb_col)
    speck = N._math("LESS_THAN", grit_.outputs["Distance"], 0.12)
    col = N.mix(N._math("MULTIPLY", speck, 0.1 if kerb else 0.3), col, srgb("#b8b1a2"))
    col = N.mix(N._math("MULTIPLY", N._math("SUBTRACT", stains.outputs["Fac"], 0.5, True), 2.4, True), col,
                srgb("#4f4a42"))
    rosette = N._math("LESS_THAN", N._math("ADD", lichen.outputs["Distance"],
                                           N._math("MULTIPLY", mottle.outputs["Fac"], 0.35)), 0.26)
    col = N.mix(N._math("MULTIPLY", N._math("MULTIPLY", rosette, N._math("GREATER_THAN", stains.outputs["Fac"], 0.45)),
                        0.15 if kerb else 0.35), col, srgb("#b3af9a"))
    tannin = N._math("MULTIPLY", N._math("GREATER_THAN", leaf.outputs["Fac"], 0.68), 0.35)
    col = N.mix(tannin, col, srgb("#5e4a36"))
    crack = N._math("MULTIPLY", N._math("LESS_THAN", N._math("ABSOLUTE", N._math("SUBTRACT", crack_n.outputs["Fac"], 0.5)),
                                        0.005), N._math("GREATER_THAN", crack_m.outputs["Fac"], 0.56))
    pit = N._math("LESS_THAN", pits.outputs["Distance"], 0.06)
    dark = N._math("MAXIMUM", pit, crack)
    col = N.mix(N._math("MULTIPLY", dark, 0.8), col, srgb("#302c28"))
    if kerb:  # algae up from the foot, the top edge worn pale
        foot = N._math("POWER", N._math("SUBTRACT", 1.0, N._math("DIVIDE", sep.outputs["Z"], 0.035), True), 1.5)
        algae = N._math("MULTIPLY", foot, N._math("ADD", 0.4, N._math("MULTIPLY", stains.outputs["Fac"], 0.8)))
        col = N.mix(N._math("MINIMUM", algae, 0.85), col, srgb("#2e3321"))
        worn = N._math("GREATER_THAN", sep.outputs["Z"], KERB_H - 0.004)
        col = N.mix(N._math("MULTIPLY", worn, 0.35), col, srgb("#b4ad9e"))
    else:     # grime and a green tinge gathered toward the joint with the kerb
        near = N._math("EXPONENT", N._math("DIVIDE", N._math("SUBTRACT", sep.outputs["Y"], KERB), 0.018))
        col = N.mix(N._math("MULTIPLY", N._math("MINIMUM", near, 1.0), 0.55), col, srgb("#3f3e30"))
    h = N._math("ADD", N._math("MULTIPLY", mottle.outputs["Fac"], 0.4),
                N._math("ADD", N._math("ADD", N._math("MULTIPLY", agg, 0.25), N._math("MULTIPLY", peb, 0.5)),
                        N._math("SUBTRACT", N._math("MULTIPLY", fine.outputs["Fac"], 0.3), N._math("MULTIPLY", dark, 1.2))))
    bump = N.add("ShaderNodeBump", Strength=0.6, Distance=0.0005, Height=h)
    rough = N._math("ADD", 0.8, N._math("MULTIPLY", agg, 0.1))
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": rough, "Specular IOR Level": 0.3,
                                                 "Normal": bump.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def soil_material():
    m, N = material("Lawn thatch")
    tc = N.add("ShaderNodeTexCoord")
    n = N.add("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=80.0, Detail=6.0)
    col = N.ramp(n.outputs["Fac"], [(0.3, srgb("#2c2a17")), (0.7, srgb("#4a4a25"))])
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.95})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def grass_material():
    """Blades of a summer lawn: greens that vary blade to blade, some sun-bleached, lit through as well as on;
    little shine, so the blurred lawn holds no glints."""
    m, N = material("Grass")
    info = N.add("ShaderNodeObjectInfo")
    geo = N.add("ShaderNodeNewGeometry")
    patch = N.add("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=2.5, Detail=3.0)
    pick = N._math("ADD", N._math("MULTIPLY", info.outputs["Random"], 0.7), N._math("MULTIPLY", patch.outputs["Fac"], 0.3))
    col = N.ramp(pick, [(0.0, srgb("#4d5e2f")), (0.35, srgb("#63753a")), (0.65, srgb("#7c8a44")),
                        (0.88, srgb("#9a9a58")), (1.0, srgb("#b3a877"))])
    light = N.add("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=0.8, Detail=2.0)
    col = N.mix(N._math("MULTIPLY", N._math("SUBTRACT", light.outputs["Fac"], 0.45, True), 1.6, True), col,
                srgb("#a3a864"))
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.55, "Specular IOR Level": 0.25})
    tr = N.add("ShaderNodeBsdfTranslucent", Color=col)
    mixs = N.add("ShaderNodeMixShader", Fac=0.3)
    N.t.links.new(bsdf.outputs[0], mixs.inputs[1])
    N.t.links.new(tr.outputs[0], mixs.inputs[2])
    o = N.add("ShaderNodeOutputMaterial")
    N.out(mixs, "Shader", o.inputs["Surface"])
    return m


def blade(name, length, width, bend, fold=0.25, segs=8, mat="Grass"):
    """One blade: a strip that narrows to a point, curving over, creased down its middle."""
    verts, faces = [], []
    for i in range(segs + 1):
        t = i / segs
        w = max(width * (1 - t) ** 0.8, 0.00015)
        y, z = bend * length * t * t, length * t * (1 - 0.25 * bend * t)
        verts += [(-w / 2, y + fold * w, z), (0.0, y, z), (w / 2, y + fold * w, z)]
    for i in range(segs):
        r0, r1 = 3 * i, 3 * (i + 1)
        faces += [(r0, r0 + 1, r1 + 1, r1), (r0 + 1, r0 + 2, r1 + 2, r1 + 1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("use_smooth", [True] * len(faces))
    me.materials.append(shared(mat, {"Turf": turf_material, "Dry grass": dry_grass_material}.get(mat, grass_material)))
    ob = bpy.data.objects.new(name, me)
    ob["length"] = length
    return ob


def lawn(name, x0, x1, y0, y1, density, blades, seed_no, z0=-0.012, clear=(), bank=True, ground=None):
    """Ground from y0 to y1, flat and then (if bank) rising as a bank, sown with blades by geometry nodes."""
    nx, ny = 36, 48
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    X, Y = np.meshgrid(xs, ys)
    Z = z0 + (0.12 * np.clip(Y - 0.5, 0, None) ** 1.4 if bank else 0.0 * Y)
    verts = np.stack([X, Y, Z], -1).reshape(-1, 3)
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(ny - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces)
    me.materials.append(ground or shared("Lawn thatch", soil_material))
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)

    ng = bpy.data.node_groups.new(f"{name} blades", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nd, ln = ng.nodes, ng.links
    gi, go = nd.new("NodeGroupInput"), nd.new("NodeGroupOutput")
    dist = nd.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = density
    dist.inputs["Seed"].default_value = seed_no
    inst = nd.new("GeometryNodeInstanceOnPoints")
    coll = nd.new("GeometryNodeCollectionInfo")
    coll.inputs["Collection"].default_value = blades
    coll.inputs["Separate Children"].default_value = True
    coll.inputs["Reset Children"].default_value = True
    pick = nd.new("FunctionNodeRandomValue")
    pick.data_type = "INT"
    pick.inputs["Min"].default_value, pick.inputs["Max"].default_value = 0, len(blades.objects) - 1
    rot = nd.new("FunctionNodeRandomValue")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Min"].default_value = (-0.6, -0.6, 0.0)
    rot.inputs["Max"].default_value = (0.6, 0.6, 6.2832)
    rot.inputs["Seed"].default_value = 3
    scl = nd.new("FunctionNodeRandomValue")
    scl.data_type = "FLOAT"
    scl.inputs["Min"].default_value, scl.inputs["Max"].default_value = 0.65, 1.35
    scl.inputs["Seed"].default_value = 7
    join = nd.new("GeometryNodeJoinGeometry")
    ln.new(gi.outputs[0], dist.inputs["Mesh"])
    ln.new(dist.outputs["Points"], inst.inputs["Points"])
    ln.new(coll.outputs[0], inst.inputs["Instance"])
    inst.inputs["Pick Instance"].default_value = True
    ln.new(pick.outputs[0], inst.inputs["Instance Index"])
    ln.new(rot.outputs[0], inst.inputs["Rotation"])
    if clear:
        # no blade long enough to reach a packet: nearer them, the grass is shorter, as if pressed
        targets = nd.new("GeometryNodeJoinGeometry")
        for ob_ in clear:
            oi = nd.new("GeometryNodeObjectInfo")
            oi.transform_space = "RELATIVE"
            oi.inputs["Object"].default_value = ob_
            ln.new(oi.outputs["Geometry"], targets.inputs[0])
        prox = nd.new("GeometryNodeProximity")
        prox.target_element = "FACES"
        ln.new(targets.outputs[0], prox.inputs[0])
        reach = max(o.get("length", 0.1) for o in blades.objects) * 1.05
        cap = nd.new("ShaderNodeMath")
        cap.operation = "DIVIDE"
        ln.new(prox.outputs["Distance"], cap.inputs[0])
        cap.inputs[1].default_value = reach
        least = nd.new("ShaderNodeMath")
        least.operation = "MINIMUM"
        ln.new(scl.outputs[0], least.inputs[0])
        ln.new(cap.outputs[0], least.inputs[1])
        ln.new(least.outputs[0], inst.inputs["Scale"])
    else:
        ln.new(scl.outputs[0], inst.inputs["Scale"])
    ln.new(gi.outputs[0], join.inputs[0])
    ln.new(inst.outputs[0], join.inputs[0])
    ln.new(join.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("Blades", "NODES")
    mod.node_group = ng
    return ob


def pebble_mesh(name, flat=1.0, seed_no=0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    r = np.random.default_rng(seed_no)
    for v in bm.verts:
        v.co *= 0.75 + 0.45 * r.random()
        v.co.z *= flat
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    return me


def clipping_mesh(name):
    """A dry cut end of grass: a short flat strip with a little twist, lying down."""
    verts, faces = [], []
    n = 6
    for i in range(n + 1):
        t = i / n
        w = 0.08 * (1 - 0.3 * t)
        x, z = t - 0.5, 0.05 * math.sin(math.pi * t)
        verts += [(x, -w / 2, z), (x, w / 2, z + 0.02 * t)]
    for i in range(n):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    return me


def scatter_material(name, stops, rough=0.8):
    m, N = material(name)
    info = N.add("ShaderNodeObjectInfo")
    col = N.ramp(info.outputs["Random"], stops)
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": rough})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def scatter(name, x0, x1, y0, y1, density, sizes, mesh, patch=40.0, lie=False, seed_no=0, z=0.0):
    """Small things strewn on the stone by geometry nodes: more of them toward the joint (y1), and gathered
    in patches, the way sand and grit lie where water and brooms have left them."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)
    ng = bpy.data.node_groups.new(f"{name} scatter", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nd, ln = ng.nodes, ng.links
    gi, go = nd.new("NodeGroupInput"), nd.new("NodeGroupOutput")
    pos = nd.new("GeometryNodeInputPosition")
    sep = nd.new("ShaderNodeSeparateXYZ")
    near = nd.new("ShaderNodeMapRange")
    near.inputs["From Min"].default_value, near.inputs["From Max"].default_value = y0, y1
    near.inputs["To Min"].default_value, near.inputs["To Max"].default_value = 0.1, 1.0
    clumps = nd.new("ShaderNodeTexNoise")
    clumps.inputs["Scale"].default_value = patch
    clumps.inputs["Detail"].default_value = 3.0
    shape = nd.new("ShaderNodeMapRange")
    shape.inputs["From Min"].default_value, shape.inputs["From Max"].default_value = 0.42, 0.68
    both = nd.new("ShaderNodeMath")
    both.operation = "MULTIPLY"
    dist = nd.new("GeometryNodeDistributePointsOnFaces")
    dist.distribute_method = "POISSON"
    dist.inputs["Distance Min"].default_value = 0.0
    dist.inputs["Density Max"].default_value = density
    dist.inputs["Seed"].default_value = seed_no
    inst = nd.new("GeometryNodeInstanceOnPoints")
    oi = nd.new("GeometryNodeObjectInfo")
    oi.inputs["Object"].default_value = bpy.data.objects.new(f"{name} piece", mesh)   # only instanced
    scl = nd.new("FunctionNodeRandomValue")
    scl.data_type = "FLOAT"
    scl.inputs["Min"].default_value, scl.inputs["Max"].default_value = sizes
    rot = nd.new("FunctionNodeRandomValue")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Min"].default_value = (0.0, 0.0, 0.0)
    rot.inputs["Max"].default_value = (0.25, 0.25, 6.28) if lie else (6.28, 6.28, 6.28)
    ln.new(pos.outputs[0], sep.inputs[0])
    ln.new(sep.outputs["Y"], near.inputs["Value"])
    ln.new(clumps.outputs["Fac"], shape.inputs["Value"])
    ln.new(near.outputs[0], both.inputs[0])
    ln.new(shape.outputs[0], both.inputs[1])
    ln.new(gi.outputs[0], dist.inputs["Mesh"])
    ln.new(both.outputs[0], dist.inputs["Density Factor"])
    ln.new(dist.outputs["Points"], inst.inputs["Points"])
    ln.new(oi.outputs["Geometry"], inst.inputs["Instance"])
    ln.new(scl.outputs[0], inst.inputs["Scale"])
    ln.new(rot.outputs[0], inst.inputs["Rotation"])
    ln.new(inst.outputs[0], go.inputs[0])
    ob.modifiers.new("Scatter", "NODES").node_group = ng
    return ob


def stripes(N, pos, width=1.6, angle=0.5):
    """A fairway's mowing stripes: alternate passes of the mower lay the blades toward and away from us."""
    sep = N.add("ShaderNodeSeparateXYZ", Vector=pos)
    u = N._math("ADD", N._math("MULTIPLY", sep.outputs["X"], math.cos(angle)),
                N._math("MULTIPLY", sep.outputs["Y"], math.sin(angle)))
    wave = N._math("SINE", N._math("MULTIPLY", u, math.pi / width))
    return N._math("MULTIPLY", N._math("ADD", N._math("MULTIPLY", wave, 4.0), 0.5), 1.0, True)


def turf_material():
    """Close-mown turf: fine, even, well-watered blades, striped by the mower."""
    m, N = material("Turf")
    info = N.add("ShaderNodeObjectInfo")
    geo = N.add("ShaderNodeNewGeometry")
    patch = N.add("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=3.0, Detail=3.0)
    pick = N._math("ADD", N._math("MULTIPLY", info.outputs["Random"], 0.6), N._math("MULTIPLY", patch.outputs["Fac"], 0.4))
    col = N.ramp(pick, [(0.0, srgb("#46612a")), (0.5, srgb("#587636")), (0.85, srgb("#6c8a40")), (1.0, srgb("#8e9657"))])
    col = N.mix(N._math("MULTIPLY", stripes(N, geo.outputs["Position"]), 0.35), col, srgb("#94ac5c"))
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.55, "Specular IOR Level": 0.25})
    tr = N.add("ShaderNodeBsdfTranslucent", Color=col)
    mixs = N.add("ShaderNodeMixShader", Fac=0.3)
    N.t.links.new(bsdf.outputs[0], mixs.inputs[1])
    N.t.links.new(tr.outputs[0], mixs.inputs[2])
    o = N.add("ShaderNodeOutputMaterial")
    N.out(mixs, "Shader", o.inputs["Surface"])
    return m


def fairway_material(green=False):
    """Turf too far off to see blade by blade: its colour, and the mower's stripes, one pass lighter than the
    next. The green is finer and cut in narrower stripes."""
    m, N = material("Green" if green else "Fairway")
    geo = N.add("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    n = N.add("ShaderNodeTexNoise", Vector=pos, Scale=1.2 if not green else 3.0, Detail=6.0)
    fine = N.add("ShaderNodeTexNoise", Vector=pos, Scale=300.0, Detail=2.0)
    band = stripes(N, pos, 0.9 if green else 1.7, -0.4 if green else 0.55)
    dark = N.ramp(n.outputs["Fac"], [(0.3, srgb("#3f5a24")), (0.7, srgb("#4b6a2b"))])
    light = N.ramp(n.outputs["Fac"], [(0.3, srgb("#65853a")), (0.7, srgb("#739444"))])
    col = N.mix(band, dark, light)
    bump = N.add("ShaderNodeBump", Strength=0.3, Distance=0.01, Height=fine.outputs["Fac"])
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.8, "Specular IOR Level": 0.2,
                                                 "Normal": bump.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def plain_material(name, hex_col, rough=0.9, noise_scale=0.0, dark="#000000", spec=0.5):
    m, N = material(name)
    col = srgb(hex_col)
    if noise_scale:
        geo = N.add("ShaderNodeNewGeometry")
        n = N.add("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=noise_scale, Detail=8.0)
        col = N.mix(N._math("MULTIPLY", n.outputs["Fac"], 0.8), srgb(hex_col), srgb(dark))
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": rough, "Specular IOR Level": spec})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def mesh_object(name, verts, faces, mat, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if smooth:
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)
    return ob


def disc(name, cx, cy, rx, ry, z, mat, rim=0.0, n=64, rings=6, rng=None):
    """A flattened, slightly irregular disc of ground: a green or a bunker, raised (or sunk) by rim at its
    middle."""
    rng = rng or np.random.default_rng(0)
    wob = 1 + 0.08 * np.convolve(rng.normal(0, 1, n + 8), np.ones(9) / 9, "valid")[:n]
    verts, faces = [(cx, cy, z + rim)], []
    for r in range(1, rings + 1):
        t = r / rings
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append((cx + rx * t * wob[k] * math.cos(a), cy + ry * t * wob[k] * math.sin(a),
                          z + rim * (1 - t * t)))
    for k in range(n):
        faces.append((0, 1 + k, 1 + (k + 1) % n))
    for r in range(1, rings):
        for k in range(n):
            a0, a1 = 1 + (r - 1) * n + k, 1 + (r - 1) * n + (k + 1) % n
            faces.append((a0, a0 + n, a1 + n, a1))
    return mesh_object(name, verts, faces, mat, smooth=True)


def rise(y):
    """The hole plays uphill: flat by the path, then the fairway climbs toward the green."""
    t = np.clip((np.asarray(y, float) - 3.0) / 27.0, 0, 1)
    return 2.2 * t * t * (3 - 2 * t)


def golf_course(front, rear, rng):
    """Behind the cart path's kerb: a strip of rough, then the fairway in its mower's stripes climbing to a green
    on the crest with the pin in it, a bunker short of it, and trees beyond, softened by the distance."""
    z0 = KERB_H - 0.006
    rough_blades = bpy.data.collections.new("Rough blades")
    turf_blades = bpy.data.collections.new("Turf blades")
    for i in range(6):
        rough_blades.objects.link(blade(f"Rough blade {i}", rng.uniform(0.025, 0.05), rng.uniform(0.0022, 0.0034),
                                        rng.uniform(0.2, 0.6), mat="Turf"))
        turf_blades.objects.link(blade(f"Turf blade {i}", rng.uniform(0.009, 0.016), rng.uniform(0.0016, 0.0024),
                                       rng.uniform(0.05, 0.3), mat="Turf"))
    fair = shared("Fairway", fairway_material)
    # a ball that came to rest in the rough, beside the packets
    lawn("Rough", -0.9, 0.9, KERB + 0.058, KERB + 0.34, 70000, rough_blades, 1, z0=z0, clear=(front, rear),
         bank=False, ground=fair)
    lawn("Fairway near", -1.8, 1.8, KERB + 0.34, 2.8, 60000, turf_blades, 2, z0=z0, bank=False, ground=fair)
    # beyond, too far to see blade by blade: climbing, and rolling a little
    nx, ny = 80, 120
    X, Y = np.meshgrid(np.linspace(-90, 90, nx), np.linspace(2.7, 140, ny))
    Z = z0 + rise(Y) + 0.18 * np.sin(X / 7.0) * np.sin(Y / 9.0) * np.clip((Y - 2.7) / 6, 0, 1)
    verts = np.stack([X, Y, Z], -1).reshape(-1, 3)
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    mesh_object("Fairway", verts, faces, fair, smooth=True)

    def ground(x, y):
        return z0 + float(rise(y)) + 0.18 * math.sin(x / 7.0) * math.sin(y / 9.0)

    # the green on the crest, to the left, with its pin; a bunker short of it to the right
    gx, gy = -3.2, 31.0
    disc("Green", gx, gy, 8.0, 6.0, ground(gx, gy) + 0.02, fairway_material(green=True), rim=0.3, rng=rng)
    bx, by = gx + 6.5, gy - 6.5
    disc("Bunker", bx, by, 3.6, 1.9, ground(bx, by) + 0.03, plain_material("Bunker sand", "#cdbb95", 0.95, 40.0, "#b3a17c"),
         rim=-0.2, rng=rng)
    pz = ground(gx, gy) + 0.3
    me = bpy.data.meshes.new("Pin")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.008, radius2=0.008, depth=2.2)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(plain_material("Pin", "#ece8dc", 0.4))
    pin = bpy.data.objects.new("Pin", me)
    SCENE.collection.objects.link(pin)
    px = gx + 1.2
    pin.location = (px, gy, pz + 1.1)
    # the flag: the packet's own red, lifting a little in the breeze
    fverts, ffaces, nu, nv = [], [], 12, 6
    for j in range(nv + 1):
        for i in range(nu + 1):
            u, v = i / nu, j / nv
            fverts.append((px + 0.5 * u * math.cos(0.35), gy + 0.5 * u * math.sin(0.35) + 0.04 * math.sin(3 * u),
                           pz + 2.2 - 0.36 * v - 0.05 * u * u))
    for j in range(nv):
        for i in range(nu):
            a_ = j * (nu + 1) + i
            ffaces.append((a_, a_ + 1, a_ + nu + 2, a_ + nu + 1))
    mesh_object("Flag", fverts, ffaces, plain_material("Flag", "#b8432e", 0.8), smooth=True)
    # the tree line beyond the green: broadleaf trees in no particular order, their crowns clumped and
    # uneven, each a slightly different green, greyed a little by the air between
    m, N = material("Far leaves")
    info_ = N.add("ShaderNodeObjectInfo")
    geo = N.add("ShaderNodeNewGeometry")
    clump = N.add("ShaderNodeTexNoise", Vector=geo.outputs["Position"], Scale=0.9, Detail=4.0)
    pick = N._math("ADD", N._math("MULTIPLY", info_.outputs["Random"], 0.6), N._math("MULTIPLY", clump.outputs["Fac"], 0.4))
    col = N.ramp(pick, [(0.0, srgb("#26351d")), (0.4, srgb("#34462a")), (0.75, srgb("#46562f")), (1.0, srgb("#5b6236"))])
    col = N.mix(0.22, col, srgb("#8d9486"))
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.95, "Specular IOR Level": 0.0})
    tr = N.add("ShaderNodeBsdfTranslucent", Color=col)
    mix_ = N.add("ShaderNodeMixShader", Fac=0.2)
    N.t.links.new(bsdf.outputs[0], mix_.inputs[1])
    N.t.links.new(tr.outputs[0], mix_.inputs[2])
    o = N.add("ShaderNodeOutputMaterial")
    N.out(mix_, "Shader", o.inputs["Surface"])
    bark = plain_material("Bark", "#3b342c", 0.95, spec=0.0)
    kinds = [tree_mesh(f"Tree {i}", rng, m, bark) for i in range(6)]
    for k in range(95):
        x = rng.uniform(-75, 75)
        y = rng.uniform(52, 84)
        t = bpy.data.objects.new("Tree", kinds[int(rng.integers(0, len(kinds)))])
        SCENE.collection.objects.link(t)
        t.location = (x, y, ground(x, 30.0) - 0.3)
        t.rotation_euler = (0, 0, rng.uniform(0, 2 * math.pi))
        t.scale = (rng.uniform(0.8, 1.3),) * 3


def concrete_maps(name, info):
    """The material for a surface made by concrete.py: its colour and roughness, and its height as bump
    for what the displaced mesh is too coarse to carry."""
    m, N = material(f"{name.title()} concrete")
    uv = N.add("ShaderNodeTexCoord")
    col = N.add("ShaderNodeTexImage", image=image(f"{name}-color.png", "sRGB"), interpolation="Cubic")
    rough = N.add("ShaderNodeTexImage", image=image(f"{name}-rough.png", "Non-Color"))
    hgt = N.add("ShaderNodeTexImage", image=image(f"{name}-height.png", "Non-Color"), interpolation="Cubic")
    for n in (col, rough, hgt):
        N.link_in(n, "Vector", uv.outputs["UV"])
    lo, hi = info[name]["height_range_mm"]
    bump = N.add("ShaderNodeBump", Strength=0.35, Distance=(hi - lo) / 1000 * 0.2, Height=hgt.outputs["Color"])
    grain = N.add("ShaderNodeTexNoise", Vector=uv.outputs["Object"], Scale=7000.0, Detail=2.0, Roughness=0.7)
    sandy = N.add("ShaderNodeBump", Strength=0.7, Distance=0.00006, Height=grain.outputs["Fac"],
                  Normal=bump.outputs["Normal"])
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col.outputs["Color"], "Roughness": rough.outputs["Color"],
                                                 "Specular IOR Level": 0.18, "Normal": sandy.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def profile(parts, step):
    """A cross-section as (y, z) points, from straight runs and quarter-round arrises:
    ("line", (y0, z0), (y1, z1)) or ("arc", (cy, cz), r, a0, a1) with angles in degrees."""
    pts = []
    for part in parts:
        if part[0] == "line":
            (y0, z0), (y1, z1) = part[1], part[2]
            n = max(2, int(math.hypot(y1 - y0, z1 - z0) / step) + 1)
            seg = [(y0 + (y1 - y0) * t, z0 + (z1 - z0) * t) for t in np.linspace(0, 1, n)]
        else:
            (cy, cz), r, a0, a1 = part[1], part[2], math.radians(part[3]), math.radians(part[4])
            n = max(3, int(abs(a1 - a0) * r / (step * 0.5)) + 1)
            seg = [(cy + r * math.cos(a), cz + r * math.sin(a)) for a in np.linspace(a0, a1, n)]
        pts += seg[1:] if pts else seg
    pts = np.array(pts)
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    return pts, s


def profiled(name, xs, prof, arc, v_of_s, u_width, maps, height_name, info):
    """A length of concrete: the cross-section swept along x, its surface displaced by concrete.py's height map
    (so the aggregate stands proud and casts its own small shadows) and textured with its colour."""
    ny = len(prof)
    X = np.repeat(xs[None, :], ny, 0)
    Y = np.repeat(prof[:, 0:1], len(xs), 1)
    Z = np.repeat(prof[:, 1:2], len(xs), 1)
    verts = np.stack([X, Y, Z], -1).reshape(-1, 3)
    nx = len(xs)
    jj, ii = np.meshgrid(np.arange(ny - 1), np.arange(nx - 1), indexing="ij")
    a = (jj * nx + ii).ravel()
    quads = np.stack([a, a + 1, a + nx + 1, a + nx], 1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    me.update(calc_edges=True)
    U = np.repeat((xs / u_width)[None, :], ny, 0)
    V = np.repeat(v_of_s(arc)[:, None], nx, 1)
    uvv = np.stack([U, V], -1).reshape(-1, 2)
    me.uv_layers.new(name="UV").data.foreach_set("uv", uvv[quads.ravel()].astype(np.float32).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    me.materials.append(maps)
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)
    tex = bpy.data.textures.new(f"{name} relief", "IMAGE")
    tex.image = image(f"{height_name}-height.png", "Non-Color")
    tex.extension = "REPEAT"
    lo, hi = info[height_name]["height_range_mm"]
    d = ob.modifiers.new("Relief", "DISPLACE")
    d.texture, d.texture_coords, d.direction = tex, "UV", "NORMAL"
    d.strength, d.mid_level = (hi - lo) / 1000, -lo / (hi - lo)
    return ob


def moss_material():
    m, N = material("Moss")
    info = N.add("ShaderNodeObjectInfo")
    col = N.ramp(info.outputs["Random"], [(0.0, srgb("#3d4a1f")), (0.5, srgb("#5a6b28")), (0.85, srgb("#7b8a36")),
                                         (1.0, srgb("#8f8a4a"))])
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.85, "Sheen Weight": 0.8,
                                                 "Sheen Roughness": 0.3, "Specular IOR Level": 0.2})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def dry_grass_material():
    m, N = material("Dry grass")
    info = N.add("ShaderNodeObjectInfo")
    col = N.ramp(info.outputs["Random"], [(0.0, srgb("#6f5f3c")), (0.6, srgb("#9b8a5c")), (1.0, srgb("#b9a878"))])
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.7})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def tuft(cx, blades, dry, rng, packs):
    """A clump of grass come up in the joint: a crowded crown of short blades, longer ones fanning out and
    flopping over the paving (never into the kerb), a few dead and brown; each kept short of the packets."""
    for k in range(int(rng.integers(16, 26))):
        dead = rng.random() < 0.18
        pool = dry if dead else blades
        src = pool[int(rng.integers(0, len(pool)))]
        root = Vector((cx + rng.normal(0, 0.0035), KERB - GAP / 2 + rng.uniform(-0.0025, 0.0025), -0.0045))
        crown = rng.random() < 0.35
        size = rng.uniform(0.12, 0.25) if crown else rng.uniform(0.3, 0.75)
        room = min(t.find_nearest(root)[3] for t in packs)
        size = min(size, room / (src["length"] * 1.05))
        tilt = rng.uniform(0.05, 0.35) if crown else rng.uniform(0.25, 1.05)
        toward = rng.uniform(-1.9, 1.9)                   # about -y: out over the paving, or along the joint
        b = bpy.data.objects.new("Joint grass", src.data)
        SCENE.collection.objects.link(b)
        b.location = root
        b.rotation_euler = (Matrix.Rotation(toward, 4, "Z") @ Matrix.Rotation(tilt, 4, "X")
                            @ Matrix.Rotation(math.pi, 4, "Z")).to_euler()
        b.scale = (size,) * 3


def golf_ball_material():
    """A ball that has been played: white, a soft sheen, its dimples, a green smudge where it rolled."""
    m, N = material("Golf ball")
    tc = N.add("ShaderNodeTexCoord")
    vor = N.add("ShaderNodeTexVoronoi", Vector=tc.outputs["Object"], Scale=260.0)
    dimple = N._math("POWER", N._math("MULTIPLY", vor.outputs["Distance"], 1.9, True), 0.5)
    smudge = N.add("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=60.0, Detail=4.0)
    stain = N._math("MULTIPLY", N._math("SUBTRACT", smudge.outputs["Fac"], 0.58, True), 3.0, True)
    col = N.mix(stain, srgb("#f2f0ea"), srgb("#8e9a62"))
    bump = N.add("ShaderNodeBump", Strength=0.9, Distance=0.0004, Height=dimple)
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.35, "Coat Weight": 0.5,
                                                 "Coat Roughness": 0.2, "Normal": bump.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


def golf_ball(loc):
    me = bpy.data.meshes.new("Golf ball")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=0.02134)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    me.materials.append(golf_ball_material())
    ob = bpy.data.objects.new("Golf ball", me)
    SCENE.collection.objects.link(ob)
    ob.location = loc
    return ob


def tree_mesh(name, rng, leaf, bark):
    """A broadleaf tree as it looks from a long way off: a trunk and a crown of many irregular clumps."""
    bm = bmesh.new()
    th = rng.uniform(2.5, 4.0)
    tr = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=rng.uniform(0.25, 0.4),
                               radius2=0.18, depth=th + 3)
    for v in tr["verts"]:
        v.co.z += (th + 3) / 2
    for f in bm.faces:
        f.material_index = 1
    w, h = rng.uniform(5.0, 8.5), rng.uniform(6.0, 10.0)
    for _ in range(int(rng.integers(22, 36))):
        u = rng.normal(0, 1, 3)
        u /= np.linalg.norm(u)
        rr = rng.random() ** 0.4
        c = Vector((u[0] * w / 2 * rr, u[1] * w / 2 * rr, th + h / 2 + u[2] * h / 2 * rr))
        res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rng.uniform(0.8, 1.9))
        for v in res["verts"]:
            v.co = v.co + c + Vector(rng.normal(0, 0.18, 3))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(leaf)
    me.materials.append(bark)
    return me


def seed_material():
    m, N = material("Seed")
    tc = N.add("ShaderNodeTexCoord")
    sep = N.add("ShaderNodeSeparateXYZ", Vector=tc.outputs["Object"])
    # ribs running the seed's length
    ang = N.add("ShaderNodeMath", operation="ARCTAN2")
    N.t.links.new(sep.outputs["Z"], ang.inputs[0])
    N.t.links.new(sep.outputs["Y"], ang.inputs[1])
    ribs = N._math("SINE", N._math("MULTIPLY", ang.outputs[0], 7.0))
    n = N.add("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=2500.0, Detail=4.0)
    col = N.mix(N._math("ADD", N._math("MULTIPLY", ribs, 0.25), n.outputs["Fac"]), srgb("#3b2413"), srgb("#8a6440"))
    bump = N.add("ShaderNodeBump", Strength=0.6, Distance=0.00004, Height=ribs)
    bsdf = N.add("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.5, "Sheen Weight": 0.2,
                                                 "Normal": bump.outputs["Normal"]})
    o = N.add("ShaderNodeOutputMaterial")
    N.out(bsdf, "BSDF", o.inputs["Surface"])
    return m


# ---- objects -------------------------------------------------------------------------------------------

def packet(name, side, info, lean, yaw, x):
    """A packet from its sheet, the printed side toward us, leant back and turned, at x across."""
    P = np.load(COVER / f"{side}-sheet.npy").astype(np.float64)
    ny, nx, _ = P.shape
    P[..., 0] -= info["width_mm"] / 2000
    verts = P.reshape(-1, 3)
    ii, jj = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1))
    a = (jj * nx + ii).ravel()
    quads = np.stack([a, a + 1, a + nx + 1, a + nx], 1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    me.update(calc_edges=True)
    u, v = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny))
    uvv = np.stack([u, v], -1).reshape(-1, 2)
    uvl = me.uv_layers.new(name="Face")
    uvl.data.foreach_set("uv", uvv[quads.ravel()].astype(np.float32).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    me.validate()
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)
    back = shared("Packet paper", lambda: plain_paper("Packet paper"))
    edge = shared("Packet edge", lambda: plain_paper("Packet edge", "#e3d6bb"))
    for mat in (face_material(side, info), back, edge):
        me.materials.append(mat)
    sol = ob.modifiers.new("Two sheets of paper", "SOLIDIFY")
    sol.thickness, sol.offset, sol.use_even_offset = 0.00035, -1.0, True
    sol.use_rim, sol.material_offset, sol.material_offset_rim = True, 1, 2
    ob.rotation_euler = Euler((math.pi / 2 - lean, 0, yaw), "XYZ")
    ob.location = (x, -0.05, 0.0)
    return ob


def world_points(ob, every=1):
    vl = SCENE.view_layers[0]
    vl.update()
    ev = ob.evaluated_get(vl.depsgraph)
    em = ev.to_mesh()
    co = np.empty(len(em.vertices) * 3)
    em.vertices.foreach_get("co", co)
    polys = [tuple(p.vertices) for p in em.polygons] if every == 0 else None
    ev.to_mesh_clear()
    mw = np.array(ob.matrix_world)
    pts = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    return (pts, polys) if every == 0 else pts[::every]


def world_tree(ob):
    pts, polys = world_points(ob, every=0)
    return BVHTree.FromPolygons([tuple(p) for p in pts], polys)


def stand(ob):
    """Its lowest point on the stone."""
    ob.location.z -= world_points(ob, 7)[:, 2].min() - 0.00002


def lean_on(ob, supports, gap=0.00015):
    """Slide it straight back until it touches the first of its supports: that is what holds it up."""
    trees = [world_tree(s) for s in supports]
    best = 1.0
    for p in world_points(ob, 23):
        for t in trees:
            hit = t.ray_cast(Vector(p), Vector((0, 1, 0)), 0.3)
            if hit[0] is not None:
                best = min(best, hit[3])
    ob.location.y += best - gap
    return best


def seed(name, loc, yaw, tilt=0.0, length=0.0044):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    SCENE.collection.objects.link(ob)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    x = co[:, 0]
    taper = 1 - 0.38 * np.clip(x, 0, 1) ** 1.5 + 0.05 * np.clip(-x, 0, 1)
    co[:, 0] *= length / 2
    co[:, 1] *= length * 0.17 * taper
    co[:, 2] *= length * 0.13 * taper
    co[:, 2] += 0.00012 * (x**2 - 1) * -0.5      # a slight curve along the length
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    ob.location = (loc[0], loc[1], length * 0.13 - 0.00003)
    ob.rotation_euler = Euler((tilt, 0, yaw))
    ob.data.materials.append(shared("Seed", seed_material))
    return ob


# ---- the scene -----------------------------------------------------------------------------------------

def fresh_scene(live: bool):
    global SCENE
    MADE.clear()
    if not live:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        SCENE = bpy.data.scenes[0]
        SCENE.name = SCENE_NAME
        return SCENE
    for kind in KINDS:  # what an earlier build made, and nothing else
        coll = getattr(bpy.data, kind)
        for d in [d for d in coll if d.get(TAG)]:
            coll.remove(d)
    SCENE = bpy.data.scenes.get(SCENE_NAME) or bpy.data.scenes.new(SCENE_NAME)
    return SCENE


def build(live: bool = False):
    sc = fresh_scene(live)
    before = {k: {d.as_pointer() for d in getattr(bpy.data, k)} for k in KINDS}
    sc.unit_settings.system, sc.unit_settings.scale_length = "METRIC", 1.0
    info = json.loads((COVER / "faces.json").read_text())
    H = info["height_mm"] / 1000

    # the stone underfoot, and the kerb behind that edges the lawn
    def block(name, loc, size, bevel):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        SCENE.collection.objects.link(ob)
        ob.location, ob.scale = loc, size
        bev = ob.modifiers.new("Worn edges", "BEVEL")
        bev.width, bev.segments = bevel, 3
        return ob

    conc = json.loads((COVER / "concrete.json").read_text())
    # the paving slab's body, its top a few millimetres down under the surface made from concrete.py
    stone = block("Paving stone", (0, KERB - GAP - 0.225, -0.029), (0.6, 0.45, 0.05), 0.004)
    stone.data.materials.append(concrete_material("Paving"))
    r_ = 0.003
    prof, arc = profile([("line", (KERB - 0.30, 0.0), (KERB - GAP - r_, 0.0)),
                         ("arc", (KERB - GAP - r_, -r_), r_, 90, 0),
                         ("line", (KERB - GAP, -r_), (KERB - GAP, -0.016))], 0.00035)
    xs = np.linspace(-0.25, 0.25, 1430)
    profiled("Paving", xs, prof, arc, lambda s_: s_ / 0.300, 0.5, concrete_maps("paving", conc), "paving", conc)
    # the kerb, swept along its length: fine where the camera sees it, coarse beyond
    R, R2 = 0.008, 0.006
    kprof, karc = profile([("line", (KERB, -0.014), (KERB, KERB_H - R)),
                           ("arc", (KERB + R, KERB_H - R), R, 180, 90),
                           ("line", (KERB + R, KERB_H), (KERB + 0.06 - R2, KERB_H)),
                           ("arc", (KERB + 0.06 - R2, KERB_H - R2), R2, 90, 0),
                           ("line", (KERB + 0.06, KERB_H - R2), (KERB + 0.06, KERB_H - 0.03))], 0.0004)
    s0 = karc[np.argmin(np.abs(kprof[:, 1] + 0.005))]           # the texture starts at the soil in the joint
    total = sum(conc["kerb_profile_mm"]) / 1000
    kxs = np.concatenate([np.linspace(-0.7, -0.36, 70)[:-1], np.linspace(-0.36, 0.36, 1800), np.linspace(0.36, 0.7, 70)[1:]])
    kerb = profiled("Kerb", kxs, kprof, karc, lambda s_: (s_ - s0) / total, 0.5, concrete_maps("kerb", conc), "kerb", conc)

    # the joint: soil a few millimetres down between the two, moss in cushions along it
    jx, jy = np.meshgrid(np.linspace(-0.7, 0.7, 1400), np.linspace(KERB - GAP - 0.001, KERB + 0.001, 12))
    jz = -0.0052 + 0.0012 * np.sin(jx * 530) * np.cos(jy * 900) + 0.0008 * np.sin(jx * 1700 + 1.3)
    jn = jx.shape[1]
    soil = mesh_object("Joint soil", np.stack([jx, jy, jz], -1).reshape(-1, 3),
                       [(j * jn + i, j * jn + i + 1, (j + 1) * jn + i + 1, (j + 1) * jn + i)
                        for j in range(jx.shape[0] - 1) for i in range(jn - 1)],
                       shared("Lawn thatch", soil_material), smooth=True)
    del soil
    moss = pebble_mesh("Moss", flat=0.7, seed_no=9)
    moss.materials.append(moss_material())
    scatter("Moss", -0.7, 0.7, KERB - GAP, KERB, 90000, (0.0006, 0.0016), moss, 9.0, seed_no=5, z=-0.0038)
    grain = pebble_mesh("Grain")
    grain.materials.append(scatter_material("Grit", [(0.0, srgb("#433c34")), (0.45, srgb("#6f665a")),
                                                      (0.8, srgb("#998f82")), (1.0, srgb("#c9c2b4"))]))
    stone_ = pebble_mesh("Pebble", flat=0.6, seed_no=3)
    stone_.materials.append(scatter_material("Pebbles", [(0.0, srgb("#4d4640")), (0.3, srgb("#7d6f5f")),
                                                          (0.6, srgb("#a39785")), (1.0, srgb("#d1cab9"))], 0.6))
    straw = clipping_mesh("Clipping")
    straw.materials.append(scatter_material("Clippings", [(0.0, srgb("#8a7f52")), (0.6, srgb("#b3a674")),
                                                          (1.0, srgb("#7d8450"))], 0.7))
    scatter("Sand", -0.3, 0.3, KERB - 0.1, KERB - GAP - 0.0005, 90000, (0.00008, 0.0002), grain, 60.0, seed_no=1)
    scatter("Grit", -0.3, 0.3, KERB - 0.1, KERB - GAP - 0.0005, 14000, (0.00018, 0.0006), grain, 25.0, seed_no=2)
    scatter("Pebbles", -0.3, 0.3, KERB - 0.12, KERB - GAP - 0.0005, 500, (0.0007, 0.0017), stone_, 12.0, seed_no=3)
    scatter("Clippings", -0.3, 0.3, KERB - 0.06, KERB - GAP - 0.0005, 260, (0.004, 0.009), straw, 18.0, True, seed_no=4)

    # the packets: the one behind shows its back and leans on the kerb; the one in front leans on it
    lean = (10.0, 11.4) if GOLF else (16.0, 17.5)   # the course needs the camera looking less far down
    rear = packet("Packet behind", "back", info, math.radians(lean[0]), math.radians(5.0), 0.034)
    stand(rear)
    lean_on(rear, [kerb])
    front = packet("Packet", "front", info, math.radians(lean[1]), math.radians(-2.0), -0.020)
    stand(front)
    lean_on(front, [rear, kerb])

    # the lawn beyond the kerb, kept clear of the packets, and grass come up in the joint at its foot
    blades = bpy.data.collections.new("Grass blades")      # not in the scene: only instanced
    rng = np.random.default_rng(5)
    for i in range(7):
        blades.objects.link(blade(f"Blade {i}", rng.uniform(0.045, 0.1), rng.uniform(0.0028, 0.0048),
                                  rng.uniform(0.15, 0.6)))
    if GOLF:
        golf_course(front, rear, rng)
    else:
        lawn("Lawn near", -0.9, 0.9, KERB + 0.058, 0.9, 45000, blades, 1, z0=KERB_H - 0.006, clear=(front, rear))
        lawn("Lawn far", -2.2, 2.2, 0.9, 6.0, 9000, blades, 2, z0=KERB_H - 0.006)
    packs = [world_tree(front), world_tree(rear)]
    dry = []
    for i in range(3):
        o = blade(f"Dead blade {i}", rng.uniform(0.04, 0.08), rng.uniform(0.002, 0.0035), rng.uniform(0.4, 0.9),
                  mat="Dry grass")
        dry.append(o)
    xs_all = np.concatenate([world_points(front, 9)[:, 0], world_points(rear, 9)[:, 0]])
    for tx in (xs_all.min() - 0.02, xs_all.max() + 0.022, xs_all.max() + 0.07, xs_all.min() - 0.075):
        tuft(tx, list(blades.objects), dry, rng, packs)

    feet = world_points(front, 5)
    foot_y = feet[feet[:, 2] < 0.001][:, 1].min()
    seed("Seed 1", (-0.041, foot_y - 0.0052), math.radians(24))
    seed("Seed 2", (-0.012, foot_y - 0.0086), math.radians(-58), length=0.0041)
    seed("Seed 3", (0.021, foot_y - 0.0044), math.radians(101), length=0.0046)
    seed("Seed 4", (0.052, foot_y - 0.0021), math.radians(12), length=0.0038)

    # the camera: square to the front packet's face, centred on the pair
    mw = front.matrix_world
    centre = mw @ Vector((0.017, H * (0.64 if GOLF else 0.5), 0.0))
    normal = (mw.to_3x3() @ Vector((0, 0, 1))).normalized()
    dist = FRAME / (2 * 18 / 50)
    cam_dir = Matrix.Rotation(ORBIT, 3, "Z") @ normal
    cd = bpy.data.cameras.new("50 mm")
    cd.lens, cd.sensor_width, cd.sensor_fit = 50.0, 36.0, "HORIZONTAL"
    cd.dof.use_dof, cd.dof.aperture_fstop, cd.dof.focus_distance = True, FSTOP, dist
    cd.dof.aperture_blades = 0
    cd.clip_start = 0.01
    cam = bpy.data.objects.new("Camera", cd)
    SCENE.collection.objects.link(cam)
    look = (-cam_dir).to_track_quat("-Z", "Y")
    cam.rotation_euler = (look.to_matrix().to_4x4() @ Matrix.Rotation(ROLL, 4, "Z")).to_euler()
    cam.location = centre + cam_dir * dist
    sc.camera = cam
    if GOLF:
        # a ball come to rest down in the rough, the blades round and in front of it: placed where the camera
        # sees it, beside the packets and a little past the kerb
        from bpy_extras.object_utils import world_to_camera_view
        sc.render.resolution_x = sc.render.resolution_y = 3000
        SCENE.view_layers[0].update()
        by, bz = KERB + 0.2, KERB_H - 0.006 + 0.012
        xs_ = np.linspace(-0.3, 0.5, 400)
        sx = np.array([world_to_camera_view(sc, cam, Vector((x, by, bz))).x for x in xs_])
        golf_ball((float(xs_[np.argmin(np.abs(sx - 0.9))]), by, bz))

    # light: a low sun from the upper left, a little in front; the sky for the rest
    to_sun = Vector((-0.75, -0.4, 0.53)).normalized()
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy, sd.angle, sd.color = SUN, math.radians(1.5), (1.0, 0.975, 0.94)
    sun = bpy.data.objects.new("Sun", sd)
    SCENE.collection.objects.link(sun)
    sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("Sky")
    sc.world = world
    if world.node_tree is None:
        world.use_nodes = True
    wn = world.node_tree
    wn.nodes.clear()
    sky = wn.nodes.new("ShaderNodeTexSky")
    sky.sky_type, sky.sun_disc = "MULTIPLE_SCATTERING", False
    sky.sun_elevation = math.asin(to_sun.z)
    sky.sun_rotation = math.atan2(to_sun.x, to_sun.y)
    bg = wn.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = SKY
    out = wn.nodes.new("ShaderNodeOutputWorld")
    wn.links.new(sky.outputs[0], bg.inputs["Color"])
    wn.links.new(bg.outputs[0], out.inputs["Surface"])

    for k in KINDS:
        for d in getattr(bpy.data, k):
            if d.as_pointer() not in before[k]:
                d[TAG] = True

    # render
    sc.render.engine = "CYCLES"
    sc.cycles.device = "GPU"
    if not live:  # a live session keeps its own device preferences
        prefs = bpy.context.preferences.addons["cycles"].preferences
        try:
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = d.type == "OPTIX"
        except Exception as e:  # no GPU here: the CPU will do, slowly
            print("GPU unavailable:", e)
            sc.cycles.device = "CPU"
    sc.cycles.use_adaptive_sampling, sc.cycles.adaptive_threshold = True, 0.004
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
        sc.cycles.denoising_prefilter = "ACCURATE"
    except Exception:
        pass
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.render.resolution_x = sc.render.resolution_y = 3000
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = "8"
    vs = sc.view_settings
    vs.view_transform, vs.look = "Khronos PBR Neutral", "None"   # keeps the paper cream and the red a red
    vs.exposure = EXPOSURE
    vs.use_white_balance, vs.white_balance_temperature, vs.white_balance_tint = True, WHITE_BALANCE, 8.0
    sc.cycles.samples = 640
    return sc


def show(sc):
    """In a live session: this scene in the window, looking through the camera, rendered."""
    win = bpy.context.window_manager.windows[0]
    win.scene = sc
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            sp = area.spaces.active
            sp.region_3d.view_perspective = "CAMERA"
            sp.shading.type = "RENDERED"
    sc.cycles.preview_samples = 64


def main():
    if MODE == "live":
        sc = build(live=True)
        show(sc)
        print(f"built the cover in scene '{SCENE_NAME}'")
        return
    sc = build()
    bpy.ops.wm.save_as_mainfile(filepath=str(ART / f"cover{SUFFIX}.blend"))
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    if MODE == "save":
        return
    if MODE == "preview":
        sc.render.resolution_x = sc.render.resolution_y = 1000
        sc.cycles.samples = 96
        sc.render.filepath = str(COVER / f"preview{SUFFIX}.png")
    else:
        sc.render.filepath = str(COVER / f"render{SUFFIX}-3000.png")   # finish.py makes the release files
    bpy.ops.render.render(write_still=True)


if __name__ in ("__main__", "__songbird_link__"):
    main()
