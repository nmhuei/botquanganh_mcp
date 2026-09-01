import QtQuick

Rectangle {
    id: root
    property alias title: titleLabel.text
    property alias content: content.data
    property color backgroundColor: "#202631"
    property color borderColor: "#343B48"
    property int radius: 12

    color: backgroundColor
    border.color: borderColor
    radius: root.radius
    implicitHeight: content.implicitHeight + titleLabel.height + 32

    Column {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Text {
            id: titleLabel
            color: "#F4F7FB"
            font.pixelSize: 16
            font.bold: true
        }

        Column { id: content; spacing: 8 }
    }
}
