import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QSlider, QGroupBox, QGridLayout,
    QFrame, QSizePolicy, QToolButton
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush

from simulator import Simulator, compile_vhdl

VHDL_DIR = "vhdl"
TOP_ENTITY = "tb_tang"
VHDL_FILES = [
    os.path.join(VHDL_DIR, "tang_nano_9k.vhd"),
    os.path.join(VHDL_DIR, "tb_tang.vhd"),
]


# ─────────────────────────────────────────── Bridge
class Bridge(QObject):
    state_changed = Signal(dict)


# ─────────────────────────────────────────── LED Widget
class LEDWidget(QLabel):
    def __init__(self, color_on="#ff3300", color_off="#1a0000", size=28):
        super().__init__()
        self._on = False
        self._color_on = color_on
        self._color_off = color_off
        r = size // 2
        self.setFixedSize(size, size)
        self._r = r
        self._size = size
        self._refresh()

    def set_on(self, value: bool):
        if self._on != value:
            self._on = value
            self._refresh()

    def _refresh(self):
        color = self._color_on if self._on else self._color_off
        glow = "box-shadow: 0 0 8px 3px " + self._color_on + ";" if self._on else ""
        self.setStyleSheet(f"""
            background-color: {color};
            border-radius: {self._r}px;
            border: 1px solid #444;
            {glow}
        """)


# ─────────────────────────────────────────── Switch Widget
class SwitchWidget(QWidget):
    toggled = Signal(bool)

    def __init__(self, label=""):
        super().__init__()
        self._on = False
        self._label = label
        self.setFixedSize(36, 56)
        self.setCursor(Qt.PointingHandCursor)

    def is_on(self):
        return self._on

    def mousePressEvent(self, event):
        self._on = not self._on
        self.toggled.emit(self._on)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Body
        body_color = QColor("#2a2a2a")
        p.setBrush(QBrush(body_color))
        p.setPen(QPen(QColor("#555"), 1))
        p.drawRoundedRect(8, 4, 20, 44, 4, 4)

        # Lever
        lever_color = QColor("#cccccc") if not self._on else QColor("#88aaff")
        p.setBrush(QBrush(lever_color))
        p.setPen(Qt.NoPen)
        if self._on:
            p.drawRoundedRect(10, 6, 16, 20, 3, 3)
        else:
            p.drawRoundedRect(10, 26, 16, 20, 3, 3)

        # Label
        if self._label:
            p.setPen(QColor("#888"))
            p.setFont(QFont("monospace", 7))
            p.drawText(0, 50, 36, 10, Qt.AlignCenter, self._label)


# ─────────────────────────────────────────── 7-Segment Display Widget
SEG_SEGS = "abcdefgp"   # order in the 8-bit word from testbench

# Segment rectangles: (x, y, w, h, horizontal?)
#  Layout for a single digit cell (60x90 px canvas)
def _seg_rects(x0, y0, W=50, H=80, T=6):
    """Returns dict of segment -> (x,y,w,h) for one digit."""
    return {
        'a': (x0+T,    y0,       W-2*T, T),       # top
        'b': (x0+W-T,  y0+T,     T,     H//2-2*T),# top-right
        'c': (x0+W-T,  y0+H//2+T,T,    H//2-2*T), # bot-right
        'd': (x0+T,    y0+H-T,   W-2*T, T),       # bottom
        'e': (x0,      y0+H//2+T,T,     H//2-2*T),# bot-left
        'f': (x0,      y0+T,     T,     H//2-2*T),# top-left
        'g': (x0+T,    y0+H//2-T//2, W-2*T, T),   # middle
        'p': (x0+W+2,  y0+H-T,   T,     T),       # decimal point
    }


class SevenSegWidget(QWidget):
    """Draws 4 multiplexed seven-segment displays."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(240, 110)
        # digit_segs[i] = 8-bit bool list (a,b,c,d,e,f,g,dp), latched
        self.digit_segs = [[False]*8 for _ in range(4)]
        self._active = -1  # which digit is currently active (-1=none)

    def update_state(self, digit_bits: list, seg_bits: list):
        """digit_bits: 4 bools (active-low), seg_bits: 8 bools."""
        active = -1
        for i, d in enumerate(digit_bits):
            if not d:  # active-low: False means active
                active = i
        if active >= 0:
            self.digit_segs[active] = list(seg_bits)
        self._active = active
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d0d0d"))

        W, H, T = 46, 76, 6
        gap = 10
        total_w = 4 * (W + gap + T + 4)
        x_start = (self.width() - total_w) // 2
        y_start = (self.height() - H) // 2

        seg_names = ['a','b','c','d','e','f','g','p']
        col_on  = QColor("#ff4400")
        col_off = QColor("#1a0800")

        for digit_idx in range(4):
            x0 = x_start + digit_idx * (W + gap + T + 4)
            rects = _seg_rects(x0, y_start, W, H, T)
            segs = self.digit_segs[digit_idx]

            for si, sname in enumerate(seg_names):
                rx, ry, rw, rh = rects[sname]
                color = col_on if segs[si] else col_off
                p.setBrush(QBrush(color))
                p.setPen(Qt.NoPen)
                if sname == 'p':
                    p.drawEllipse(rx, ry, rw, rh)
                else:
                    p.drawRoundedRect(rx, ry, rw, rh, 2, 2)


# ─────────────────────────────────────────── Group Box helpers
def make_group(title):
    g = QGroupBox(title)
    g.setStyleSheet("""
        QGroupBox {
            color: #aaa;
            border: 1px solid #333;
            border-radius: 6px;
            margin-top: 8px;
            padding: 8px;
            font-size: 11px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; }
    """)
    return g


# ─────────────────────────────────────────── Main Window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tang Nano 9K — Simulador")
        self.setMinimumSize(700, 560)
        self.sim = None
        self.bridge = Bridge()
        self.bridge.state_changed.connect(self._on_state)

        self._sw_active_high  = True
        self._led_active_high = True
        self._jumper_display  = False

        self._build_ui()
        self._apply_theme()

    # ──────────────────────────── UI construction
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_v = QVBoxLayout(root)
        root_v.setSpacing(10)
        root_v.setContentsMargins(16, 16, 16, 16)

        # ── Title row
        title = QLabel("Tang Nano 9K — Simulador VHDL")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #eee;")
        root_v.addWidget(title)

        self.status_label = QLabel("Estado: sin compilar")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        root_v.addWidget(self.status_label)

        # ── LED section
        led_group = make_group("LEDs (16)")
        led_layout = QVBoxLayout(led_group)
        self.led_widgets = []
        led_names = [
            ["L15","L14","L13","L12"],
            ["L11","L10","L9","L8"],
            ["L7","L6","L5","L4"],
            ["L3","L2","L1","L0"],
        ]
        for row_labels in led_names:
            row = QHBoxLayout()
            row.setSpacing(6)
            for lbl in row_labels:
                col = QVBoxLayout()
                col.setSpacing(2)
                w = LEDWidget()
                l = QLabel(lbl)
                l.setStyleSheet("color:#666; font-size:9px;")
                l.setAlignment(Qt.AlignCenter)
                col.addWidget(w, alignment=Qt.AlignCenter)
                col.addWidget(l)
                row.addLayout(col)
                self.led_widgets.append(w)
            row.addStretch()
            led_layout.addLayout(row)
        root_v.addWidget(led_group)

        # ── 7-Segment display section
        seg_group = make_group("Display 7 Segmentos (4 dígitos multiplexados)")
        seg_layout = QVBoxLayout(seg_group)
        self.seg_widget = SevenSegWidget()
        self.seg_widget.setFixedHeight(110)
        seg_layout.addWidget(self.seg_widget)

        # Jumper selector
        jmp_row = QHBoxLayout()
        jmp_row.addWidget(QLabel("Jumper:"))
        self.jmp_leds_btn = QPushButton("LEDS")
        self.jmp_disp_btn = QPushButton("DISPLAY")
        for b in [self.jmp_leds_btn, self.jmp_disp_btn]:
            b.setCheckable(True)
            b.setFixedWidth(90)
        self.jmp_leds_btn.setChecked(True)
        self.jmp_leds_btn.clicked.connect(lambda: self._set_jumper(False))
        self.jmp_disp_btn.clicked.connect(lambda: self._set_jumper(True))
        jmp_row.addWidget(self.jmp_leds_btn)
        jmp_row.addWidget(self.jmp_disp_btn)
        jmp_row.addStretch()
        seg_layout.addLayout(jmp_row)
        root_v.addWidget(seg_group)

        # ── Switch section
        sw_group = make_group("Switches (16)")
        sw_layout = QVBoxLayout(sw_group)
        self.sw_widgets = []
        sw_labels = [
            ["SW16","SW15","SW14","SW13"],
            ["SW12","SW11","SW10","SW9"],
            ["SW8","SW7","SW6","SW5"],
            ["SW4","SW3","SW2","SW1"],
        ]
        for gi, row_labels in enumerate(sw_labels):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(f"G{gi+1}")
            lbl.setStyleSheet("color:#666; font-size:10px; min-width:20px;")
            row.addWidget(lbl)
            for li, sname in enumerate(row_labels):
                sw_idx = gi * 4 + li
                col = QVBoxLayout()
                col.setSpacing(2)
                sw = SwitchWidget(sname)
                sw.toggled.connect(lambda val, idx=sw_idx: self._on_switch(idx, val))
                name_lbl = QLabel(sname)
                name_lbl.setStyleSheet("color:#555; font-size:8px;")
                name_lbl.setAlignment(Qt.AlignCenter)
                col.addWidget(sw, alignment=Qt.AlignCenter)
                row.addLayout(col)
                self.sw_widgets.append(sw)
            row.addStretch()
            sw_layout.addLayout(row)
        root_v.addWidget(sw_group)

        # ── Config + Controls row
        bottom = QHBoxLayout()

        # Config
        cfg_group = make_group("Configuración")
        cfg_v = QVBoxLayout(cfg_group)

        self.sw_pol = QCheckBox("Switches activos en ALTO (UP=1)")
        self.sw_pol.setChecked(True)
        self.sw_pol.toggled.connect(self._on_sw_polarity)
        cfg_v.addWidget(self.sw_pol)

        self.led_pol = QCheckBox("LEDs activos en ALTO")
        self.led_pol.setChecked(True)
        self.led_pol.toggled.connect(self._on_led_polarity)
        cfg_v.addWidget(self.led_pol)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Velocidad:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(10, 2000)
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(self._on_speed)
        speed_row.addWidget(self.speed_slider)
        self.speed_lbl = QLabel("100 pasos/frame")
        self.speed_lbl.setStyleSheet("color:#888; font-size:10px; min-width:110px;")
        speed_row.addWidget(self.speed_lbl)
        cfg_v.addLayout(speed_row)
        bottom.addWidget(cfg_group)

        # Compile/run controls
        ctrl_group = make_group("Control")
        ctrl_v = QVBoxLayout(ctrl_group)
        self.btn_compile = QPushButton("⚙ Compilar VHDL")
        self.btn_compile.clicked.connect(self._compile)
        self.btn_start = QPushButton("▶ Iniciar")
        self.btn_start.clicked.connect(self._start)
        self.btn_start.setEnabled(False)
        self.btn_stop = QPushButton("■ Detener")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setEnabled(False)
        for b in [self.btn_compile, self.btn_start, self.btn_stop]:
            b.setMinimumHeight(32)
            ctrl_v.addWidget(b)
        bottom.addWidget(ctrl_group)

        root_v.addLayout(bottom)

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1a1a1a; color: #ddd; }
            QPushButton {
                background: #2c2c2c; color: #ddd;
                border: 1px solid #444; border-radius: 5px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: #383838; }
            QPushButton:pressed { background: #222; }
            QPushButton:disabled { color: #555; }
            QPushButton:checked { background: #1a3a5a; border-color: #4a8abf; color: #9cf; }
            QCheckBox { color: #bbb; }
            QSlider::groove:horizontal { background:#333; height:4px; border-radius:2px; }
            QSlider::handle:horizontal {
                background:#5a8abf; width:14px; height:14px;
                margin:-5px 0; border-radius:7px;
            }
            QLabel { color: #ccc; }
        """)

    # ──────────────────────────── Slots
    def _compile(self):
        self.status_label.setText("Compilando…")
        self.status_label.setStyleSheet("color: orange; font-size:12px;")
        QApplication.processEvents()
        ok, err = compile_vhdl(VHDL_FILES, TOP_ENTITY)
        if ok:
            self.status_label.setText("✓ Compilación exitosa")
            self.status_label.setStyleSheet("color: #4caf50; font-size:12px;")
            self.btn_start.setEnabled(True)
        else:
            self.status_label.setText(f"✗ Error: {err[:120]}")
            self.status_label.setStyleSheet("color: #f44; font-size:12px;")

    def _start(self):
        if self.sim:
            self.sim.stop()
        self.sim = Simulator(
            top_entity=TOP_ENTITY,
            on_state_update=lambda s: self.bridge.state_changed.emit(s),
            sw_active_high=self._sw_active_high,
            led_active_high=self._led_active_high,
            steps_per_frame=self.speed_slider.value(),
        )
        # Apply current switch states
        for i, sw in enumerate(self.sw_widgets):
            self.sim.set_switch(i, sw.is_on())
        self.sim.set_jumper(self._jumper_display)
        self.sim.start()
        self.status_label.setText("▶ Simulando…")
        self.status_label.setStyleSheet("color: #5af; font-size:12px;")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _stop(self):
        if self.sim:
            self.sim.stop()
            self.sim = None
        self.status_label.setText("■ Detenido")
        self.status_label.setStyleSheet("color: #888; font-size:12px;")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_switch(self, idx: int, value: bool):
        if self.sim:
            self.sim.set_switch(idx, value)

    def _set_jumper(self, display_mode: bool):
        self._jumper_display = display_mode
        self.jmp_leds_btn.setChecked(not display_mode)
        self.jmp_disp_btn.setChecked(display_mode)
        if self.sim:
            self.sim.set_jumper(display_mode)

    def _on_sw_polarity(self, checked):
        self._sw_active_high = checked
        if self.sim:
            self.sim.sw_active_high = checked

    def _on_led_polarity(self, checked):
        self._led_active_high = checked
        if self.sim:
            self.sim.led_active_high = checked

    def _on_speed(self, value):
        self.speed_lbl.setText(f"{value} pasos/frame")
        if self.sim:
            self.sim.steps_per_frame = value

    def _on_state(self, state: dict):
        # LEDs
        leds = state.get("leds", [False]*16)
        for i, w in enumerate(self.led_widgets):
            w.set_on(leds[i] if i < len(leds) else False)

        # 7-seg
        self.seg_widget.update_state(
            state.get("seg_digit", [True]*4),
            state.get("seg_segs",  [False]*8),
        )

    def closeEvent(self, event):
        if self.sim:
            self.sim.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())