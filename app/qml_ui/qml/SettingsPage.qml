pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts

Item {
    id: root
    objectName: "settingsPage"

    required property var theme
    required property var backend
    required property var tr
    required property var labels

    function loadSearchLimits() {
        try {
            var values = JSON.parse(root.backend.searchLimitsJson || "{}");
            var apply = function(id, key) {
                var item = root.findChild(id);
                if (item && values[key] !== undefined && values[key] !== "") {
                    item.text = String(values[key]);
                }
            };
            apply("searchDeadlineField", "SEARCH_TEXT_DEADLINE_SECONDS");
            apply("searchWorkField", "WORKSPACE_SEARCH_MAX_WORK_MATCHES");
            apply("searchScannedFilesField", "WORKSPACE_SEARCH_MAX_SCANNED_FILES");
            apply("searchScannedBytesField", "WORKSPACE_SEARCH_MAX_SCANNED_BYTES");
            apply("searchConcurrentField", "WORKSPACE_SEARCH_MAX_CONCURRENT");
            apply("searchPerChatField", "WORKSPACE_SEARCH_MAX_PER_CHAT");
            apply("searchQueueField", "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS");
            apply("searchDefaultCapField", "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES");
            apply("searchMaxCapField", "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES");
            apply("searchLineCharsField", "WORKSPACE_SEARCH_MAX_LINE_CHARS");
            apply("searchPayloadField", "MCP_MAX_PAYLOAD_BYTES");
            apply("searchOverheadField", "MCP_TOOL_RESULT_OVERHEAD_BYTES");
        } catch (e) {}
    }

    Component.onCompleted: loadSearchLimits()

    FolderDialog {
        id: workspaceFolderDialog
        title: root.tr("Choose host workspace", "Chọn host workspace")
        onAccepted: workspaceField.text = selectedFolder.toString().replace("file://", "")
    }

    Rectangle {
        anchors.fill: parent
        color: root.theme.window

        ScrollView {
            anchors.fill: parent
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: Math.min(parent.width - root.theme.xl * 2, 720)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                anchors.topMargin: root.theme.xl
                spacing: root.theme.xl

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.theme.sm

                    Text {
                        text: root.tr("Appearance", "Giao diện")
                        color: root.theme.text
                        font.pixelSize: root.theme.font(12)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: root.tr(
                            "Presentation preferences apply immediately and do not change server configuration.",
                            "Tùy chọn hiển thị áp dụng ngay và không thay đổi cấu hình máy chủ."
                        )
                        color: root.theme.textMuted
                        font.pixelSize: root.theme.font(9)
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }

                    ClassicPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: appearanceGrid.implicitHeight + root.theme.xl * 2
                        theme: root.theme

                        GridLayout {
                            id: appearanceGrid
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: root.theme.xl
                            columns: 2
                            columnSpacing: root.theme.xl
                            rowSpacing: root.theme.md

                            Text {
                                text: root.tr("Language", "Ngôn ngữ")
                                color: root.theme.textMuted
                                font.pixelSize: root.theme.font(9)
                            }
                            RowLayout {
                                spacing: root.theme.xs
                                NavItem {
                                    theme: root.theme
                                    text: "English"
                                    selected: root.backend.language === "en"
                                    onClicked: root.backend.changeLanguage("en")
                                }
                                NavItem {
                                    objectName: "settingsLanguageVietnamese"
                                    theme: root.theme
                                    text: "Tiếng Việt"
                                    selected: root.backend.language === "vi"
                                    onClicked: root.backend.changeLanguage("vi")
                                }
                            }

                            Text {
                                text: root.tr("Theme", "Chủ đề")
                                color: root.theme.textMuted
                                font.pixelSize: root.theme.font(9)
                            }
                            RowLayout {
                                spacing: root.theme.xs
                                Repeater {
                                    model: [
                                        {label: root.tr("Graphite", "Graphite"), value: "classic"},
                                        {label: root.tr("Light", "Sáng"), value: "light"},
                                        {label: root.tr("Dark", "Tối"), value: "dark"}
                                    ]
                                    NavItem {
                                        required property var modelData
                                        objectName: "settingsTheme-" + modelData.value
                                        theme: root.theme
                                        text: modelData.label
                                        selected: root.backend.themeName === modelData.value
                                        onClicked: root.backend.changeTheme(modelData.value)
                                    }
                                }
                            }

                            Text {
                                text: root.tr("Density", "Mật độ")
                                color: root.theme.textMuted
                                font.pixelSize: root.theme.font(9)
                            }
                            RowLayout {
                                spacing: root.theme.xs
                                NavItem {
                                    theme: root.theme
                                    text: root.tr("Compact", "Gọn")
                                    selected: root.backend.density === "compact"
                                    onClicked: root.backend.changeDensity("compact")
                                }
                                NavItem {
                                    objectName: "settingsDensityComfortable"
                                    theme: root.theme
                                    text: root.tr("Comfortable", "Thoải mái")
                                    selected: root.backend.density === "comfortable"
                                    onClicked: root.backend.changeDensity("comfortable")
                                }
                            }

                            Text {
                                text: root.tr("Font scale", "Cỡ chữ")
                                color: root.theme.textMuted
                                font.pixelSize: root.theme.font(9)
                            }
                            RowLayout {
                                spacing: root.theme.xs
                                ClassicButton {
                                    theme: root.theme
                                    quiet: true
                                    text: "−"
                                    implicitWidth: 36
                                    onClicked: root.backend.changeFontScale(Math.max(0.8, root.backend.fontScale - 0.05))
                                }
                                Text {
                                    text: Math.round(root.backend.fontScale * 100) + "%"
                                    color: root.theme.text
                                    font.pixelSize: root.theme.font(9)
                                    Layout.preferredWidth: 48
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                ClassicButton {
                                    objectName: "settingsFontScaleUp"
                                    theme: root.theme
                                    quiet: true
                                    text: "+"
                                    implicitWidth: 36
                                    onClicked: root.backend.changeFontScale(Math.min(1.4, root.backend.fontScale + 0.05))
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.theme.sm

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: root.tr("Host workspace", "Host workspace")
                            color: root.theme.text
                            font.pixelSize: root.theme.font(12)
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        StatusLamp {
                            theme: root.theme
                            text: root.backend.bridgeState
                            tone: root.backend.bridgeState === "ready" ? "success" : "warning"
                        }
                    }

                    Text {
                        text: root.tr(
                            "Changing this path restarts the bridge while preserving the connector lifecycle.",
                            "Đổi đường dẫn này sẽ khởi động lại bridge nhưng vẫn giữ vòng đời connector."
                        )
                        color: root.theme.textMuted
                        font.pixelSize: root.theme.font(9)
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }

                    ClassicPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: workspaceControls.implicitHeight + root.theme.xl * 2
                        theme: root.theme

                        ColumnLayout {
                            id: workspaceControls
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: root.theme.xl
                            spacing: root.theme.sm

                            ClassicSearch {
                                id: workspaceField
                                objectName: "workspaceField"
                                theme: root.theme
                                Layout.fillWidth: true
                                text: root.backend.workspace
                                placeholderText: root.tr("Workspace path", "Đường dẫn workspace")
                                debounceMs: 999999
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: root.theme.xs

                                ClassicButton {
                                    theme: root.theme
                                    quiet: true
                                    text: root.tr("Browse…", "Duyệt…")
                                    onClicked: workspaceFolderDialog.open()
                                }
                                Item { Layout.fillWidth: true }
                                ClassicButton {
                                    theme: root.theme
                                    primary: true
                                    text: root.tr("Apply workspace", "Áp dụng workspace")
                                    enabled: workspaceField.text.length > 0 && !root.backend.actionBusy
                                    onClicked: root.backend.applyWorkspace(workspaceField.text)
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.theme.sm

                    Text {
                        text: root.tr("Search Limits", "Giới hạn tìm kiếm")
                        color: root.theme.text
                        font.pixelSize: root.theme.font(12)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: root.tr(
                            "Bounded workspace search. Saving restarts the bridge only and preserves the connector.",
                            "Tìm kiếm có giới hạn. Lưu sẽ chỉ khởi động lại bridge và giữ connector."
                        )
                        color: root.theme.textMuted
                        font.pixelSize: root.theme.font(9)
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }

                    ClassicPanel {
                        Layout.fillWidth: true
                        theme: root.theme

                        ColumnLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: root.theme.xl
                            spacing: root.theme.sm

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: root.theme.xl
                                rowSpacing: root.theme.md

                                Text { text: "SEARCH_TEXT_DEADLINE_SECONDS (s)"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchDeadlineField; objectName: "searchDeadlineField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_WORK_MATCHES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchWorkField; objectName: "searchWorkField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_SCANNED_FILES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchScannedFilesField; objectName: "searchScannedFilesField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_SCANNED_BYTES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchScannedBytesField; objectName: "searchScannedBytesField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_CONCURRENT"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchConcurrentField; objectName: "searchConcurrentField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_PER_CHAT"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchPerChatField; objectName: "searchPerChatField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS (s)"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchQueueField; objectName: "searchQueueField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchDefaultCapField; objectName: "searchDefaultCapField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchMaxCapField; objectName: "searchMaxCapField"; text: ""; Layout.fillWidth: true }
                                Text { text: "WORKSPACE_SEARCH_MAX_LINE_CHARS"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchLineCharsField; objectName: "searchLineCharsField"; text: ""; Layout.fillWidth: true }
                                Text { text: "MCP_MAX_PAYLOAD_BYTES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchPayloadField; objectName: "searchPayloadField"; text: ""; Layout.fillWidth: true }
                                Text { text: "MCP_TOOL_RESULT_OVERHEAD_BYTES"; color: root.theme.textMuted; font.pixelSize: root.theme.font(9) }
                                TextField { id: searchOverheadField; objectName: "searchOverheadField"; text: ""; Layout.fillWidth: true }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Item { Layout.fillWidth: true }
                                ClassicButton {
                                    objectName: "applySearchLimitsButton"
                                    theme: root.theme
                                    primary: true
                                    text: root.tr("Save search limits", "Lưu giới hạn tìm kiếm")
                                    enabled: !root.backend.actionBusy
                                    onClicked: root.backend.applySearchLimits(JSON.stringify({
                                        "SEARCH_TEXT_DEADLINE_SECONDS": searchDeadlineField.text,
                                        "WORKSPACE_SEARCH_MAX_WORK_MATCHES": searchWorkField.text,
                                        "WORKSPACE_SEARCH_MAX_SCANNED_FILES": searchScannedFilesField.text,
                                        "WORKSPACE_SEARCH_MAX_SCANNED_BYTES": searchScannedBytesField.text,
                                        "WORKSPACE_SEARCH_MAX_CONCURRENT": searchConcurrentField.text,
                                        "WORKSPACE_SEARCH_MAX_PER_CHAT": searchPerChatField.text,
                                        "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS": searchQueueField.text,
                                        "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES": searchDefaultCapField.text,
                                        "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES": searchMaxCapField.text,
                                        "WORKSPACE_SEARCH_MAX_LINE_CHARS": searchLineCharsField.text,
                                        "MCP_MAX_PAYLOAD_BYTES": searchPayloadField.text,
                                        "MCP_TOOL_RESULT_OVERHEAD_BYTES": searchOverheadField.text
                                    }))
                                }
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: root.theme.xl

                    Text {
                        text: root.tr(
                            "Need deeper validation?",
                            "Cần kiểm tra sâu hơn?"
                        )
                        color: root.theme.textDim
                        font.pixelSize: root.theme.font(9)
                        Layout.fillWidth: true
                    }
                    ClassicButton {
                        objectName: "openValidationButton"
                        theme: root.theme
                        quiet: true
                        text: root.tr("Open diagnostics", "Mở chẩn đoán")
                        onClicked: root.backend.setActivePage("diagnostics")
                    }
                }
            }
        }
    }
}
