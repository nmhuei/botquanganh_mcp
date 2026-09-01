import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    property var theme
    property string iconText: ""
    property bool selected: false
    property bool compact: false

    implicitHeight: 32
    implicitWidth: label.implicitWidth + 24
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.Button
    Accessible.name: text

    contentItem: Text {
        id: label
        Accessible.ignored: true
        text: control.text
        color: control.selected ? control.theme.text : control.theme.textMuted
        font.pixelSize: control.theme.font(10)
        font.weight: control.selected ? Font.DemiBold : Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: 7
        color: control.selected
            ? control.theme.navigationSelected
            : control.hovered
            ? control.theme.hover
            : "transparent"
        border.width: control.activeFocus ? 1 : 0
        border.color: control.theme.accent

        Rectangle {
            visible: control.selected
            width: 16
            height: 2
            radius: 1
            color: control.theme.accent
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
        }
    }
}
