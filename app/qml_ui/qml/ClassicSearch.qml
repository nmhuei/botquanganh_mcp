import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: field
    property var theme
    property int debounceMs: 140
    signal searchRequested(string value)

    Accessible.role: Accessible.EditableText
    Accessible.name: placeholderText
    Accessible.searchEdit: true

    onTextChanged: debounce.restart()

    Timer {
        id: debounce
        interval: field.debounceMs
        repeat: false
        onTriggered: field.searchRequested(field.text)
    }

    implicitHeight: field.theme ? field.theme.controlHeight : 34
    color: field.theme.text
    placeholderTextColor: field.theme.textDim
    selectionColor: field.theme.accent
    selectedTextColor: "#FFFFFF"
    font.pixelSize: field.theme.font(10)
    leftPadding: 13
    rightPadding: 13

    background: Rectangle {
        color: field.activeFocus ? field.theme.panelRaised : field.theme.input
        border.width: field.activeFocus ? 1 : 1
        border.color: field.activeFocus ? field.theme.accent : field.theme.borderDark
        radius: field.theme.smallRadius

        Rectangle {
            visible: field.activeFocus
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: field.theme.accent
            opacity: 0.7
        }
    }
}
