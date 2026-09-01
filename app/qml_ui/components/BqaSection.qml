import QtQuick

Column {
    property string title: ""
    spacing: 12

    Text {
        text: parent.title
        color: "#F4F7FB"
        font.pixelSize: 18
        font.bold: true
    }

    default property alias content: body.data
    Column { id: body; spacing: 8 }
}
