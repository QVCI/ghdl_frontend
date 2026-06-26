import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QObject

from simulator import Simulator, compile_vhdl

VHDL_DIR = "vhdl"
TOP_ENTITY = "tb_blink"
VHDL_FILES = [
    os.path.join(VHDL_DIR, "blink.vhd"),
    os.path.join(VHDL_DIR, "tb_blink.vhd"),
]


class Bridge(QObject):
    state_changed = Signal(dict)


class LEDWidget(QLabel):
    def __init__(self, label="LED"):
        super().__init__()
        self._on = False
        self.setFixedSize(60, 60)
        self.setAlignment(Qt.AlignCenter)
        self._label = label
        self._refresh()

    def set_on(self, value):
        if self._on != bool(value):
            self._on = bool(value)
            self._refresh()

    def _refresh(self):
        color = "#ff3300" if self._on else "#330000"
        self.setStyleSheet(f"""
            background-color: {color};
            border-radius: 30px;
            border: 2px solid #666;
            color: white;
            font-weight: bold;
            font-size: 10px;
        """)
        self.setText(self._label)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GHDL Frontend — Tang Nano 9K")
        self.setMinimumSize(400, 300)
        self.sim = None
        self.bridge = Bridge()
        self.bridge.state_changed.connect(self._on_state)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Tang Nano 9K — Simulador")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.status_label = QLabel("Estado: sin compilar")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        led_row = QHBoxLayout()
        led_row.addWidget(QLabel("LED:"))
        self.led = LEDWidget("LED")
        led_row.addWidget(self.led)
        led_row.addStretch()
        layout.addLayout(led_row)

        self.sw_check = QCheckBox("Switch (reset)")
        self.sw_check.stateChanged.connect(self._on_switch)
        layout.addWidget(self.sw_check)

        btn_row = QHBoxLayout()
        self.btn_compile = QPushButton("Compilar")
        self.btn_compile.clicked.connect(self._compile)
        self.btn_start = QPushButton("Iniciar")
        self.btn_start.clicked.connect(self._start)
        self.btn_start.setEnabled(False)
        self.btn_stop = QPushButton("Detener")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_compile)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        layout.addLayout(btn_row)

        layout.addStretch()

    def _compile(self):
        self.status_label.setText("Compilando...")
        self.status_label.setStyleSheet("color: orange;")
        QApplication.processEvents()
        ok, err = compile_vhdl(VHDL_FILES, TOP_ENTITY)
        if ok:
            self.status_label.setText("Compilación exitosa")
            self.status_label.setStyleSheet("color: green;")
            self.btn_start.setEnabled(True)
        else:
            self.status_label.setText(f"Error: {err[:120]}")
            self.status_label.setStyleSheet("color: red;")

    def _start(self):
        if self.sim:
            self.sim.stop()
        self.sim = Simulator(
            top_entity=TOP_ENTITY,
            on_state_update=lambda s: self.bridge.state_changed.emit(s)
        )
        self.sim.start()
        self.status_label.setText("Simulando...")
        self.status_label.setStyleSheet("color: blue;")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _stop(self):
        if self.sim:
            self.sim.stop()
            self.sim = None
        self.status_label.setText("Detenido")
        self.status_label.setStyleSheet("color: gray;")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_switch(self, state):
        if self.sim:
            self.sim.set_input("sw", 1 if state else 0)

    def _on_state(self, state):
        if "LED" in state:
            self.led.set_on(state["LED"])

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