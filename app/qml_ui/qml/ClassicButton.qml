import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    property var theme
    property bool primary: false
    property bool danger: false
    property bool quiet: false
    property bool alignLeft: false
    property bool compact: false

    implicitHeight: compact ? 30 : (control.theme ? control.theme.controlHeight : 34)
    implicitWidth: Math.max(compact ? 54 : 68, contentItem.implicitWidth + (compact ? 18 : 24))
    leftPadding: compact ? 9 : 12
    rightPadding: compact ? 9 : 12
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.Button
    Accessible.name: text

    contentItem: Text {
        Accessible.ignored: true
        text: control.text
        color: !control.enabled
            ? control.theme.disabledText
            : control.primary
            ? "#FFFFFF"
            : control.danger
            ? (control.hovered ? "#FFFFFF" : control.theme.error)
            : control.theme.text
        font.pixelSize: control.theme.font(control.compact ? 9 : 10)
        font.weight: control.primary ? Font.DemiBold : Font.Medium
        horizontalAlignment: control.alignLeft ? Text.AlignLeft : Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: control.theme.smallRadius
        color: !control.enabled
            ? "transparent"
            : control.primary
            ? (control.pressed ? control.theme.accentDark : control.hovered ? control.theme.accentLight : control.theme.accent)
            : control.danger
            ? (control.pressed ? control.theme.errorBg : control.hovered ? control.theme.error : "transparent")
            : control.quiet
            ? (control.pressed ? control.theme.panelDark : control.hovered ? control.theme.hover : "transparent")
            : (control.pressed ? control.theme.panelDark : control.hovered ? control.theme.hover : control.theme.panelRaised)
        border.width: control.activeFocus ? 2 : ((!control.quiet && !control.primary) ? 1 : 0)
        border.color: control.activeFocus
            ? control.theme.accent
            : control.danger
            ? control.theme.error
            : control.theme.border

        Rectangle {
            visible: control.primary && control.enabled && !control.pressed
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            radius: parent.radius
            color: Qt.rgba(1, 1, 1, control.hovered ? 0.22 : 0.14)
        }
    }
}
