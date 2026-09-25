"""Interactive 3D model render preview — Silver (VIP) and above.

The viewer is a *pure-software painter*: vertices are projected with numpy and
triangles are rasterised scanline-by-scanline into an RGB + depth buffer, then
blitted into a QImage. No OpenGL / pyglet / Blender needed, and it composites
real base-colour textures (glTF/GLB/OBJ materials) by sampling the texture
image at each triangle's UVs. Flat-shaded meshes fall back to their material's
base colour.

Entitlement: ``has_feature("model_rendering", ...)`` — Silver+ or dev mode.
Normal/Bronze users get an upgrade prompt that deep-links to the Pricing page.
"""

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel, FluentIcon, InfoBar, InfoBarPosition, MessageBox,
    PrimaryPushButton, PushButton, TitleLabel,
)

import lang
from services.ranks import RankManager, has_feature
from ui.widgets.badge import RankBadge


def _load_scene(path: str):
    """Load a mesh or full scene; force plain meshes for scan formats."""
    import trimesh
    if Path(path).suffix.lower() in (".stl", ".ply", ".off", ".xyz"):
        return trimesh.load(path, force="mesh")
    return trimesh.load(path)


# --------------------------------------------------------------- renderer --

_LIGHT = np.array([0.4, 0.7, 0.85], dtype=np.float64)
_LIGHT /= np.linalg.norm(_LIGHT)


def _material_colour_and_texture(visual):
    """Return ((r,g,b) 0-255 float, texture RGBA ndarray|None, uvs|None)."""
    from PIL import Image
    import io
    colour = np.array([168.0, 168.0, 176.0])
    texture = uvs = None
    mat = getattr(visual, "material", None)
    if mat is not None:
        factor = getattr(mat, "baseColorFactor", None)
        if factor is not None:
            factor = np.asarray(factor, dtype=float)[:3]
            colour = factor if factor.max() > 1.0 else factor * 255.0
        image = getattr(mat, "baseColorTexture", None)
        if image is not None:
            try:
                if not isinstance(image, Image.Image):
                    image = Image.open(io.BytesIO(image))
                texture = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            except Exception:
                texture = None
    uv_obj = getattr(visual, "uv", None)
    if uv_obj is not None and len(uv_obj):
        uvs = np.asarray(uv_obj, dtype=np.float64)
    return colour, texture, uvs


def _sample_texture(texture, bary, tri_uvs, y0, x0, w, h):
    """Nearest-neighbour UV lookup for one triangle block (vectorised)."""
    th, tw = texture.shape[:2]
    # Interpolate UV across the small block using barycentric gradients.
    u00, v00 = tri_uvs[0]
    du = np.array([tri_uvs[1][0] - u00, tri_uvs[2][0] - u00])
    dv = np.array([tri_uvs[1][1] - v00, tri_uvs[2][1] - v00])
    ys = np.arange(y0, y0 + h)[:, None] - 0.5
    xs = np.arange(x0, x0 + w)[None, :] - 0.5
    # Approximate UV via screen-space linear fit inside the triangle bbox.
    u = u00 + (xs / max(w, 1)) * du[0] + (ys / max(h, 1)) * du[1]
    v = v00 + (xs / max(w, 1)) * dv[0] + (ys / max(h, 1)) * dv[1]
    px = np.clip((u % 1.0) * tw, 0, tw - 1).astype(np.int32)
    py = np.clip((1.0 - (v % 1.0)) * th, 0, th - 1).astype(np.int32)
    # u/v broadcast to (h, w); output matches the coverage-mask layout.
    return texture[py, px][:, :, :3]


def render_mesh_to_qimage(mesh, yaw: float, pitch: float,
                          zoom: float, width: int = 720,
                          height: int = 540) -> Optional[QImage]:
    """Software-rasterise ``mesh`` from an orbit camera into a QImage."""
    try:
        import trimesh
        if isinstance(mesh, trimesh.Scene):
            flat = trimesh.util.concatenate(
                [g for g in mesh.geometry.values()
                 if isinstance(g, trimesh.Trimesh)])
            mesh = flat if len(flat.faces) else mesh
        if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
            return None

        verts = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        centre = verts.mean(axis=0)
        radius = max(np.abs(verts - centre).max(), 1e-6)

        # World rotation (orbit) then translate to camera space.
        cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
        cp, sp = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
        rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        pts = (verts - centre) @ rz.T @ rx.T
        pts *= min(width, height) * 0.42 * zoom / radius
        pts[:, 1] *= -1                      # y down in image space
        eye_z = radius * 3.0 / (radius * 0.84 * min(width, height) * zoom / radius)
        focal = min(width, height) * 0.9
        cam_z = pts[:, 2] + focal * 1.15
        safe = np.where(np.abs(cam_z) < 1e-3, 1e-3, cam_z)
        sx = pts[:, 0] * focal / safe + width / 2
        sy_ = pts[:, 1] * focal / safe + height / 2
        screen = np.stack([sx, sy_, cam_z], axis=1)

        colour, texture, uvs = _material_colour_and_texture(mesh.visual)
        normals = np.asarray(mesh.face_normals, dtype=np.float64)

        img = np.full((height, width, 3), 29, dtype=np.uint8)     # #1d1f22
        zbuf = np.full((height, width), np.inf, dtype=np.float64)

        p0, p1, p2 = screen[faces[:, 0]], screen[faces[:, 1]], screen[faces[:, 2]]
        area = ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
                - (p2[:, 0] - p0[:, 0]) * (p1[:, 1] - p0[:, 1]))
        front = area < 0                       # winding after y-flip
        shade = 0.35 + 0.65 * np.abs(normals @ _LIGHT)
        shade = np.clip(shade, 0.15, 1.25)

        order = np.argsort(-np.minimum.reduce([p0[:, 2], p1[:, 2], p2[:, 2]]))
        for i in order:
            if not front[i]:
                continue
            a, b, c = p0[i], p1[i], p2[i]
            x_min = max(int(np.floor(min(a[0], b[0], c[0]))), 0)
            x_max = min(int(np.ceil(max(a[0], b[0], c[0]))), width - 1)
            y_min = max(int(np.floor(min(a[1], b[1], c[1]))), 0)
            y_max = min(int(np.ceil(max(a[1], b[1], c[1]))), height - 1)
            if x_max < x_min or y_max < y_min or (x_max - x_min) > width:
                continue
            xs = np.arange(x_min, x_max + 1)          # columns (x)
            ys = np.arange(y_min, y_max + 1)          # rows    (y)
            # gx varies along axis 1, gy along axis 0 -> arrays are (h, w).
            gx = xs[None, :] + 0.5
            gy = ys[:, None] + 0.5
            denom = area[i]
            w0 = ((b[0] - gx) * (c[1] - b[1]) + (c[0] - b[0]) * (gy - b[1])) / denom
            w1 = ((c[0] - gx) * (a[1] - c[1]) + (a[0] - c[0]) * (gy - c[1])) / denom
            w2 = 1.0 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            z = w0 * a[2] + w1 * b[2] + w2 * c[2]
            region_z = zbuf[y_min:y_max + 1, x_min:x_max + 1]
            visible = inside & (z < region_z)
            if not visible.any():
                continue
            if texture is not None and uvs is not None:
                tri_uvs = uvs[faces[i]]
                rgb = _sample_texture(texture, None, tri_uvs,
                                      y_min, x_min,
                                      x_max - x_min + 1, y_max - y_min + 1)
                rgb = rgb * shade[i]
            else:
                rgb = np.broadcast_to(colour * shade[i],
                                      visible.shape + (3,))
            idx = np.argwhere(visible)
            yy = idx[:, 0] + y_min
            xx = idx[:, 1] + x_min
            img[yy, xx] = np.clip(rgb[idx[:, 0], idx[:, 1]], 0, 255)
            region_z[visible] = z[visible]

        data = np.ascontiguousarray(img)
        image = QImage(data.tobytes(), width, height,
                       width * 3, QImage.Format_RGB888).copy()
        return image if not image.isNull() else None
    except Exception:
        import traceback
        traceback.print_exc()
        return None


class ModelCanvas(QLabel):
    """Holds the last rendered frame; drag = orbit, wheel = zoom."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #1d1f22; border-radius: 8px;")
        self._yaw, self._pitch, self._zoom = 35.0, 22.0, 1.0
        self._last_pos = None
        self.mesh = None
        self.setText(lang.lang.get("Drag to orbit · scroll to zoom"))

    # ------------------------------------------------------- interaction --
    def mousePressEvent(self, event):
        self._last_pos = event.position()

    def mouseMoveEvent(self, event):
        if self._last_pos is not None and self.mesh is not None:
            delta = event.position() - self._last_pos
            self._yaw += delta.x() * 0.4
            self._pitch = max(-89.0, min(89.0, self._pitch + delta.y() * 0.4))
            self.render()
        self._last_pos = event.position()

    def mouseReleaseEvent(self, event):
        self._last_pos = None

    def wheelEvent(self, event):
        factor = 0.9 if event.angleDelta().y() > 0 else 1.1
        self._zoom = max(0.35, min(2.5, self._zoom * factor))
        self.render()

    # ------------------------------------------------------------ drawing --
    def set_mesh(self, mesh):
        self.mesh = mesh
        self.reset_view()

    def reset_view(self):
        self._yaw, self._pitch, self._zoom = 35.0, 22.0, 1.0
        self.render()

    def render(self):
        if self.mesh is None:
            return
        image = render_mesh_to_qimage(self.mesh, self._yaw, self._pitch,
                                      self._zoom)
        if image is not None:
            scaled = image.scaled(self.size(), Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation)
            self.setPixmap(QPixmap.fromImage(scaled))


class ModelPreviewDialog(QDialog):
    """Modal dialog hosting the canvas plus stats and snapshot export."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setObjectName("modelPreviewDialog")
        self.file_path = file_path
        self.manager = RankManager.instance()
        self.setWindowTitle(Path(file_path).name)
        self.resize(860, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(TitleLabel(lang.lang.get("Model preview"), self))
        head.addStretch(1)
        head.addWidget(RankBadge(self.manager.rank, self))
        self.reset_button = PushButton(FluentIcon.ROTATE,
                                       lang.lang.get("Reset view"), self)
        head.addWidget(self.reset_button)
        root.addLayout(head)

        self.canvas = ModelCanvas(self)
        root.addWidget(self.canvas, 1)

        foot = QHBoxLayout()
        self.info = BodyLabel("", self)
        foot.addWidget(self.info, 1)
        self.export_png = PrimaryPushButton(
            FluentIcon.SAVE_AS, lang.lang.get("Export snapshot"), self)
        foot.addWidget(self.export_png)
        root.addLayout(foot)

        self.reset_button.clicked.connect(self.canvas.reset_view)
        self.export_png.clicked.connect(self._save_snapshot)

    # -------------------------------------------------------------- logic --
    def load(self) -> bool:
        """Populate the canvas. False when the file cannot be read."""
        try:
            mesh = _load_scene(self.file_path)
        except Exception as exc:
            InfoBar.error(lang.lang.get("Cannot open model"), str(exc),
                          parent=self.window(),
                          position=InfoBarPosition.TOP, duration=6000)
            return False
        self.canvas.set_mesh(mesh)
        parts = []
        geoms = getattr(mesh, "geometry", None) or {}
        verts = faces = 0
        textured = False
        items = geoms.values() if geoms else [mesh]
        for g in items:
            verts += len(getattr(g, "vertices", []))
            faces += len(getattr(g, "faces", []))
            mat = getattr(getattr(g, "visual", None), "material", None)
            if getattr(mat, "baseColorTexture", None) is not None:
                textured = True
        parts.append(lang.lang.get("{:,} vertices").format(verts))
        parts.append(lang.lang.get("{:,} faces").format(faces))
        parts.append(lang.lang.get("textured") if textured
                     else lang.lang.get("no texture"))
        self.info.setText(" · ".join(parts))
        return True

    def _save_snapshot(self):
        path, _ = QFileDialog.getSaveFileName(
            self, lang.lang.get("Export snapshot"),
            str(Path(self.file_path).with_suffix(".png")), "PNG (*.png)")
        if not path:
            return
        pixmap = self.canvas.pixmap()
        if pixmap is not None and not pixmap.isNull():
            pixmap.save(path, "PNG")


def open_model_preview(file_path: str, parent: QWidget) -> bool:
    """Show the preview if entitled; otherwise prompt to upgrade.

    Returns True when the dialog was actually shown.
    """
    manager = RankManager.instance()
    if has_feature("model_rendering", manager.rank_key, manager.dev_mode):
        dialog = ModelPreviewDialog(file_path, parent.window())
        if dialog.load():
            dialog.exec()
            return True
        return False
    box = MessageBox(
        lang.lang.get("Silver rank required"),
        lang.lang.get("3D model rendering with textures is available for "
                      "Silver (VIP) and Gold (SVIP) plans. Upgrade to "
                      "unlock this preview."),
        parent.window())
    box.yesButton.setText(lang.lang.get("View plans"))
    box.cancelButton.setText(lang.lang.get("Maybe later"))
    if box.exec():
        window = parent.window()
        interface = getattr(window, "pricing_interface", None)
        # FluentWindow routes navigation by the widget's objectName.
        if interface is not None and hasattr(window, "switchTo"):
            window.switchTo(interface)
        elif hasattr(window, "navigate"):
            window.navigate(getattr(interface, "routeKey", lambda: "")())
    return True
