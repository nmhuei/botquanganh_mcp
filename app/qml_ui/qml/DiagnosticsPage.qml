pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "diagnosticsPage"

    required property var theme
    required property var backend
    required property var tr
    required property var labels

    property int sectionIndex: 0

    Rectangle {
        anchors.fill: parent
        color: root.theme.window

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: root.theme.lg
            spacing: root.theme.md

            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.sm

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: root.tr("System checks", "Kiểm tra hệ thống")
                        color: root.theme.text
                        font.pixelSize: root.theme.font(12)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: root.tr(
                            "Run checks only when you need evidence beyond the Monitor view.",
                            "Chỉ chạy kiểm tra khi cần bằng chứng sâu hơn màn hình Theo dõi."
                        )
                        color: root.theme.textMuted
                        font.pixelSize: root.theme.font(9)
                    }
                }

                ClassicButton {
                    theme: root.theme
                    quiet: true
                    text: root.tr("Local checks", "Kiểm tra local")
                    enabled: !root.backend.doctorBusy
                    onClicked: root.backend.runDiagnostics(true)
                }
                ClassicButton {
                    theme: root.theme
                    primary: true
                    text: root.tr("Run full doctor", "Chạy doctor đầy đủ")
                    enabled: !root.backend.doctorBusy
                    onClicked: root.backend.runDiagnostics(false)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.sm

                StatusLamp {
                    theme: root.theme
                    text: root.labels.runtimeState(root.backend.doctorStatus, root.backend.doctorStatus)
                    tone: root.backend.doctorFailureCount > 0 ? "error"
                        : root.backend.doctorWarningCount > 0 ? "warning" : "success"
                }
                Text {
                    text: root.backend.doctorWarningCount + root.tr(" warnings", " cảnh báo")
                    color: root.theme.warning
                    font.pixelSize: root.theme.font(9)
                }
                Text {
                    text: root.backend.doctorFailureCount + root.tr(" failures", " lỗi")
                    color: root.backend.doctorFailureCount > 0 ? root.theme.error : root.theme.textDim
                    font.pixelSize: root.theme.font(9)
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: "v" + root.backend.serviceVersion + " · " + root.backend.commandPolicy
                    color: root.theme.textDim
                    font.pixelSize: root.theme.font(8)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 2

                Repeater {
                    model: [
                        root.tr("Doctor", "Doctor"),
                        root.tr("Security", "Bảo mật"),
                        root.tr("Configuration", "Cấu hình"),
                        root.tr("Health metrics", "Health metrics")
                    ]

                    NavItem {
                        required property int index
                        required property string modelData
                        theme: root.theme
                        text: modelData
                        selected: root.sectionIndex === index
                        onClicked: root.sectionIndex = index
                    }
                }

                Item { Layout.fillWidth: true }

                ClassicButton {
                    theme: root.theme
                    quiet: true
                    text: "↻"
                    implicitWidth: 38
                    onClicked: root.backend.refreshNow()
                }
            }

            ClassicPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: root.theme
                outlined: false

                StackLayout {
                    anchors.fill: parent
                    currentIndex: root.sectionIndex

                    ListView {
                        id: doctorList
                        model: root.backend.doctorChecksModel
                        clip: true
                        reuseItems: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: doctorRow
                            required property int index
                            required property string name
                            required property string status
                            required property string message

                            width: doctorList.width
                            height: Math.max(root.theme.rowHeight + 8, messageText.implicitHeight + 18)
                            color: "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: root.theme.md
                                anchors.rightMargin: root.theme.md
                                spacing: root.theme.md

                                StatusLamp {
                                    theme: root.theme
                                    text: doctorRow.status
                                    tone: doctorRow.status === "failed" ? "error" : doctorRow.status === "warning" ? "warning" : "success"
                                    Layout.preferredWidth: 90
                                }
                                Text {
                                    text: doctorRow.name
                                    color: root.theme.text
                                    font.pixelSize: root.theme.font(9)
                                    font.weight: Font.DemiBold
                                    Layout.preferredWidth: 180
                                    elide: Text.ElideRight
                                }
                                Text {
                                    id: messageText
                                    text: doctorRow.message
                                    color: root.theme.textMuted
                                    font.pixelSize: root.theme.font(9)
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }

                    ListView {
                        id: securityList
                        model: root.backend.securityModel
                        clip: true
                        reuseItems: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: securityRow
                            required property string itemId
                            required property string label
                            required property string value
                            required property string tone
                            required property string detail

                            width: securityList.width
                            height: Math.max(root.theme.rowHeight + 12, detailText.implicitHeight + 22)
                            color: "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: root.theme.md
                                anchors.rightMargin: root.theme.md
                                spacing: root.theme.md

                                StatusLamp {
                                    theme: root.theme
                                    text: securityRow.value
                                    tone: securityRow.tone
                                    Layout.preferredWidth: 120
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: securityRow.label
                                        color: root.theme.text
                                        font.pixelSize: root.theme.font(9)
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        id: detailText
                                        text: securityRow.detail
                                        color: root.theme.textMuted
                                        font.pixelSize: root.theme.font(8)
                                        Layout.fillWidth: true
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }
                        }
                    }

                    ListView {
                        id: configList
                        model: root.backend.configChecksModel
                        clip: true
                        reuseItems: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: configRow
                            required property int index
                            required property string name
                            required property string status
                            required property string message

                            width: configList.width
                            height: Math.max(root.theme.rowHeight + 8, configMessage.implicitHeight + 18)
                            color: "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: root.theme.md
                                anchors.rightMargin: root.theme.md
                                spacing: root.theme.md

                                StatusLamp {
                                    theme: root.theme
                                    text: configRow.status
                                    tone: configRow.status === "failed" ? "error" : configRow.status === "warning" ? "warning" : "success"
                                    Layout.preferredWidth: 90
                                }
                                Text {
                                    text: configRow.name
                                    color: root.theme.text
                                    font.pixelSize: root.theme.font(9)
                                    font.weight: Font.DemiBold
                                    Layout.preferredWidth: 190
                                }
                                Text {
                                    id: configMessage
                                    text: configRow.message
                                    color: root.theme.textMuted
                                    font.pixelSize: root.theme.font(9)
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }

                    ListView {
                        id: metricList
                        model: root.backend.healthMetricsModel
                        clip: true
                        reuseItems: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: metricRow
                            required property string itemId
                            required property string label
                            required property string value
                            required property string detail

                            width: metricList.width
                            height: root.theme.rowHeight + 8
                            color: "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: root.theme.md
                                anchors.rightMargin: root.theme.md
                                spacing: root.theme.md

                                Text {
                                    text: metricRow.label
                                    color: root.theme.textMuted
                                    font.pixelSize: root.theme.font(9)
                                    Layout.preferredWidth: 210
                                }
                                Text {
                                    text: metricRow.value
                                    color: root.theme.text
                                    font.pixelSize: root.theme.font(10)
                                    font.weight: Font.DemiBold
                                    Layout.preferredWidth: 120
                                }
                                Text {
                                    text: metricRow.detail
                                    color: root.theme.textDim
                                    font.pixelSize: root.theme.font(8)
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
