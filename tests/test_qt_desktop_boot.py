def test_qt_boot_total_duration_is_three_seconds():
    from app.cli.desktop_qt.boot import QT_BOOT_TOTAL_MS

    assert QT_BOOT_TOTAL_MS == 3000


def test_qt_boot_uses_existing_phase_count():
    from app.cli.desktop_views.boot import BOOT_PHASES
    from app.cli.desktop_qt.boot import phase_delay_ms

    assert phase_delay_ms() * len(BOOT_PHASES) == 3000
