import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property string severity
    required property string title
    required property string detail
    property string actionText: ""
    property bool compact: false
    signal actionTriggered()

    property string tone: severity === "error" ? "error" : severity === "warning" ? "warning" : "info"

    Accessible.role: Accessible.AlertMessage
    Accessible.name: root.title
    Accessible.description: root.detail

    implicitHeight: Math.max(root.compact ? 48 : 62, content.implicitHeight + root.theme.md * 2)
    color: root.theme.toneBackground(root.tone)
    border.width: 1
    border.color: Qt.rgba(
        root.theme.toneColor(root.tone).r,
        root.theme.toneColor(root.tone).g,
        root.theme.toneColor(root.tone).b,
        0.22
    )
    radius: root.theme.panelRadius

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: 1
        anchors.verticalCenter: parent.verticalCenter
        width: 3
        height: Math.max(24, parent.height - 18)
        radius: 2
        color: root.theme.toneColor(root.tone)
    }

    RowLayout {
        id: content
        anchors.fill: parent
        anchors.leftMargin: root.theme.lg
        anchors.rightMargin: root.theme.md
        anchors.topMargin: root.theme.sm
        anchors.bottomMargin: root.theme.sm
        spacing: root.theme.md

        Rectangle {
            Layout.preferredWidth: 24
            Layout.preferredHeight: 24
            radius: 12
            color: "transparent"
            border.width: 1
            border.color: Qt.rgba(
                root.theme.toneColor(root.tone).r,
                root.theme.toneColor(root.tone).g,
                root.theme.toneColor(root.tone).b,
                0.42
            )

            Text {
                anchors.centerIn: parent
                text: root.tone === "error" ? "×" : root.tone === "warning" ? "!" : "i"
                color: root.theme.toneColor(root.tone)
                font.pixelSize: root.theme.font(10)
                font.weight: Font.Bold
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                text: root.title
                color: root.theme.text
                font.pixelSize: root.theme.font(10)
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                maximumLineCount: root.compact ? 1 : 2
                elide: Text.ElideRight
            }

            Text {
                text: root.detail
                color: root.theme.textMuted
                font.pixelSize: root.theme.font(9)
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                maximumLineCount: root.compact ? 1 : 3
                elide: Text.ElideRight
            }
        }

        ClassicButton {
            visible: root.actionText.length > 0
            theme: root.theme
            text: root.actionText
            quiet: true
            compact: true
            onClicked: root.actionTriggered()
        }
    }
}
