import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property var theme
    property string label: ""
    property string value: ""
    property string detail: ""
    property color accent: theme ? theme.accent : "#8587FF"

    implicitHeight: 96
    radius: theme ? theme.panelRadius : 12
    color: theme ? theme.panelRaised : "#151820"
    border.width: 1
    border.color: theme ? theme.border : "#252936"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: theme ? theme.lg : 16
        spacing: 4

        Text {
            text: root.label
            color: theme ? theme.textMuted : "white"
            font.pixelSize: theme ? theme.font(13) : 13
        }

        Text {
            text: root.value
            color: theme ? theme.text : "white"
            font.pixelSize: theme ? theme.font(24) : 24
            font.weight: Font.DemiBold
        }

        Text {
            text: root.detail
            visible: text.length > 0
            color: theme ? theme.textDim : "gray"
            font.pixelSize: theme ? theme.font(12) : 12
        }
    }
}
