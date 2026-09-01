import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var theme
    property string title: ""
    property string stateText: ""
    property string detail: ""
    property string tone: "info"
    property bool compact: false

    implicitHeight: compact ? 58 : 66

    Accessible.role: Accessible.StaticText
    Accessible.name: root.title + ": " + root.stateText
    Accessible.description: root.detail

    RowLayout {
        anchors.fill: parent
        spacing: root.theme.md

        Rectangle {
            Layout.preferredWidth: 8
            Layout.preferredHeight: 8
            radius: 4
            color: root.theme.toneColor(root.tone)
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                text: root.title
                color: root.theme.textDim
                font.pixelSize: root.theme.font(8)
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            Text {
                text: root.stateText
                color: root.theme.text
                font.pixelSize: root.theme.font(10)
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }

        Text {
            text: root.detail
            color: root.theme.textMuted
            font.pixelSize: root.theme.font(8)
            horizontalAlignment: Text.AlignRight
            Layout.maximumWidth: 220
            elide: Text.ElideRight
        }
    }
}
