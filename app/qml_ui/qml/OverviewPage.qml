pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "overviewPage"

    required property var theme
    required property var backend
    required property var tr
    required property var labels

    property bool compactLayout: width < 1040 || height < 700

    function toneForState(state) {
        const value = String(state || "").toLowerCase()
        if (value === "healthy" || value === "ready" || value === "running" || value === "live" || value === "connected")
            return "success"
        if (value === "down" || value === "failed" || value === "error" || value === "offline")
            return "error"
        return "warning"
    }

    function connectorTitle() {
        if (backend.connectorUrlState === "active")
            return root.tr("Connected", "Đã kết nối")
        if (backend.connectorUrlState === "stale")
            return root.tr("Stale", "Đã cũ")
        return root.tr("Local only", "Chỉ local")
    }

    function endpointText() {
        if (backend.connectorUrlState === "active")
            return backend.endpoint
        return backend.lastKnownEndpoint
    }

    Rectangle {
        anchors.fill: parent
        color: root.theme.window

        ScrollView {
            anchors.fill: parent
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            Item {
                implicitWidth: Math.max(0, root.width)
                implicitHeight: Math.max(content.implicitHeight + root.theme.xxl * 2, root.height)

                ColumnLayout {
                    id: content
                    width: Math.min(parent.width - root.theme.xxl * 2, 980)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: root.theme.xl
                    spacing: root.theme.xl

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.theme.md

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3

                            Text {
                                text: root.tr("Monitor", "Theo dõi")
                                color: root.theme.text
                                font.pixelSize: root.theme.font(24)
                                font.weight: Font.DemiBold
                            }

                            Text {
                                text: root.tr(
                                    "System state and active work, without dashboard noise.",
                                    "Trạng thái hệ thống và công việc đang chạy, không có nhiễu dashboard."
                                )
                                color: root.theme.textDim
                                font.pixelSize: root.theme.font(9)
                            }
                        }

                        StatusLamp {
                            theme: root.theme
                            text: root.labels.runtimeState(root.backend.overallState, root.backend.runtimeBadge)
                            tone: root.backend.runtimeTone
                        }
                    }

                    ClassicPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: systemContent.implicitHeight + root.theme.xl * 2
                        theme: root.theme
                        raised: true

                        ColumnLayout {
                            id: systemContent
                            anchors.fill: parent
                            anchors.margins: root.theme.xl
                            spacing: root.theme.lg

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: root.theme.md

                                Rectangle {
                                    Layout.preferredWidth: 12
                                    Layout.preferredHeight: 12
                                    radius: 6
                                    color: root.theme.toneColor(root.backend.runtimeTone)

                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 24
                                        height: 24
                                        radius: 12
                                        color: "transparent"
                                        border.width: 1
                                        border.color: Qt.rgba(
                                            root.theme.toneColor(root.backend.runtimeTone).r,
                                            root.theme.toneColor(root.backend.runtimeTone).g,
                                            root.theme.toneColor(root.backend.runtimeTone).b,
                                            0.20
                                        )
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        text: root.labels.runtimeState(root.backend.overallState, root.backend.runtimeBadge)
                                        color: root.theme.text
                                        font.pixelSize: root.theme.font(16)
                                        font.weight: Font.DemiBold
                                    }

                                    Text {
                                        text: root.backend.overallDetail
                                        color: root.theme.textMuted
                                        font.pixelSize: root.theme.font(9)
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: root.theme.borderDark
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: root.compactLayout ? 1 : 3
                                columnSpacing: root.theme.xl
                                rowSpacing: root.theme.md

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: root.theme.sm

                                    Rectangle {
                                        Layout.preferredWidth: 7
                                        Layout.preferredHeight: 7
                                        radius: 4
                                        color: root.theme.toneColor(root.toneForState(root.backend.serverState))
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1
                                        Text {
                                            text: root.tr("Server", "Máy chủ")
                                            color: root.theme.textDim
                                            font.pixelSize: root.theme.font(8)
                                        }
                                        Text {
                                            text: root.labels.runtimeState(root.backend.serverState, root.backend.serverState)
                                            color: root.theme.text
                                            font.pixelSize: root.theme.font(10)
                                            font.weight: Font.Medium
                                        }
                                    }

                                    ClassicButton {
                                        visible: root.toneForState(root.backend.serverState) === "error"
                                        theme: root.theme
                                        primary: true
                                        compact: true
                                        text: root.tr("Start", "Khởi động")
                                        enabled: !root.backend.actionBusy
                                        onClicked: root.backend.startService()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: root.theme.sm

                                    Rectangle {
                                        Layout.preferredWidth: 7
                                        Layout.preferredHeight: 7
                                        radius: 4
                                        color: root.backend.connectorUrlState === "active"
                                            ? root.theme.success
                                            : root.backend.connectorUrlState === "stale"
                                            ? root.theme.warning : root.theme.textDim
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1
                                        Text {
                                            text: root.tr("Connector", "Connector")
                                            color: root.theme.textDim
                                            font.pixelSize: root.theme.font(8)
                                        }
                                        Text {
                                            text: root.connectorTitle()
                                            color: root.theme.text
                                            font.pixelSize: root.theme.font(10)
                                            font.weight: Font.Medium
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: root.theme.sm

                                    Rectangle {
                                        Layout.preferredWidth: 7
                                        Layout.preferredHeight: 7
                                        radius: 4
                                        color: root.backend.streamState === "LIVE" ? root.theme.success : root.theme.warning
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1
                                        Text {
                                            text: root.tr("Event stream", "Luồng sự kiện")
                                            color: root.theme.textDim
                                            font.pixelSize: root.theme.font(8)
                                        }
                                        Text {
                                            text: root.backend.streamState
                                            color: root.theme.text
                                            font.pixelSize: root.theme.font(10)
                                            font.weight: Font.Medium
                                        }
                                    }
                                }
                            }

                            RowLayout {
                                visible: root.endpointText().length > 0
                                Layout.fillWidth: true
                                spacing: root.theme.sm

                                Text {
                                    text: root.tr("Public endpoint", "Endpoint công khai")
                                    color: root.theme.textDim
                                    font.pixelSize: root.theme.font(8)
                                }

                                Text {
                                    text: root.endpointText()
                                    color: root.theme.textMuted
                                    font.family: root.backend.monoFontFamily
                                    font.pixelSize: root.theme.font(8)
                                    Layout.fillWidth: true
                                    elide: Text.ElideMiddle
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: root.backend.attentionCount > 0
                        Layout.fillWidth: true
                        spacing: root.theme.sm

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: root.tr("Needs attention", "Cần chú ý")
                                color: root.theme.text
                                font.pixelSize: root.theme.font(11)
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                            Text {
                                text: String(root.backend.attentionCount)
                                color: root.theme.warning
                                font.pixelSize: root.theme.font(9)
                                font.weight: Font.DemiBold
                            }
                        }

                        Repeater {
                            model: root.backend.attentionModel

                            InlineAlert {
                                required property string itemId

                                Layout.fillWidth: true
                                theme: root.theme
                                compact: root.compactLayout
                                onActionTriggered: root.backend.performAttentionAction(itemId)
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: root.theme.sm

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: root.tr("Active now", "Đang hoạt động")
                                color: root.theme.text
                                font.pixelSize: root.theme.font(11)
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }

                            ClassicButton {
                                theme: root.theme
                                quiet: true
                                compact: true
                                text: root.tr("Open activity", "Mở hoạt động")
                                onClicked: root.backend.setActivePage("activity")
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.max(108, Math.min(4, recentList.count) * (root.theme.rowHeight + 1) + 14)
                            color: root.theme.panel
                            radius: root.theme.panelRadius
                            border.width: 1
                            border.color: root.theme.borderDark

                            ListView {
                                id: recentList
                                anchors.fill: parent
                                anchors.margins: 6
                                clip: true
                                interactive: count > 3
                                model: root.backend.recentOperationsModel
                                spacing: 0

                                delegate: Rectangle {
                                    id: recentRow
                                    required property int index
                                    required property string utc
                                    required property string status
                                    required property string command
                                    required property string duration
                                    required property string chatId

                                    width: recentList.width
                                    height: root.theme.rowHeight
                                    radius: 7
                                    color: recentMouse.containsMouse ? root.theme.rowHover : "transparent"

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: root.theme.sm
                                        anchors.rightMargin: root.theme.sm
                                        spacing: root.theme.md

                                        Rectangle {
                                            Layout.preferredWidth: 7
                                            Layout.preferredHeight: 7
                                            radius: 4
                                            color: recentRow.status === "failed" || recentRow.status === "timed_out"
                                                ? root.theme.error
                                                : recentRow.status === "running"
                                                ? root.theme.warning
                                                : root.theme.success
                                        }

                                        Text {
                                            text: recentRow.command
                                            color: root.theme.text
                                            font.family: root.backend.monoFontFamily
                                            font.pixelSize: root.theme.font(9)
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            visible: !root.compactLayout
                                            text: recentRow.chatId
                                            color: root.theme.textDim
                                            font.pixelSize: root.theme.font(8)
                                            Layout.preferredWidth: 155
                                            elide: Text.ElideMiddle
                                        }

                                        Text {
                                            text: recentRow.status === "running"
                                                ? recentRow.duration + " ms"
                                                : root.labels.operationStatus(recentRow.status)
                                            color: recentRow.status === "failed" || recentRow.status === "timed_out"
                                                ? root.theme.error
                                                : recentRow.status === "running"
                                                ? root.theme.warning
                                                : root.theme.textMuted
                                            font.pixelSize: root.theme.font(8)
                                            font.weight: Font.Medium
                                        }
                                    }

                                    MouseArea {
                                        id: recentMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.backend.setActivePage("activity")
                                    }
                                }

                                EmptyState {
                                    anchors.fill: parent
                                    visible: recentList.count === 0
                                    theme: root.theme
                                    title: root.tr("No operation running", "Không có tác vụ đang chạy")
                                    detail: root.tr(
                                        "Commands will appear here automatically.",
                                        "Lệnh sẽ tự động xuất hiện tại đây."
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
