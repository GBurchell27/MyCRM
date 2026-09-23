"""Pan/zoom canvas that draws the relationship board.

Holds no database logic: it renders whatever nodes/edges it is given and
reports interactions back through callbacks, so the owning dialog stays the
only place that writes to the board tables.
"""

import tkinter as tk

from offices import office_colors
from relationship_board import (
    CONTACT_NODE,
    NOTE_NODE,
    age_label,
    kind_is_directed,
    kind_label,
    node_is_orphan,
    node_title,
)

NODE_W, NODE_H = 200.0, 84.0
NOTE_W, NOTE_H = 190.0, 120.0
MIN_ZOOM, MAX_ZOOM = 0.3, 2.4

BOARD_BG = "#f7f8fa"
ORPHAN_FILL = "#f7e6e6"
ORPHAN_OUTLINE = "#c98b8b"
NOTE_OUTLINE = "#d8c25f"
SELECT_OUTLINE = "#1d4f91"
LINK_OUTLINE = "#c9761d"
EDGE_COLOR = "#8b97a4"
EDGE_SELECTED = "#1d4f91"
TITLE_COLOR = "#1b2733"
DETAIL_COLOR = "#4b5866"
MUTED_COLOR = "#7c8797"


def blend(color, target, amount):
    """Mix a #rrggbb colour towards another one; used to fade stale cards."""
    if amount <= 0 or len(color) != 7 or not color.startswith("#"):
        return color
    amount = min(1.0, amount)
    channels = [
        round(int(color[i:i + 2], 16) + (int(target[i:i + 2], 16) - int(color[i:i + 2], 16)) * amount)
        for i in (1, 3, 5)
    ]
    return "#%02x%02x%02x" % tuple(channels)


class BoardCanvas(tk.Canvas):
    def __init__(self, master, on_select=None, on_move=None, on_open=None,
                 on_link=None, on_context=None, **kwargs):
        kwargs.setdefault("background", BOARD_BG)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)
        self.on_select = on_select or (lambda kind, item_id: None)
        self.on_move = on_move or (lambda node_id, x, y: None)
        self.on_open = on_open or (lambda node_id: None)
        self.on_link = on_link or (lambda source_id, target_id: None)
        self.on_context = on_context or (lambda kind, item_id, event: None)

        self.zoom = 1.0
        self.nodes = []
        self.edges = []
        self._by_id = {}
        self.selected_kind = None
        self.selected_id = None
        self.link_mode = False
        self.link_source_id = None

        self._drag_node = None
        self._drag_origin = None
        self._drag_moved = False
        self._panning = False
        self._fit_pending = True

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Configure>", self._on_configure)

    # --- data ---------------------------------------------------------------

    def set_data(self, nodes, edges, keep_view=True):
        self.nodes = nodes
        self.edges = edges
        self._by_id = {n["id"]: n for n in nodes}
        if self.selected_id not in self._by_id and self.selected_kind == "node":
            self.selected_kind = self.selected_id = None
        if self.link_source_id not in self._by_id:
            self.link_source_id = None
        if keep_view:
            self.redraw()
        else:
            self.fit_to_content()

    def selected_node(self):
        if self.selected_kind != "node":
            return None
        return self._by_id.get(self.selected_id)

    def select(self, kind, item_id, notify=True):
        self.selected_kind = kind
        self.selected_id = item_id
        self.redraw()
        if notify:
            self.on_select(kind, item_id)

    def set_link_mode(self, enabled):
        self.link_mode = enabled
        self.link_source_id = None
        self.configure(cursor="tcross" if enabled else "")
        self.redraw()

    # --- drawing ------------------------------------------------------------

    def redraw(self):
        self.delete("all")
        for edge in self.edges:
            self._draw_edge(edge)
        for node in self.nodes:
            self._draw_node(node)
        self._update_scrollregion()

    def _font(self, size, weight="normal", slant="roman"):
        return ("Segoe UI", max(6, int(round(size * self.zoom))), weight, slant)

    @staticmethod
    def node_size(node):
        return (NOTE_W, NOTE_H) if node["kind"] == NOTE_NODE else (NODE_W, NODE_H)

    def _node_rect(self, node):
        """Node bounds in canvas coordinates."""
        w, h = self.node_size(node)
        x0, y0 = node["x"] * self.zoom, node["y"] * self.zoom
        return x0, y0, x0 + w * self.zoom, y0 + h * self.zoom

    def _draw_node(self, node):
        tag = f"node:{node['id']}"
        x0, y0, x1, y1 = self._node_rect(node)
        selected = self.selected_kind == "node" and self.selected_id == node["id"]
        is_source = self.link_source_id == node["id"]

        fade = 0.0
        if node["kind"] == NOTE_NODE:
            fill = node["color"] or "#fff3bf"
            outline = NOTE_OUTLINE
        elif node_is_orphan(node):
            fill, outline = ORPHAN_FILL, ORPHAN_OUTLINE
        else:
            # Colour says which office; how faded says how long since you spoke.
            fade = node.get("staleness") or 0.0
            office_fill, outline = office_colors(node["office"])
            fill = blend(node["color"] or office_fill, BOARD_BG, fade)
            outline = blend(outline, BOARD_BG, fade)
        title_color = blend(TITLE_COLOR, BOARD_BG, fade * 0.5)
        detail_color = blend(DETAIL_COLOR, BOARD_BG, fade * 0.5)
        muted_color = blend(MUTED_COLOR, BOARD_BG, fade * 0.4)
        width = 1.5
        if is_source:
            outline, width = LINK_OUTLINE, 3.0
        elif selected:
            outline, width = SELECT_OUTLINE, 3.0

        self._rounded_rect(x0, y0, x1, y1, 10 * self.zoom,
                           fill=fill, outline=outline, width=width, tags=(tag,))
        pad = 12 * self.zoom
        text_width = max(20, (x1 - x0) - 2 * pad)

        if node["kind"] == NOTE_NODE:
            self.create_text(
                x0 + pad, y0 + pad, anchor="nw", width=text_width,
                text=node["label"] or "Note", fill=TITLE_COLOR,
                font=self._font(9, "bold"), tags=(tag,),
            )
            body = (node["notes"] or "").strip()
            if body and self.zoom > 0.5:
                self.create_text(
                    x0 + pad, y0 + pad + 22 * self.zoom, anchor="nw", width=text_width,
                    text=body, fill=DETAIL_COLOR, font=self._font(8), tags=(tag,),
                )
            return

        has_note = bool((node["notes"] or "").strip())
        self.create_text(
            x0 + pad, y0 + pad, anchor="nw",
            width=text_width - (14 * self.zoom if has_note else 0),
            text=node_title(node), fill=title_color,
            font=self._font(10, "bold"), tags=(tag,),
        )
        if has_note:
            self.create_text(
                x1 - pad, y0 + pad, anchor="ne", text="✎",
                fill=muted_color, font=self._font(9), tags=(tag,),
            )
        if self.zoom > 0.45:
            role = (node["role"] or "").strip() or "—"
            self.create_text(
                x0 + pad, y0 + pad + 24 * self.zoom, anchor="nw", width=text_width,
                text=role, fill=detail_color, font=self._font(8), tags=(tag,),
            )
            footer = " · ".join(
                part for part in ((node["team"] or "").strip(), (node["office"] or "").strip())
                if part
            )
            if footer:
                self.create_text(
                    x0 + pad, y1 - pad, anchor="sw", width=text_width - 34 * self.zoom,
                    text=footer, fill=muted_color,
                    font=self._font(8, slant="italic"), tags=(tag,),
                )
            age = age_label(node.get("days_since"))
            if age:
                self.create_text(
                    x1 - pad, y1 - pad, anchor="se", text=age,
                    fill=muted_color, font=self._font(8), tags=(tag,),
                )

    def _draw_edge(self, edge):
        source = self._by_id.get(edge["from_node"])
        target = self._by_id.get(edge["to_node"])
        if not source or not target:
            return
        tag = f"edge:{edge['id']}"
        sx, sy = self._center(source)
        tx, ty = self._center(target)
        x1, y1 = self._clip_to_node(source, tx, ty)
        x2, y2 = self._clip_to_node(target, sx, sy)
        selected = self.selected_kind == "edge" and self.selected_id == edge["id"]
        self.create_line(
            x1, y1, x2, y2,
            fill=EDGE_SELECTED if selected else EDGE_COLOR,
            width=3.0 if selected else 1.8,
            arrow="last" if kind_is_directed(edge["kind"]) else "none",
            arrowshape=(12, 14, 5), tags=(tag,),
        )
        if self.zoom < 0.55:
            return
        text = kind_label(edge["kind"], edge["label"])
        label_id = self.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=MUTED_COLOR,
            font=self._font(8), tags=(tag,),
        )
        bx0, by0, bx1, by1 = self.bbox(label_id)
        backing = self.create_rectangle(
            bx0 - 3, by0 - 1, bx1 + 3, by1 + 1,
            fill=BOARD_BG, outline="", tags=(tag,),
        )
        self.tag_lower(backing, label_id)

    def _center(self, node):
        x0, y0, x1, y1 = self._node_rect(node)
        return (x0 + x1) / 2, (y0 + y1) / 2

    def _clip_to_node(self, node, tx, ty):
        """Where the line towards (tx, ty) leaves this node's box."""
        x0, y0, x1, y1 = self._node_rect(node)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = tx - cx, ty - cy
        if not dx and not dy:
            return cx, cy
        half_w, half_h = (x1 - x0) / 2, (y1 - y0) / 2
        scale = min(
            half_w / abs(dx) if dx else float("inf"),
            half_h / abs(dy) if dy else float("inf"),
        )
        return cx + dx * scale, cy + dy * scale

    def _rounded_rect(self, x0, y0, x1, y1, r, **kwargs):
        r = max(1.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1,
            x0 + r, y1, x0, y1, x0, y1 - r,
            x0, y0 + r, x0, y0,
        ]
        return self.create_polygon(points, smooth=True, splinesteps=12, **kwargs)

    def _update_scrollregion(self, pad=1200):
        bbox = self.bbox("all")
        if not bbox:
            bbox = (0, 0, 1, 1)
        self.configure(scrollregion=(
            bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
        ))

    # --- view ---------------------------------------------------------------

    def zoom_by(self, factor, screen_x=None, screen_y=None):
        target = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        if abs(target - self.zoom) < 1e-6:
            return
        if screen_x is None:
            screen_x, screen_y = self.winfo_width() / 2, self.winfo_height() / 2
        world_x = self.canvasx(screen_x) / self.zoom
        world_y = self.canvasy(screen_y) / self.zoom
        self.zoom = target
        self.redraw()
        self._show_world_at(world_x, world_y, screen_x, screen_y)

    def fit_to_content(self):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 50 or height < 50:
            self._fit_pending = True
            return
        self._fit_pending = False
        if not self.nodes:
            self.zoom = 1.0
            self.redraw()
            return
        x0 = min(n["x"] for n in self.nodes)
        y0 = min(n["y"] for n in self.nodes)
        x1 = max(n["x"] + self.node_size(n)[0] for n in self.nodes)
        y1 = max(n["y"] + self.node_size(n)[1] for n in self.nodes)
        margin = 60
        self.zoom = max(MIN_ZOOM, min(
            MAX_ZOOM,
            (width - margin) / max(1.0, x1 - x0),
            (height - margin) / max(1.0, y1 - y0),
        ))
        self.redraw()
        self.center_on_world((x0 + x1) / 2, (y0 + y1) / 2)

    def center_on_world(self, world_x, world_y):
        self._show_world_at(
            world_x, world_y, self.winfo_width() / 2, self.winfo_height() / 2
        )

    def _show_world_at(self, world_x, world_y, screen_x, screen_y):
        """Scroll so a world point sits under the given screen position."""
        region = [float(v) for v in self.cget("scrollregion").split()]
        if len(region) != 4:
            return
        rx0, ry0, rx1, ry1 = region
        span_x, span_y = max(1.0, rx1 - rx0), max(1.0, ry1 - ry0)
        self.xview_moveto(((world_x * self.zoom - screen_x) - rx0) / span_x)
        self.yview_moveto(((world_y * self.zoom - screen_y) - ry0) / span_y)

    def view_center_world(self):
        return (
            self.canvasx(self.winfo_width() / 2) / self.zoom,
            self.canvasy(self.winfo_height() / 2) / self.zoom,
        )

    def event_world(self, event):
        return self.canvasx(event.x) / self.zoom, self.canvasy(event.y) / self.zoom

    # --- interaction --------------------------------------------------------

    def _hit(self, event, halo=3):
        x, y = self.canvasx(event.x), self.canvasy(event.y)
        items = self.find_overlapping(x - halo, y - halo, x + halo, y + halo)
        for prefix in ("node:", "edge:"):
            for item in reversed(items):
                for tag in self.gettags(item):
                    if tag.startswith(prefix):
                        return prefix[:-1], int(tag.split(":")[1])
        return None, None

    def _on_press(self, event):
        self.focus_set()
        kind, item_id = self._hit(event)
        if self.link_mode and kind == "node":
            if self.link_source_id is None:
                self.link_source_id = item_id
                self.redraw()
            elif self.link_source_id != item_id:
                source, self.link_source_id = self.link_source_id, None
                self.on_link(source, item_id)
            return
        if kind == "node":
            self.select("node", item_id)
            self._drag_node = self._by_id[item_id]
            self._drag_origin = (event.x, event.y)
            self._drag_moved = False
            return
        if kind == "edge":
            self.select("edge", item_id)
            return
        self.select(None, None)
        self._panning = True
        self.scan_mark(event.x, event.y)

    def _on_motion(self, event):
        if self._drag_node is not None:
            dx = event.x - self._drag_origin[0]
            dy = event.y - self._drag_origin[1]
            if not self._drag_moved and abs(dx) < 3 and abs(dy) < 3:
                return
            self._drag_moved = True
            self._drag_origin = (event.x, event.y)
            node = self._drag_node
            node["x"] += dx / self.zoom
            node["y"] += dy / self.zoom
            self.move(f"node:{node['id']}", dx, dy)
            self._redraw_edges_of(node["id"])
            return
        if self._panning:
            self.scan_dragto(event.x, event.y, gain=1)

    def _on_release(self, event):
        if self._drag_node is not None and self._drag_moved:
            node = self._drag_node
            self.on_move(node["id"], node["x"], node["y"])
            self._update_scrollregion()
        self._drag_node = None
        self._drag_moved = False
        self._panning = False

    def _redraw_edges_of(self, node_id):
        for edge in self.edges:
            if node_id in (edge["from_node"], edge["to_node"]):
                self.delete(f"edge:{edge['id']}")
                self._draw_edge(edge)
                self.tag_lower(f"edge:{edge['id']}")

    def _on_double_click(self, event):
        kind, item_id = self._hit(event)
        if kind == "node":
            self.on_open(item_id)

    def _on_right_click(self, event):
        kind, item_id = self._hit(event)
        if kind:
            self.select(kind, item_id)
        self.on_context(kind, item_id, event)

    def _on_wheel(self, event):
        self.zoom_by(1.1 if event.delta > 0 else 1 / 1.1, event.x, event.y)

    def _on_configure(self, _event):
        if self._fit_pending:
            self.fit_to_content()
