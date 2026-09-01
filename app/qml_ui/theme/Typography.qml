pragma Singleton
import QtQuick

QtObject {
    property string family: "Noto Sans"
    readonly property int display: 32
    readonly property int pageTitle: 24
    readonly property int section: 18
    readonly property int cardTitle: 16
    readonly property int body: 15
    readonly property int secondary: 13
    readonly property int caption: 12
    readonly property int titleWeight: Font.DemiBold
    readonly property int bodyWeight: Font.Normal
}
