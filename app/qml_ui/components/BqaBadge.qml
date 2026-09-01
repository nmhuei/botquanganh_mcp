import QtQuick

Rectangle {
    property string text: ""
    property color foreground: "#F4F7FB"
    property color background: "#283140"
    radius: 8
    height: 24
    width: label.implicitWidth + 20
    color: background

    Text {
        id: label
        anchors.centerIn: parent
        text: parent.text
        color: parent.foreground
        font.pixelSize: 12
    }
}
