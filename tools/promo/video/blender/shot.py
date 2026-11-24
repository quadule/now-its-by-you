"""The film's closing shot: the camera starts square on the seed packet's face, close enough that its paper fills
the 16:9 frame, and pulls back in one unhurried move (a slight arc to the right and a drop) to the cover's own
photograph, widened to 16:9, where it rests for the song's last seconds.

    blender -b renders/review/artwork/cover-golf.blend -P tools/promo/video/blender/shot.py -- [options]

    --res WxH          frame size (default 1920x1080)
    --samples N        Cycles samples (default 384)
    --frames A:B       film frame numbers, inclusive (default 8455:9073, the whole shot)
    --step K           render every Kth frame (default 1)
    --out DIR          output folder (default renders/promo/video/blender/frames)
    --format F         png16 (default), png8 or exr
    --only F1,F2,...   render just these film frames (each written as frame_NNNNNN.png)
    --no-render        build, save shot.blend and write corners.json only
    --resume           skip frames already in the output folder
    --previz           shorthand: 960x540, 24 samples, every 6th frame, to previz/, and a contact sheet
    --look             shorthand: frames 8455, 8630 (mid-move) and 9073 at 1920x1080, final samples, to look/

The blend is opened from the cover (the golf setting is the released cover) and saved as
renders/promo/video/blender/shot.blend before anything is changed; the cover's own files are never written.
Film frame i is at t = i / 60 s of the song; the scene's frame numbers are the film's, so frame_008455.png is
the shot's first frame. Blender's temporary files go to renders/promo/video/blender/tmp (set TMPDIR there too).

corners.json gives, for every frame, where the front face of the packet lands in the picture (see write_corners).
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "renders/promo/video/blender"
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

FPS = 60
F0, F1 = 8455, 9073                 # the tag's start (140.9125 s) to the file's end (151.227 s)
T0 = F0 / FPS
T_REST = 148.0                      # the move has come to rest here; the rest is a hold
EASE_IN, EASE_OUT = 1.1, 3.6        # seconds of acceleration from rest, and of settling

# the face (front-color.png: u across, v down from the top) seen at frame 0: the band and the daisy's head
CROP_W = 0.955                      # of the face's width, so the frame never reaches its edge
CROP_V0 = 0.071                     # top of the frame on the face, just above the title band
LENS = 50.0
SENSOR = 36.0

# the resting frame, in the front packet's own coordinates (x across from its middle, y up its face, metres)
REST_TARGET = (0.035, 0.057)        # the point the camera looks at
REST_DIST = 0.64                    # from that point
REST_ORBIT = math.radians(11.0)     # round to the right of square-on, as the cover
REST_ELEV = math.radians(5.3)       # looking this far down
REST_ROLL = math.radians(1.2)       # and not quite level, as the cover
FOCUS_AT = (0.017, 0.085)           # the focus at rest: on the front face, as the cover
FSTOP_NEAR, FSTOP_REST = 16.0, 4.5      # at rest, the background as blurred as in the cover, whose camera
                                        # stood at half this distance at f/8

BREEZE = math.radians(2.2)          # the grass's sway at most
SHADE_EDGE = -0.045                 # where the shade's edge crosses the paving in front of the packets (m, y)
SHADE_DRIFT = 0.012                 # the shade's edge creeps this far toward the packets over the shot (m)


def opt(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        return ARGS[i + 1] if i + 1 < len(ARGS) and not ARGS[i + 1].startswith("--") else True
    return default


# ---- the move ------------------------------------------------------------------------------------------

def _progress_table():
    """Eased progress 0..1 of the move at each 1/600 s from T0 to T_REST: speed rises from rest as sin^2 over
    EASE_IN, falls to rest as sin^2 over EASE_OUT."""
    T = T_REST - T0
    tau = np.linspace(0.0, T, int(T * 600) + 1)
    rise = np.sin(0.5 * np.pi * np.clip(tau / EASE_IN, 0, 1)) ** 2
    fall = np.sin(0.5 * np.pi * np.clip((T - tau) / EASE_OUT, 0, 1)) ** 2
    v = rise * fall
    s = np.concatenate([[0.0], np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(tau))])
    return tau, s / s[-1]


TAU, PROG = _progress_table()


def progress(t: float) -> float:
    return float(np.interp(t - T0, TAU, PROG))


# ---- the face ------------------------------------------------------------------------------------------

class Face:
    """The front packet's printed surface: its grid of points in the world, indexed [row from the top, column],
    so grid[r, c] is at u = c / (nx - 1), v = r / (ny - 1) of front-color.png."""

    def __init__(self, ob):
        me = ob.data
        info = json.loads((ROOT / "renders/review/artwork/cover/faces.json").read_text())
        ny, nx = info["front"]["sheet_grid"]
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mw = np.array(ob.matrix_world)
        g = co.reshape(ny, nx, 3) @ mw[:3, :3].T + mw[:3, 3]
        self.grid = g[::-1].copy()          # the mesh's row 0 is the bottom of the face
        self.ny, self.nx = ny, nx
        self.mw = ob.matrix_world.copy()
        self.width, self.height = info["width_mm"] / 1000, info["height_mm"] / 1000
        polys = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
                 for j in range(ny - 1) for i in range(nx - 1)]
        self.flat = self.grid.reshape(-1, 3)
        self.bvh = BVHTree.FromPolygons([tuple(p) for p in self.flat], polys)

    def at(self, u, v):
        """The point at (u, v), bilinear between grid points."""
        x, y = u * (self.nx - 1), v * (self.ny - 1)
        i, j = min(int(x), self.nx - 2), min(int(y), self.ny - 2)
        fx, fy = x - i, y - j
        g = self.grid
        p = (g[j, i] * (1 - fx) * (1 - fy) + g[j, i + 1] * fx * (1 - fy) + g[j + 1, i] * (1 - fx) * fy
             + g[j + 1, i + 1] * fx * fy)
        return Vector(p)

    def uv_of(self, p: Vector):
        """(u, v) of a point on the face, from the nearest grid cell."""
        loc, _, idx, _ = self.bvh.find_nearest(p)
        j, i = divmod(idx, self.nx - 1)
        g = self.grid
        a, b, c = Vector(g[j, i]), Vector(g[j, i + 1]), Vector(g[j + 1, i])
        du, dv = b - a, c - a
        m = Matrix(((du.dot(du), du.dot(dv)), (du.dot(dv), dv.dot(dv))))
        rhs = Vector(((loc - a).dot(du), (loc - a).dot(dv)))
        fx, fy = m.inverted() @ rhs
        return (i + fx) / (self.nx - 1), (j + fy) / (self.ny - 1)

    def local(self, x, y):
        """A point given in the packet's own coordinates (as scene.py places its camera)."""
        return self.mw @ Vector((x, y, 0.0))


def start_frame(face: Face, aspect: float):
    """Frame 0: the camera square on the face's crop, its width spanning the frame's."""
    crop_h = CROP_W * face.width / aspect / face.height
    u0, u1 = 0.5 - CROP_W / 2, 0.5 + CROP_W / 2
    v0, v1 = CROP_V0, CROP_V0 + crop_h
    rows = slice(int(v0 * (face.ny - 1)), int(math.ceil(v1 * (face.ny - 1))) + 1)
    cols = slice(int(u0 * (face.nx - 1)), int(math.ceil(u1 * (face.nx - 1))) + 1)
    pts = face.grid[rows, cols].reshape(-1, 3)
    c = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = Vector(vt[2]).normalized()
    if n.y > 0:                      # toward the camera, which stands in front (-y)
        n = -n
    right = (face.at(u1, (v0 + v1) / 2) - face.at(u0, (v0 + v1) / 2))
    right = (right - n * right.dot(n)).normalized()
    up = n.cross(right).normalized()
    centre = face.at(0.5, (v0 + v1) / 2)
    width = (face.at(u1, (v0 + v1) / 2) - face.at(u0, (v0 + v1) / 2)).length
    dist = width * LENS / SENSOR
    return dict(centre=centre, normal=n, up=up, dist=dist, crop=(u0, v0, u1, v1))


def sph(v: Vector):
    return math.atan2(v.x, -v.y), math.asin(max(-1.0, min(1.0, v.z)))


def camera_at(p: float, s0: dict, face: Face):
    """Camera position, rotation and focus distance at progress p of the move."""
    target_rest = face.local(*REST_TARGET)
    az0, el0 = sph(s0["normal"])
    n_rest = (face.mw.to_3x3() @ Vector((0, 0, 1))).normalized()
    if n_rest.y > 0:
        n_rest = -n_rest
    az_rest, _ = sph(n_rest)
    az1 = az_rest + REST_ORBIT               # round to +x, as the cover's camera
    el1 = REST_ELEV
    # the target, distance and angles travel on slightly different curves, which bends the path into an arc
    pt = p * p * (3 - 2 * p) * 0.35 + p * 0.65
    target = s0["centre"].lerp(target_rest, pt)
    dist = math.exp(math.log(s0["dist"]) + (math.log(REST_DIST) - math.log(s0["dist"])) * p)
    pa = min(1.0, p ** 1.25 * 1.0)
    az = az0 + (az1 - az0) * pa
    el = el0 + (el1 - el0) * (p ** 0.8)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    loc = target + d * dist
    fwd = (target - loc).normalized()
    up_ref = s0["up"].lerp(Vector((0, 0, 1)), p).normalized()
    right = fwd.cross(up_ref).normalized()
    up = right.cross(fwd).normalized()
    rot = Matrix((right, up, -fwd)).transposed().to_quaternion()
    rot = rot @ Quaternion((0, 0, 1), REST_ROLL * p)
    focus_pt = s0["centre"].lerp(face.local(*FOCUS_AT), p)
    focus = (focus_pt - loc).dot(fwd)
    fstop = math.exp(math.log(FSTOP_NEAR) + (math.log(FSTOP_REST) - math.log(FSTOP_NEAR)) * min(1.0, p * 1.6))
    return loc, rot, focus, fstop


def animate_camera(sc, face: Face):
    aspect = sc.render.resolution_x / sc.render.resolution_y
    s0 = start_frame(face, aspect)
    cd = bpy.data.cameras.new("Shot 50 mm")
    cd.lens, cd.sensor_width, cd.sensor_fit = LENS, SENSOR, "HORIZONTAL"
    cd.clip_start, cd.clip_end = 0.005, 1000.0
    cd.dof.use_dof, cd.dof.aperture_blades = True, 0
    cam = bpy.data.objects.new("Shot camera", cd)
    sc.collection.objects.link(cam)
    cam.rotation_mode = "QUATERNION"
    sc.camera = cam
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    poses = {}
    for f in range(F0, F1 + 1):
        loc, rot, focus, fstop = camera_at(progress(f / FPS), s0, face)
        poses[f] = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
        cam.location, cam.rotation_quaternion = loc, rot
        cd.dof.focus_distance, cd.dof.aperture_fstop = focus, fstop
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_quaternion", frame=f)
        cd.dof.keyframe_insert("focus_distance", frame=f)
        cd.dof.keyframe_insert("aperture_fstop", frame=f)
    return cam, s0, poses


# ---- the set -------------------------------------------------------------------------------------------

def copy_object(ob, name, dx=0.0, dy=0.0, mirror=False, seed=None):
    """A copy sharing ob's mesh, moved by (dx, dy), mirrored across its own x if asked, its scatter reseeded."""
    o = ob.copy()
    o.name = name
    o.location.x += dx
    o.location.y += dy
    if mirror:
        o.scale.x = -o.scale.x
    if seed is not None:
        for m in o.modifiers:
            if m.type == "NODES":
                ng = m.node_group.copy()
                for n in ng.nodes:
                    if n.bl_idname == "GeometryNodeDistributePointsOnFaces":
                        n.inputs["Seed"].default_value = seed
                m.node_group = ng
    for c in ob.users_collection:
        c.objects.link(o)
    return o


def extend_set(sc):
    """More of the same ground where the wider frame reaches: paving slabs either side of the one the packets
    stand on and a row in front (the same slab, mirrored on alternate ones so neighbours differ); the grit and
    clippings strewn over them; a bed of joint fill under all the slabs."""
    obs = bpy.data.objects
    paving, stone = obs["Paving"], obs["Paving stone"]
    pitch_x, pitch_y = 0.506, 0.306           # a slab and its joint
    for ix in (-1, 0, 1):
        for iy in (0, -1):
            if ix or iy:
                copy_object(paving, f"Paving {ix} {iy}", ix * pitch_x, iy * pitch_y, mirror=bool((ix + iy) % 2))
    # the joints between slabs: the same grimy concrete a few millimetres down
    me = bpy.data.meshes.new("Joint fill")
    me.from_pydata([(-1.4, -1.0, -0.0045), (1.4, -1.0, -0.0045), (1.4, 0.03, -0.0045), (-1.4, 0.03, -0.0045)],
                   [], [(0, 1, 2, 3)])
    me.materials.append(stone.data.materials[0])
    sc.collection.objects.link(bpy.data.objects.new("Joint fill", me))
    for k, name in enumerate(("Sand", "Grit", "Pebbles", "Clippings")):
        for ix in (-2, -1, 1, 2):
            copy_object(obs[name], f"{name} {ix}", ix * 0.6, seed=40 + 7 * k + ix)


def add_breeze(names=("Rough",)):
    """The faintest breeze in the rough behind the kerb (the lawn beyond is too soft to show it): each blade
    leans a degree or two, as a slow 4D noise over the lawn and time says."""
    for name in names:
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        ng = ob.modifiers["Blades"].node_group
        nd, ln = ng.nodes, ng.links
        inst = next(n for n in nd if n.bl_idname == "GeometryNodeInstanceOnPoints")
        src = inst.inputs["Rotation"].links[0].from_socket
        pos = nd.new("GeometryNodeInputPosition")
        tm = nd.new("GeometryNodeInputSceneTime")
        noise = nd.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "4D"
        noise.inputs["Scale"].default_value = 3.0
        noise.inputs["Detail"].default_value = 1.0
        speed = nd.new("ShaderNodeMath")
        speed.operation = "MULTIPLY"
        speed.inputs[1].default_value = 0.35
        ln.new(tm.outputs["Seconds"], speed.inputs[0])
        ln.new(pos.outputs[0], noise.inputs["Vector"])
        ln.new(speed.outputs[0], noise.inputs["W"])
        centre = nd.new("ShaderNodeVectorMath")
        centre.operation = "SUBTRACT"
        centre.inputs[1].default_value = (0.5, 0.5, 0.5)
        ln.new(noise.outputs["Color"], centre.inputs[0])
        amp = nd.new("ShaderNodeVectorMath")
        amp.operation = "MULTIPLY"
        amp.inputs[1].default_value = (BREEZE * 2, BREEZE * 2, 0.0)
        ln.new(centre.outputs[0], amp.inputs[0])
        add = nd.new("ShaderNodeVectorMath")
        add.operation = "ADD"
        ln.new(src, add.inputs[0])
        ln.new(amp.outputs[0], add.inputs[1])
        ln.new(add.outputs[0], inst.inputs["Rotation"])


def smooth_trees():
    """The far trees' crowns shaded smooth: flat facets of their low icospheres show as hard-edged blobs once the
    camera stands back and the blur is smaller than in the cover."""
    for me in {o.data for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Tree")}:
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
        me.update()


def add_shade(sc):
    """Shade over the near paving, cast by something out of frame behind the camera and to the left (a hedge
    against the low sun): a soft edge running across the foreground, creeping slowly toward the packets. It
    keeps the lower part of the resting frame calm and darker for the credits."""
    sun = bpy.data.objects["Sun"]
    to_sun = (sun.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    edge_y = SHADE_EDGE
    height = 1.1                               # the shading thing's top edge, above the paving
    t = height / to_sun.z
    e = Vector((0.0, edge_y, 0.0)) + to_sun * t
    me = bpy.data.meshes.new("Shade")
    me.from_pydata([(-6, 0, 0), (6, 0, 0), (6, -6, 0), (-6, -6, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("Shade", me)
    sc.collection.objects.link(ob)
    ob.location = e
    ob.rotation_euler = (0.0, 0.0, math.radians(-7.0))   # not quite parallel to the kerb
    ob.visible_camera = False
    ob.visible_glossy = False
    for f, dy in ((F0, 0.0), (F1, SHADE_DRIFT)):
        ob.location = e + Vector((0.0, dy, 0.0))
        ob.keyframe_insert("location", frame=f)
    return ob


# ---- corners -------------------------------------------------------------------------------------------

def homography(src, dst):
    """3x3 H with dst ~ H @ (src, 1), from four point pairs."""
    A = []
    for (x, y), (X, Y) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -X * x, -X * y, -X])
        A.append([0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y])
    _, _, vt = np.linalg.svd(np.array(A, float))
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def project(sc, cam, pts, mw):
    """World points to pixels (x right, y down, origin at the top-left corner of the frame), for the camera
    placed at mw."""
    W, Hh = sc.render.resolution_x, sc.render.resolution_y
    mi = mw.inverted()
    cd = cam.data
    fx = cd.lens / cd.sensor_width * W
    out = []
    for p in pts:
        q = mi @ Vector(p)
        out.append((W / 2 + fx * q.x / -q.z, Hh / 2 - fx * q.y / -q.z))
    return out


def write_corners(sc, cam, face: Face, s0: dict, poses: dict, path: Path):
    """corners.json: for each film frame, the front face's four corners in pixels and the homography from the
    face's UV square (u right, v down, as front-color.png) to pixels; for the first 2 s also a grid of the face's
    points in pixels, since the paper bows by a few millimetres and a homography is exact only at the corners."""
    W, Hh = sc.render.resolution_x, sc.render.resolution_y
    uvc = [(0, 0), (1, 0), (1, 1), (0, 1)]
    world_c = [face.at(u, v) for u, v in uvc]
    gu, gv = np.linspace(0, 1, 17), np.linspace(0, 1, 21)
    grid_world = [face.at(u, v) for v in gv for u in gu]
    frames = []
    for f in range(F0, F1 + 1):
        px = project(sc, cam, world_c, poses[f])
        H = homography(uvc, px)
        rec = {"frame": f, "t": round(f / FPS, 6), "corners_px": [[round(x, 3), round(y, 3)] for x, y in px],
               "H_uv_to_px": [[float(x) for x in r] for r in H]}
        if f < F0 + 2 * FPS:
            g = project(sc, cam, grid_world, poses[f])
            rec["grid_px"] = [[round(x, 2), round(y, 2)] for x, y in g]
        frames.append(rec)
    # the face's UV visible at frame 0: where the frame's corners fall on the paper (casting rays at the face)
    mw = poses[F0]
    cd = cam.data
    fx = cd.lens / cd.sensor_width * W
    crop = []
    for x, y in ((0, 0), (W, 0), (W, Hh), (0, Hh)):
        d = mw.to_3x3() @ Vector(((x - W / 2) / fx, -(y - Hh / 2) / fx, -1.0))
        hit = face.bvh.ray_cast(mw.translation, d.normalized())
        crop.append([round(c, 5) for c in face.uv_of(hit[0])] if hit[0] is not None else None)
    H0 = np.array(frames[0]["H_uv_to_px"])
    g0 = np.array(frames[0]["grid_px"])
    uvg = np.array([(u, v, 1.0) for v in gv for u in gu])
    h = uvg @ H0.T
    resid = np.hypot(*(h[:, :2] / h[:, 2:] - g0).T)
    inside = (g0[:, 0] >= 0) & (g0[:, 0] <= W) & (g0[:, 1] >= 0) & (g0[:, 1] <= Hh)
    fov_h = 2 * math.degrees(math.atan(SENSOR / 2 / LENS))
    fov_v = 2 * math.degrees(math.atan(SENSOR / 2 / LENS * Hh / W))
    doc = {
        "about": "The seed packet's front face in the Blender closing shot, per film frame. Pixels: x right, y down, "
                 "origin the top-left corner of the frame, at the frame size given (scale for other sizes). UV: the "
                 "face's own square as front-color.png lies, u = x / 3825 right, v = y / 4950 down. corners_px are "
                 "the face's corners in the order (u,v) = (0,0) top-left, (1,0) top-right, (1,1) bottom-right, "
                 "(0,1) bottom-left; H_uv_to_px maps (u, v, 1) to pixels (divide by the third). The paper bows a "
                 "few mm, so for the first 2 s grid_px gives the face's true points on a 17 x 21 grid "
                 "(u = i/16, v = j/20, row by row from the top) for a mesh warp; its departure from the "
                 "homography is in h_residual_px.",
        "frame_size": [W, Hh], "fps": FPS, "first_frame": F0, "last_frame": F1,
        "lens_mm": LENS, "sensor_width_mm": SENSOR, "fov_h_deg": round(fov_h, 4), "fov_v_deg": round(fov_v, 4),
        "face_mm": [round(face.width * 1000, 3), round(face.height * 1000, 3)],
        "face_texture": "renders/review/artwork/cover/front-color.png (3825 x 4950)",
        "crop_uv_frame0": {"aimed": [round(c, 5) for c in s0["crop"]],
                           "frame_corners_uv": crop,
                           "order": "frame's top-left, top-right, bottom-right, bottom-left as (u, v)"},
        "h_residual_px_frame0": {"max_in_frame": round(float(resid[inside].max()), 2),
                                 "mean_in_frame": round(float(resid[inside].mean()), 2)},
        "move": {"rest_from_t": T_REST, "ease_in_s": EASE_IN, "ease_out_s": EASE_OUT},
        "frames": frames,
    }
    path.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"corners: {path} (frame 0 crop {crop}; homography residual max {resid[inside].max():.2f} px)")


# ---- render settings -----------------------------------------------------------------------------------

def settings(sc, res, samples, fmt):
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences
    prefs.filepaths.temporary_directory = str(OUT / "tmp") + "/"
    cy = prefs.addons["cycles"].preferences
    try:
        cy.compute_device_type = "OPTIX"
        cy.get_devices()
        for d in cy.devices:
            d.use = d.type == "OPTIX"
        sc.cycles.device = "GPU"
    except Exception as e:
        print("GPU unavailable:", e)
        sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = float(opt("--threshold", 0.006))
    den = str(opt("--denoiser", "oidn"))
    sc.cycles.use_denoising = den != "none"
    if den == "optix":
        sc.cycles.denoiser = "OPTIX"
    elif den == "oidn":
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
        sc.cycles.denoising_prefilter = "ACCURATE"   # cleans the albedo and normal passes, noisy in the blur
        sc.cycles.denoising_use_gpu = True
    sc.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    sc.cycles.seed, sc.cycles.use_animated_seed = int(opt("--seed", 0)), False   # one noise pattern for every frame
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.render.use_persistent_data = True
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.render.motion_blur_position = "CENTER"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps, sc.render.fps_base = FPS, 1.0
    sc.frame_start, sc.frame_end = F0, F1
    im = sc.render.image_settings
    if fmt == "exr":
        im.file_format, im.color_depth, im.exr_codec = "OPEN_EXR", "16", "DWAA"
    else:
        im.file_format, im.color_mode, im.color_depth = "PNG", "RGB", "16" if fmt == "png16" else "8"
        im.compression = 15
    sc.render.use_overwrite = True
    # colour as the cover was rendered (scene.py sets these; kept): Khronos PBR Neutral, exposure -0.35,
    # white balance 6800 K, tint 8


def render_frames(sc, frames, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    import time
    times = []
    for f in frames:
        if opt("--resume") and any(out.glob(f"frame_{f:06d}.*")):
            continue
        sc.frame_set(f)
        sc.render.filepath = str(out / f"frame_{f:06d}")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        times.append(time.time() - t)
        print(f"rendered frame {f} in {times[-1]:.1f} s", flush=True)
    return times


def main():
    global REST_DIST, REST_ELEV, REST_TARGET, SHADE_EDGE
    SHADE_EDGE = float(opt("--shade", SHADE_EDGE))
    if opt("--rest"):                          # trying other resting frames: dist,elev_deg,x,y
        d_, e_, x_, y_ = (float(v) for v in str(opt("--rest")).split(","))
        REST_DIST, REST_ELEV, REST_TARGET = d_, math.radians(e_), (x_, y_)
    previz, look = bool(opt("--previz")), bool(opt("--look"))
    res = tuple(int(x) for x in str(opt("--res", "960x540" if previz else "1920x1080")).split("x"))
    samples = int(opt("--samples", 24 if previz else 384))
    fmt = opt("--format", "png8" if previz else "png16")
    step = int(opt("--step", 6 if previz else 1))
    a, b = (int(x) for x in str(opt("--frames", f"{F0}:{F1}")).split(":"))
    out = Path(opt("--out", str(OUT / ("previz" if previz else "look" if look else "frames"))))
    if not out.is_absolute():
        out = ROOT / out

    src = Path(bpy.data.filepath).resolve()
    sc = bpy.context.scene
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "shot.blend"), relative_remap=True)   # off the cover's file
    assert Path(bpy.data.filepath).resolve() != src

    settings(sc, res, samples, fmt)
    face = Face(bpy.data.objects["Packet"])
    extend_set(sc)
    add_breeze()
    smooth_trees()
    add_shade(sc)
    cam, s0, poses = animate_camera(sc, face)
    write_corners(sc, cam, face, s0, poses, OUT / ("corners.json" if res == (1920, 1080) else f"corners-{res[0]}x{res[1]}.json"))
    sc.frame_set(F0)
    bpy.ops.wm.save_mainfile()
    print("saved", bpy.data.filepath)
    if opt("--no-render"):
        return
    if opt("--only"):
        frames = [int(x) for x in str(opt("--only")).split(",")]
    elif look:
        frames = [F0, 8630, F1]
    else:
        frames = list(range(a, b + 1, step))
    times = render_frames(sc, frames, out)
    (out / "times.json").write_text(json.dumps({"res": res, "samples": samples, "frames": frames,
                                                "seconds": [round(t, 2) for t in times]}))


main()
