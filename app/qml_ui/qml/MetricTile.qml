import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var theme
    required property string label
    required property string value
    required property string detail
    property bool compact: false

    implicitHeight: compact ? 44 : 52

    Accessible.role: Accessible.StaticText
    Accessible.name: root.label + ": " + root.value
    Accessible.description: root.detail

    RowLayout {
        anchors.fill: parent
        spacing: root.theme.md

        Text {
            text: root.label
            color: root.theme.textDim
            font.pixelSize: root.theme.font(8)
            Layout.preferredWidth: 150
            elide: Text.ElideRight
        }

        Text {
            text: root.value
            color: root.theme.text
            font.pixelSize: root.theme.font(root.compact ? 10 : 11)
            font.weight: Font.DemiBold
            Layout.preferredWidth: 100
            elide: Text.ElideRight
        }

        Text {
            text: root.detail
            color: root.theme.textMuted
            font.pixelSize: root.theme.font(8)
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
    }
}
