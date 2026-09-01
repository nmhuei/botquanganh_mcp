import QtQuick

Item {
    id: root

    required property var theme
    required property string label
    required property string sortKey
    required property string activeKey
    required property bool descending
    required property string fontFamily
    property bool numeric: false
    signal clicked()

    implicitHeight: 30
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.description: root.activeKey === root.sortKey
        ? (root.descending ? "Sorted descending" : "Sorted ascending")
        : "Activate to sort"
    Accessible.focusable: true
    Accessible.onPressAction: root.clicked()

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            root.clicked()
            event.accepted = true
        }
    }

    Rectangle {
        anchors.fill: parent
        color: mouse.containsMouse ? root.theme.hover : "transparent"
        radius: 6
        border.width: root.activeFocus ? 1 : 0
        border.color: root.theme.accent
    }

    Text {
        anchors.fill: parent
        anchors.leftMargin: 9
        anchors.rightMargin: 9
        text: root.label + (root.activeKey === root.sortKey ? (root.descending ? "  ↓" : "  ↑") : "")
        color: root.activeKey === root.sortKey ? root.theme.text : root.theme.textDim
        font.family: root.fontFamily
        font.pixelSize: root.theme.font(8)
        font.weight: root.activeKey === root.sortKey ? Font.DemiBold : Font.Medium
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: root.numeric ? Text.AlignRight : Text.AlignLeft
        elide: Text.ElideRight
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            root.forceActiveFocus()
            root.clicked()
        }
    }
}
