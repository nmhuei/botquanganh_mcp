from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings


def test_premium_shell_and_stop_copy_is_complete_in_both_languages():
    english = DesktopTranslator("en")
    vietnamese = DesktopTranslator("vi")

    assert english.text("nav.workspace_logs") == "Workspace Logs"
    assert vietnamese.text("nav.workspace_logs") == "Nhật ký Workspace"
    assert english.text("action.stop") == "Stop"
    assert vietnamese.text("action.stop") == "Dừng"
    assert "Cloudflare" in english.text("dialog.stop_body")
    assert "Cloudflare" in vietnamese.text("dialog.stop_body")


def test_translator_defaults_to_english_and_formats_values():
    assert DesktopTranslator().text("tab.runtime") == "Runtime"
    assert DesktopTranslator("vi").text("activity.count", count=2) == "2 lệnh"


def test_translator_uses_english_fallback_for_missing_key_or_value():
    translator = DesktopTranslator("vi")

    assert translator.text("missing.key") == "missing.key"
    assert translator.text("activity.count") == "{count} commands"


def test_translation_bindings_update_existing_widget():
    class Widget:
        def __init__(self):
            self.values = []

        def configure(self, **values):
            self.values.append(values)

    widget = Widget()
    bindings = TranslationBindings(DesktopTranslator("en"))

    bindings.bind(widget, "action.refresh")
    bindings.set_translator(DesktopTranslator("vi"))

    assert widget.values == [{"text": "Refresh"}, {"text": "Làm mới"}]
