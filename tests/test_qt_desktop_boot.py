def test_qt_boot_total_duration_is_three_seconds():
    from app.cli.desktop_qt.boot import QT_BOOT_TOTAL_MS

    assert QT_BOOT_TOTAL_MS == 3000


def test_qt_boot_uses_existing_phase_count():
    from app.cli.desktop_views.boot import BOOT_PHASES
    from app.cli.desktop_qt.boot import phase_delay_ms

    assert phase_delay_ms() * len(BOOT_PHASES) == 3000


def test_cyberdeck_ram_bar_contract():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from app.cli.desktop_qt.boot import CyberdeckRamBar

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bar = CyberdeckRamBar(total_units=16)
    bar.setRange(0, 100)
    assert bar.minimum() == 0
    assert bar.maximum() == 100
    bar.setValue(50)
    assert bar.value() == 50
    assert bar.text() == "50%"


def test_qt_boot_splash_initialization():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from app.cli.desktop_qt.boot import QtBootSplash, CyberdeckRamBar

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ready_called = False

    def on_ready():
        nonlocal ready_called
        ready_called = True

    splash = QtBootSplash(QtCore, QtGui, QtWidgets, on_ready=on_ready)
    assert splash.window.objectName() == "splashRoot"
    assert splash.window.width() == 680
    assert splash.window.height() == 360
    assert isinstance(splash.progress, CyberdeckRamBar)
    assert splash.phase is not None
    splash.close()
