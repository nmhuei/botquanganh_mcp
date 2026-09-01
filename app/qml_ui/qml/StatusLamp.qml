import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var theme
    property string text: ""
    property string tone: "success"

    implicitHeight: 28
    implicitWidth: content.implicitWidth + 4

    Accessible.role: Accessible.StaticText
    Accessible.name: text

    RowLayout {
        id: content
        anchors.centerIn: parent
        spacing: 7

        Rectangle {
            Accessible.ignored: true
            Layout.preferredWidth: 8
            Layout.preferredHeight: 8
            radius: 4
            color: root.theme.toneColor(root.tone)

            Rectangle {
                anchors.centerIn: parent
                width: 14
                height: 14
                radius: 7
                color: "transparent"
                border.width: 1
                border.color: Qt.rgba(
                    root.theme.toneColor(root.tone).r,
                    root.theme.toneColor(root.tone).g,
                    root.theme.toneColor(root.tone).b,
                    0.25
                )
            }
        }

        Text {
            Accessible.ignored: true
            text: root.text
            color: root.tone === "success" ? root.theme.textMuted : root.theme.text
            font.pixelSize: root.theme.font(9)
            font.weight: Font.DemiBold
        }
    }
}
