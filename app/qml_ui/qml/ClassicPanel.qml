import QtQuick

Rectangle {
    id: panel
    property var theme
    property bool raised: false
    property bool outlined: true

    color: raised ? theme.panelRaised : theme.panel
    border.width: outlined ? 1 : 0
    border.color: raised ? theme.border : theme.borderDark
    radius: theme.panelRadius
}
