import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var theme
    property string title: ""
    property string detail: ""

    Accessible.role: Accessible.StaticText
    Accessible.name: root.title
    Accessible.description: root.detail

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(Math.max(240, parent.width - 48), 440)
        spacing: 7

        Text {
            text: "—"
            color: root.theme.textDim
            font.pixelSize: root.theme.font(15)
            font.weight: Font.Light
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }

        Text {
            text: root.title
            color: root.theme.text
            font.pixelSize: root.theme.font(11)
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        Text {
            text: root.detail
            color: root.theme.textDim
            font.pixelSize: root.theme.font(9)
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
