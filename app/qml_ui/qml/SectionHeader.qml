import QtQuick

Item {
    id: root
    property var theme
    property string text: ""
    implicitHeight: theme.density === "comfortable" ? 34 : 30

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 1
        anchors.verticalCenter: parent.verticalCenter
        text: root.text
        color: root.theme.textMuted
        font.pixelSize: root.theme.font(9)
        font.weight: Font.DemiBold
        font.letterSpacing: 0
    }
}
