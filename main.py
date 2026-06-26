"""
main.py  —  Frontend VHDL genérico

Abre cualquier directorio (o lista de archivos .vhd), descubre la entidad
top-level, genera un testbench automático, compila con GHDL y muestra un
panel de control con:
  - Un toggle / spinner por cada puerto de entrada (no-clk)
  - Un indicador numérico/binario por cada puerto de salida
  - Controles de compilación y simulación
"""

import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QGroupBox, QGridLayout,
    QScrollArea, QFileDialog, QCheckBox, QSlider, QSizePolicy,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush

from project_discovery import discover, Project
from orchestrator import compile_project
from generic_simulator import GenericSimulator
from port_layout import compute_layout


# ── Bridge ────────────────────────────────────────────────────────────────────
class Bridge(QObject):
    state_changed = Signal(dict)


# ── Small LED indicator ────────────────────────────────────────────────────────
class LEDWidget(QLabel):
    def __init__(self, color_on="#22ee44", color_off="#082208", size=18):
        super().__init__()
        self._on = False
        self._color_on  = color_on
        self._color_off = color_off
        self.setFixedSize(size, size)
        self._r = size // 2
        self._refresh()

    def set_on(self, value: bool):
        if self._on != value:
            self._on = value
            self._refresh()

    def _refresh(self):
        color = self._color_on if self._on else self._color_off
        self.setStyleSheet(f"""
            background-color: {color};
            border-radius: {self._r}px;
            border: 1px solid #444;
        """)


# ── Port output display ───────────────────────────────────────────────────────
class PortOutputWidget(QWidget):
    """Shows the current value of one output port (1-bit LED or N-bit number)."""

    def __init__(self, port):
        super().__init__()
        self._port = port
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        name_lbl = QLabel(port.name)
        name_lbl.setStyleSheet("color:#999; font-size:11px; min-width:80px;")
        layout.addWidget(name_lbl)

        if port.width == 1:
            self._led = LEDWidget()
            layout.addWidget(self._led)
            self._value_lbl = None
        else:
            self._led = None
            self._value_lbl = QLabel("0")
            self._value_lbl.setStyleSheet(
                "color:#4fc; font-family:monospace; font-size:12px; min-width:60px;"
            )
            layout.addWidget(self._value_lbl)
            self._bits_lbl = QLabel("0b" + "0" * port.width)
            self._bits_lbl.setStyleSheet("color:#555; font-size:9px;")
            layout.addWidget(self._bits_lbl)

        layout.addStretch()

    def update(self, info: dict):
        """info = {"bits": "0101", "value": 5, "width": 4}"""
        bits   = info.get("bits",  "0" * self._port.width)
        value  = info.get("value", 0)
        if self._port.width == 1:
            self._led.set_on(bits == "1")
        else:
            self._value_lbl.setText(str(value))
            self._bits_lbl.setText("0b" + bits)


# ── Port input widget ─────────────────────────────────────────────────────────
class PortInputWidget(QWidget):
    """Control for one input port: toggle for 1-bit, spinbox for N-bit."""

    value_changed = Signal(str, int)   # (port_name, new_value)

    def __init__(self, port):
        super().__init__()
        self._port = port
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        name_lbl = QLabel(port.name)
        name_lbl.setStyleSheet("color:#bbb; font-size:11px; min-width:80px;")
        layout.addWidget(name_lbl)

        if port.width == 1:
            self._btn = QPushButton("0")
            self._btn.setCheckable(True)
            self._btn.setFixedWidth(40)
            self._btn.toggled.connect(self._on_toggle)
            layout.addWidget(self._btn)
            self._spin = None
        else:
            self._spin = QSpinBox()
            self._spin.setRange(0, (1 << port.width) - 1)
            self._spin.setValue(0)
            self._spin.setFixedWidth(90)
            self._spin.valueChanged.connect(
                lambda v: self.value_changed.emit(port.name, v)
            )
            layout.addWidget(self._spin)
            width_lbl = QLabel(f"({port.width}b)")
            width_lbl.setStyleSheet("color:#555; font-size:9px;")
            layout.addWidget(width_lbl)
            self._btn = None

        layout.addStretch()

    def _on_toggle(self, checked: bool):
        self._btn.setText("1" if checked else "0")
        self.value_changed.emit(self._port.name, int(checked))

    def current_value(self) -> int:
        if self._btn:
            return int(self._btn.isChecked())
        return self._spin.value()


# ── Group box helper ──────────────────────────────────────────────────────────
def make_group(title: str) -> QGroupBox:
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


# ── Main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GHDL Frontend — Genérico")
        self.setMinimumSize(640, 480)

        self._project: Project | None  = None
        self._layout                   = None
        self._workdir                  = os.path.join(os.getcwd(), "work_generic")
        self._tb_entity: str | None    = None
        self._sim: GenericSimulator | None = None
        self._bridge                   = Bridge()
        self._bridge.state_changed.connect(self._on_state)

        self._input_widgets:  list[PortInputWidget]  = []
        self._output_widgets: list[PortOutputWidget] = []

        self._build_ui()
        self._apply_theme()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setSpacing(10)
        v.setContentsMargins(14, 14, 14, 14)

        # Title
        title = QLabel("GHDL Frontend — Simulador VHDL Genérico")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#eee;")
        v.addWidget(title)

        self._status = QLabel("Sin proyecto cargado.")
        self._status.setStyleSheet("color:#888; font-size:11px;")
        v.addWidget(self._status)

        # File/project controls
        proj_group = make_group("Proyecto")
        proj_h = QHBoxLayout(proj_group)
        self._path_label = QLabel("—")
        self._path_label.setStyleSheet("color:#aaa; font-size:10px;")
        self._path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        proj_h.addWidget(self._path_label)
        btn_dir = QPushButton("📂 Abrir directorio…")
        btn_dir.clicked.connect(self._open_directory)
        proj_h.addWidget(btn_dir)
        btn_files = QPushButton("📄 Abrir archivos .vhd…")
        btn_files.clicked.connect(self._open_files)
        proj_h.addWidget(btn_files)
        v.addWidget(proj_group)

        # Entity / top-level selector
        ent_group = make_group("Entidad top-level")
        ent_h = QHBoxLayout(ent_group)
        ent_lbl = QLabel("Entidad:")
        ent_lbl.setStyleSheet("color:#aaa; font-size:11px;")
        ent_h.addWidget(ent_lbl)
        self._entity_combo = QComboBox()
        self._entity_combo.setMinimumWidth(200)
        self._entity_combo.currentIndexChanged.connect(self._on_entity_selected)
        ent_h.addWidget(self._entity_combo)
        ent_h.addStretch()
        v.addWidget(ent_group)

        # Ports area (scrollable, rebuilt when a project loads)
        self._ports_container = QWidget()
        self._ports_layout    = QVBoxLayout(self._ports_container)
        self._ports_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._ports_container)
        scroll.setMinimumHeight(200)
        v.addWidget(scroll, stretch=1)

        # Speed + controls
        bottom = QHBoxLayout()

        cfg_group = make_group("Simulación")
        cfg_v = QVBoxLayout(cfg_group)
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Velocidad:"))
        self._speed = QSlider(Qt.Horizontal)
        self._speed.setRange(10, 2000)
        self._speed.setValue(100)
        self._speed.valueChanged.connect(self._on_speed)
        speed_row.addWidget(self._speed)
        self._speed_lbl = QLabel("100 pasos/frame")
        self._speed_lbl.setStyleSheet("color:#888; font-size:10px; min-width:110px;")
        speed_row.addWidget(self._speed_lbl)
        cfg_v.addLayout(speed_row)
        bottom.addWidget(cfg_group)

        ctrl_group = make_group("Control")
        ctrl_v = QVBoxLayout(ctrl_group)
        self._btn_compile = QPushButton("⚙ Compilar VHDL")
        self._btn_compile.setEnabled(False)
        self._btn_compile.clicked.connect(self._compile)
        self._btn_start = QPushButton("▶ Iniciar")
        self._btn_start.setEnabled(False)
        self._btn_start.clicked.connect(self._start)
        self._btn_stop = QPushButton("■ Detener")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop)
        for b in [self._btn_compile, self._btn_start, self._btn_stop]:
            b.setMinimumHeight(30)
            ctrl_v.addWidget(b)
        bottom.addWidget(ctrl_group)

        v.addLayout(bottom)

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
            QSpinBox {
                background: #252525; color: #eee;
                border: 1px solid #444; border-radius: 3px; padding: 2px 4px;
            }
            QScrollArea { border: none; }
            QComboBox {
                background: #252525; color: #eee;
                border: 1px solid #444; border-radius: 3px; padding: 2px 6px;
            }
            QComboBox QAbstractItemView { background: #222; color: #eee; }
        """)

    # ── File open ─────────────────────────────────────────────────────────────
    def _open_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar directorio de proyecto")
        if d:
            self._load_project(discover(d))

    def _open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar archivos VHDL", "", "VHDL (*.vhd *.vhdl)"
        )
        if files:
            self._load_project(discover(files))

    # ── Project loading ───────────────────────────────────────────────────────
    def _load_project(self, proj: Project):
        self._project = proj
        self._stop()

        self._path_label.setText(
            proj.vhd_files[0] if len(proj.vhd_files) == 1
            else f"{len(proj.vhd_files)} archivos cargados"
        )

        # Populate entity combo
        self._entity_combo.blockSignals(True)
        self._entity_combo.clear()
        for ent in proj.all_entities:
            self._entity_combo.addItem(ent.name, ent)
        # Select the auto-detected top
        if proj.top_entity:
            idx = next(
                (i for i, e in enumerate(proj.all_entities)
                 if e.name == proj.top_entity.name),
                0,
            )
            self._entity_combo.setCurrentIndex(idx)
        self._entity_combo.blockSignals(False)

        if proj.error:
            self._set_status(f"⚠ {proj.error}", "#f80")
        else:
            self._set_status(
                f"Proyecto cargado: {proj.label} — "
                f"entidad top: '{proj.top_entity.name}' "
                f"({len(proj.top_entity.ports)} puertos)",
                "#4fc"
            )

        self._rebuild_ports_ui()
        self._btn_compile.setEnabled(proj.top_entity is not None)
        self._btn_start.setEnabled(False)

    def _on_entity_selected(self, index: int):
        """User manually picked a different entity from the combo."""
        if self._project is None:
            return
        ent = self._entity_combo.itemData(index)
        if ent is not None:
            self._project.top_entity = ent
            self._rebuild_ports_ui()
            self._btn_compile.setEnabled(True)
            self._btn_start.setEnabled(False)
            self._set_status(f"Entidad seleccionada: '{ent.name}' ({len(ent.ports)} puertos)", "#4fc")

    def _rebuild_ports_ui(self):
        """Tear down and rebuild the port widgets for the current top entity."""
        # Remove old widgets
        for w in self._input_widgets + self._output_widgets:
            w.setParent(None)
        self._input_widgets.clear()
        self._output_widgets.clear()

        # Clear layout
        while self._ports_layout.count():
            item = self._ports_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        ent = self._project.top_entity if self._project else None
        if ent is None:
            return

        layout = compute_layout(ent)
        self._layout = layout

        # Outputs
        if layout.out_ports:
            out_group = make_group(f"Salidas ({len(layout.out_ports)} puertos)")
            out_v = QVBoxLayout(out_group)
            for p in layout.out_ports:
                w = PortOutputWidget(p)
                out_v.addWidget(w)
                self._output_widgets.append(w)
            self._ports_layout.addWidget(out_group)

        # Inputs
        if layout.data_in_ports:
            in_group = make_group(
                f"Entradas ({len(layout.data_in_ports)} puertos)"
                + (f" — clk: '{layout.clk_port.name}'" if layout.clk_port else " — sin clk")
            )
            in_v = QVBoxLayout(in_group)
            for p in layout.data_in_ports:
                w = PortInputWidget(p)
                w.value_changed.connect(self._on_input_changed)
                in_v.addWidget(w)
                self._input_widgets.append(w)
            self._ports_layout.addWidget(in_group)

        if layout.clk_port:
            clk_info = QLabel(f"⏱ Clock: '{layout.clk_port.name}' — gestionado automáticamente")
            clk_info.setStyleSheet("color:#666; font-size:10px;")
            self._ports_layout.addWidget(clk_info)

        self._ports_layout.addStretch()

    # ── Compile / run ─────────────────────────────────────────────────────────
    def _compile(self):
        if self._project is None or self._project.top_entity is None:
            return
        self._set_status("Compilando…", "orange")
        QApplication.processEvents()

        result = compile_project(self._project, self._workdir)
        if result["ok"]:
            self._tb_entity = result["tb_entity"]
            self._compiled_workdir = result["workdir"]
            self._set_status(
                f"✓ Compilación exitosa — testbench: '{self._tb_entity}'", "#4caf50"
            )
            self._btn_start.setEnabled(True)
        else:
            self._tb_entity = None
            self._set_status(f"✗ Error de compilación: {result['error'][:150]}", "#f44")
            self._btn_start.setEnabled(False)

    def _start(self):
        if not self._tb_entity or self._layout is None:
            return
        self._stop()

        self._sim = GenericSimulator(
            workdir=self._compiled_workdir,
            tb_entity=self._tb_entity,
            layout=self._layout,
            on_state_update=lambda s: self._bridge.state_changed.emit(s),
            steps_per_frame=self._speed.value(),
        )
        # Push current input values
        for w in self._input_widgets:
            self._sim.set_input(w._port.name, w.current_value())

        ok = self._sim.start()
        if ok:
            self._set_status("▶ Simulando…", "#5af")
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
        else:
            self._set_status("✗ No se pudo iniciar el simulador.", "#f44")
            self._sim = None

    def _stop(self):
        if self._sim:
            self._sim.stop()
            self._sim = None
        self._btn_start.setEnabled(self._tb_entity is not None)
        self._btn_stop.setEnabled(False)
        if self._tb_entity:
            self._set_status("■ Detenido", "#888")

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_input_changed(self, port_name: str, value: int):
        if self._sim:
            self._sim.set_input(port_name, value)

    def _on_speed(self, v: int):
        self._speed_lbl.setText(f"{v} pasos/frame")
        if self._sim:
            self._sim.steps_per_frame = v

    def _on_state(self, state: dict):
        for w in self._output_widgets:
            info = state.get(w._port.name)
            if info:
                w.update(info)

    def _set_status(self, msg: str, color: str = "#888"):
        self._status.setText(msg)
        self._status.setStyleSheet(f"color:{color}; font-size:11px;")

    def closeEvent(self, event):
        self._stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
