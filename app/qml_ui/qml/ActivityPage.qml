pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "activityPage"

    required property var theme
    required property var backend
    required property var tr
    required property var labels

    property int inspectorTab: 1
    property bool inspectorOpen: false
    property bool compactLayout: width < 1120

    function operationText() {
        if (inspectorTab === 0) return backend.operationMetadata
        if (inspectorTab === 1) return backend.operationStdout
        if (inspectorTab === 2) return backend.operationStderr
        return backend.operationHuman
    }

    Connections {
        target: root.backend
        function onSelectionChanged() {
            if (root.backend.activePage === "activity" && root.backend.selectedOperationId !== "")
                root.inspectorOpen = true
        }
    }

    Rectangle {
        anchors.fill: parent
        color: root.theme.window

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: root.theme.xl
            anchors.rightMargin: root.theme.xl
            anchors.topMargin: root.theme.lg
            anchors.bottomMargin: root.theme.lg
            spacing: root.theme.md

            RowLayout {
                Layout.fillWidth: true
                spacing: root.theme.md

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: root.tr("Activity", "Hoạt động")
                        color: root.theme.text
                        font.pixelSize: root.theme.font(18)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: root.tr(
                            "Live command activity across host workspaces.",
                            "Hoạt động lệnh trực tiếp trên các workspace."
                        )
                        color: root.theme.textMuted
                        font.pixelSize: root.theme.font(9)
                    }
                }

                Text {
                    text: root.backend.visibleOperationCount + root.tr(" operations", " tác vụ")
                    color: root.theme.textDim
                    font.pixelSize: root.theme.font(9)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: root.theme.md

                ClassicPanel {
                    id: sessionPane
                    visible: !(root.compactLayout && root.inspectorOpen)
                    Layout.preferredWidth: root.compactLayout ? 198 : 226
                    Layout.minimumWidth: root.compactLayout ? 198 : 210
                    Layout.fillHeight: true
                    theme: root.theme
                    raised: false
                    outlined: false
                    color: "transparent"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: root.theme.sm
                        spacing: root.theme.sm

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: root.tr("Workspaces", "Workspace")
                                color: root.theme.text
                                font.pixelSize: root.theme.font(10)
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                            Text {
                                text: root.backend.sessionVisibleCount + "/" + root.backend.sessionTotalCount
                                color: root.theme.textDim
                                font.pixelSize: root.theme.font(8)
                            }
                        }

                        ClassicSearch {
                            id: sessionSearch
                            objectName: "sessionSearch"
                            theme: root.theme
                            Layout.fillWidth: true
                            placeholderText: root.tr("Find workspace…", "Tìm workspace…")
                            onSearchRequested: function(value) {
                                root.backend.setSessionSearch(value)
                            }
                        }

                        ClassicButton {
                            theme: root.theme
                            quiet: true
                            text: root.tr("All workspaces", "Tất cả workspace")
                            Layout.fillWidth: true
                            primary: root.backend.selectedSessionId === ""
                            onClicked: root.backend.showAllSessions()
                        }

                        ListView {
                            id: sessionList
                            objectName: "sessionList"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: root.backend.sessionsModel
                            clip: true
                            reuseItems: true
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                            delegate: Rectangle {
                                id: sessionRow
                                required property int index
                                required property string chatId
                                required property string displayName
                                required property string sessionState
                                required property int unread
                                required property bool running
                                required property bool tracked

                                width: sessionList.width
                                height: root.theme.rowHeight + 4
                                radius: root.theme.smallRadius
                                color: root.backend.selectedSessionId === sessionRow.chatId
                                    ? root.theme.navigationSelected
                                    : sessionMouse.containsMouse
                                    ? root.theme.rowHover
                                    : "transparent"
                                opacity: sessionRow.tracked ? 1.0 : 0.64

                                Accessible.role: Accessible.ListItem
                                Accessible.name: sessionRow.displayName
                                Accessible.description: sessionRow.sessionState
                                Accessible.selected: root.backend.selectedSessionId === sessionRow.chatId

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: root.theme.sm
                                    anchors.rightMargin: root.theme.sm
                                    spacing: root.theme.sm

                                    Rectangle {
                                        Layout.preferredWidth: 7
                                        Layout.preferredHeight: 7
                                        radius: 4
                                        color: sessionRow.running
                                            ? root.theme.warning
                                            : sessionRow.tracked
                                            ? root.theme.success
                                            : root.theme.textDim
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 0
                                        Text {
                                            text: sessionRow.displayName
                                            color: root.theme.text
                                            font.pixelSize: root.theme.font(9)
                                            font.weight: root.backend.selectedSessionId === sessionRow.chatId
                                                ? Font.DemiBold : Font.Medium
                                            Layout.fillWidth: true
                                            elide: Text.ElideMiddle
                                        }
                                        Text {
                                            text: sessionRow.sessionState
                                            color: root.theme.textDim
                                            font.pixelSize: root.theme.font(8)
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }
                                    }

                                    Rectangle {
                                        visible: sessionRow.unread > 0
                                        Layout.preferredWidth: Math.max(20, unreadText.implicitWidth + 10)
                                        Layout.preferredHeight: 20
                                        radius: 10
                                        color: root.theme.infoBg

                                        Text {
                                            id: unreadText
                                            anchors.centerIn: parent
                                            text: sessionRow.unread
                                            color: root.theme.info
                                            font.pixelSize: root.theme.font(8)
                                            font.weight: Font.DemiBold
                                        }
                                    }
                                }

                                MouseArea {
                                    id: sessionMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        sessionList.currentIndex = sessionRow.index
                                        root.backend.selectSession(sessionRow.chatId)
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: root.theme.xs

                            Text {
                                text: root.backend.selectedSessionId === ""
                                    ? root.tr("All selected", "Đang chọn tất cả")
                                    : root.backend.selectedSessionId
                                color: root.theme.textDim
                                font.pixelSize: root.theme.font(8)
                                Layout.fillWidth: true
                                elide: Text.ElideMiddle
                            }

                            ClassicButton {
                                objectName: "sessionMenuButton"
                                theme: root.theme
                                quiet: true
                                text: "•••"
                                implicitWidth: 38
                                enabled: root.backend.selectedSessionId !== ""
                                onClicked: sessionMenu.open()
                            }
                        }
                    }
                }

                ClassicPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 400
                    theme: root.theme
                    raised: false
                    outlined: false

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: root.theme.sm
                            Layout.rightMargin: root.theme.sm
                            Layout.topMargin: root.theme.sm
                            Layout.bottomMargin: root.theme.sm
                            spacing: root.theme.sm

                            ClassicSearch {
                                id: operationSearch
                                objectName: "operationSearch"
                                theme: root.theme
                                Layout.fillWidth: true
                                Layout.maximumWidth: 420
                                placeholderText: root.tr("Search commands…", "Tìm command…")
                                onSearchRequested: function(value) {
                                    root.backend.setOperationSearch(value)
                                }
                            }

                            Item { Layout.fillWidth: true }

                            ClassicButton {
                                theme: root.theme
                                quiet: true
                                text: "↻"
                                implicitWidth: 38
                                Accessible.name: root.tr("Refresh activity", "Làm mới hoạt động")
                                onClicked: root.backend.refreshNow()
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: root.theme.borderDark
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: root.theme.xs
                            Layout.rightMargin: root.theme.xs
                            spacing: 0

                            SortHeader {
                                id: utcHeader
                                objectName: "sortUtcHeader"
                                theme: root.theme
                                label: root.tr("Time", "Thời gian")
                                sortKey: "utc"
                                activeKey: root.backend.operationSortKey
                                descending: root.backend.operationSortDescending
                                fontFamily: root.backend.uiFontFamily
                                Layout.preferredWidth: root.compactLayout ? 104 : 132
                                onClicked: root.backend.toggleOperationSort(sortKey)
                            }
                            SortHeader {
                                id: statusHeader
                                objectName: "sortStatusHeader"
                                theme: root.theme
                                label: root.tr("Status", "Trạng thái")
                                sortKey: "status"
                                activeKey: root.backend.operationSortKey
                                descending: root.backend.operationSortDescending
                                fontFamily: root.backend.uiFontFamily
                                Layout.preferredWidth: 92
                                onClicked: root.backend.toggleOperationSort(sortKey)
                            }
                            SortHeader {
                                id: commandHeader
                                objectName: "sortCommandHeader"
                                theme: root.theme
                                label: root.tr("Command", "Lệnh")
                                sortKey: "command"
                                activeKey: root.backend.operationSortKey
                                descending: root.backend.operationSortDescending
                                fontFamily: root.backend.uiFontFamily
                                Layout.fillWidth: true
                                onClicked: root.backend.toggleOperationSort(sortKey)
                            }
                            SortHeader {
                                visible: !root.compactLayout
                                objectName: "sortExitHeader"
                                theme: root.theme
                                label: "Exit"
                                sortKey: "exit"
                                activeKey: root.backend.operationSortKey
                                descending: root.backend.operationSortDescending
                                fontFamily: root.backend.uiFontFamily
                                numeric: true
                                Layout.preferredWidth: 62
                                onClicked: root.backend.toggleOperationSort(sortKey)
                            }
                            SortHeader {
                                objectName: "sortDurationHeader"
                                theme: root.theme
                                label: root.tr("Duration", "Thời lượng")
                                sortKey: "duration"
                                activeKey: root.backend.operationSortKey
                                descending: root.backend.operationSortDescending
                                fontFamily: root.backend.uiFontFamily
                                numeric: true
                                Layout.preferredWidth: root.compactLayout ? 74 : 86
                                onClicked: root.backend.toggleOperationSort(sortKey)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: root.theme.borderDark
                        }

                        ListView {
                            id: operationList
                            objectName: "operationList"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: root.backend.operationsModel
                            reuseItems: true
                            activeFocusOnTab: true
                            keyNavigationEnabled: true
                            boundsBehavior: Flickable.StopAtBounds
                            property bool followLive: true
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                            onCurrentIndexChanged: {
                                if (activeFocus && currentIndex >= 0)
                                    root.backend.selectOperationAt(currentIndex)
                            }
                            onMovementEnded: {
                                followLive = contentY <= 2
                                root.backend.setActivityAtLiveEdge(followLive)
                            }
                            onCountChanged: {
                                if (followLive) {
                                    Qt.callLater(function() {
                                        operationList.positionViewAtBeginning()
                                        root.backend.setActivityAtLiveEdge(true)
                                    })
                                }
                            }

                            delegate: Rectangle {
                                id: operationRow
                                required property int index
                                required property string operationId
                                required property string utc
                                required property string status
                                required property string command
                                required property string exit
                                required property string duration
                                required property string chatId

                                width: operationList.width
                                height: root.theme.rowHeight
                                color: root.backend.selectedOperationId === operationRow.operationId
                                    ? root.theme.navigationSelected
                                    : operationMouse.containsMouse
                                    ? root.theme.rowHover
                                    : "transparent"

                                Accessible.role: Accessible.ListItem
                                Accessible.name: operationRow.status + ", " + operationRow.command
                                Accessible.selected: root.backend.selectedOperationId === operationRow.operationId

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: root.theme.md
                                    anchors.rightMargin: root.theme.sm
                                    spacing: 0

                                    Text {
                                        text: operationRow.utc
                                        color: root.theme.textDim
                                        font.family: root.backend.monoFontFamily
                                        font.pixelSize: root.theme.font(8)
                                        Layout.preferredWidth: root.compactLayout ? 100 : 128
                                        elide: Text.ElideRight
                                    }

                                    RowLayout {
                                        Layout.preferredWidth: 92
                                        spacing: 6
                                        Rectangle {
                                            Layout.preferredWidth: 7
                                            Layout.preferredHeight: 7
                                            radius: 4
                                            color: operationRow.status === "failed" || operationRow.status === "timed_out"
                                                ? root.theme.error
                                                : operationRow.status === "running"
                                                ? root.theme.warning
                                                : root.theme.success
                                        }
                                        Text {
                                            text: root.labels.operationStatus(operationRow.status)
                                            color: operationRow.status === "failed" || operationRow.status === "timed_out"
                                                ? root.theme.error
                                                : operationRow.status === "running"
                                                ? root.theme.warning
                                                : root.theme.textMuted
                                            font.pixelSize: root.theme.font(8)
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }
                                    }

                                    Text {
                                        text: operationRow.command ? operationRow.command.replace(/\n+/g, " ↵ ") : ""
                                        color: root.theme.text
                                        font.family: root.backend.monoFontFamily
                                        font.pixelSize: root.theme.font(9)
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                        maximumLineCount: 1
                                    }


                                    Text {
                                        visible: !root.compactLayout
                                        text: operationRow.exit
                                        color: root.theme.textDim
                                        font.family: root.backend.monoFontFamily
                                        font.pixelSize: root.theme.font(8)
                                        horizontalAlignment: Text.AlignRight
                                        Layout.preferredWidth: 62
                                    }

                                    Text {
                                        text: operationRow.duration + " ms"
                                        color: root.theme.textMuted
                                        font.family: root.backend.monoFontFamily
                                        font.pixelSize: root.theme.font(8)
                                        horizontalAlignment: Text.AlignRight
                                        Layout.preferredWidth: root.compactLayout ? 74 : 86
                                    }
                                }

                                MouseArea {
                                    id: operationMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        operationList.currentIndex = operationRow.index
                                        root.backend.selectOperation(operationRow.operationId)
                                        root.inspectorOpen = true
                                    }
                                }
                            }

                            EmptyState {
                                anchors.fill: parent
                                visible: operationList.count === 0
                                theme: root.theme
                                title: root.tr("No activity", "Chưa có hoạt động")
                                detail: root.tr(
                                    "Commands will appear here as they run.",
                                    "Lệnh sẽ xuất hiện tại đây khi được chạy."
                                )
                            }
                        }

                        ClassicButton {
                            visible: root.backend.activityNewCount > 0
                            theme: root.theme
                            primary: true
                            text: "↓ " + root.backend.activityNewCount + " " + root.tr("new", "mới")
                            Layout.alignment: Qt.AlignHCenter
                            Layout.bottomMargin: root.theme.sm
                            onClicked: {
                                operationList.followLive = true
                                operationList.positionViewAtBeginning()
                                root.backend.setActivityAtLiveEdge(true)
                                root.backend.clearActivityNewCount()
                            }
                        }
                    }
                }

                ClassicPanel {
                    visible: root.inspectorOpen
                    Layout.preferredWidth: root.compactLayout ? 330 : 410
                    Layout.minimumWidth: root.compactLayout ? 320 : 360
                    Layout.fillHeight: true
                    theme: root.theme
                    raised: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: root.theme.md
                            Layout.rightMargin: root.theme.sm
                            Layout.topMargin: root.theme.sm
                            Layout.bottomMargin: root.theme.sm
                            spacing: root.theme.sm

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Text {
                                    text: root.tr("Operation", "Tác vụ")
                                    color: root.theme.textDim
                                    font.pixelSize: root.theme.font(8)
                                }
                                Text {
                                    text: root.backend.selectedOperationId
                                    color: root.theme.text
                                    font.family: root.backend.monoFontFamily
                                    font.pixelSize: root.theme.font(9)
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                    elide: Text.ElideMiddle
                                }
                            }

                            ClassicButton {
                                theme: root.theme
                                quiet: true
                                text: "×"
                                implicitWidth: 36
                                onClicked: root.inspectorOpen = false
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: root.theme.borderDark
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: root.theme.sm
                            Layout.rightMargin: root.theme.sm
                            Layout.topMargin: root.theme.sm
                            Layout.bottomMargin: root.theme.sm
                            spacing: 2

                            Repeater {
                                model: [
                                    root.tr("Metadata", "Metadata"),
                                    "STDOUT",
                                    "STDERR",
                                    root.tr("Human-readable", "Dễ đọc")
                                ]

                                ClassicButton {
                                    required property int index
                                    required property string modelData
                                    theme: root.theme
                                    text: modelData
                                    quiet: root.inspectorTab !== index
                                    primary: root.inspectorTab === index
                                    implicitWidth: 0
                                    Layout.fillWidth: true
                                    onClicked: root.inspectorTab = index
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.leftMargin: root.theme.sm
                            Layout.rightMargin: root.theme.sm
                            Layout.bottomMargin: root.theme.sm
                            color: root.theme.inspector
                            radius: root.theme.smallRadius
                            border.width: 1
                            border.color: root.theme.borderDark

                            ScrollView {
                                anchors.fill: parent
                                anchors.margins: root.theme.sm
                                clip: true
                                ScrollBar.vertical.policy: ScrollBar.AsNeeded
                                ScrollBar.horizontal.policy: ScrollBar.AsNeeded

                                TextArea {
                                    text: root.operationText()
                                    color: root.theme.text
                                    selectionColor: root.theme.accent
                                    selectedTextColor: "#FFFFFF"
                                    readOnly: true
                                    wrapMode: TextEdit.NoWrap
                                    font.family: root.backend.monoFontFamily
                                    font.pixelSize: root.theme.font(9)
                                    background: null
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: root.theme.sm
                            Layout.rightMargin: root.theme.sm
                            Layout.bottomMargin: root.theme.sm
                            spacing: root.theme.xs

                            ClassicButton {
                                objectName: "relatedLogsButton"
                                theme: root.theme
                                quiet: true
                                text: root.tr("Related logs", "Log liên quan")
                                enabled: root.backend.selectedOperationId !== ""
                                Layout.fillWidth: true
                                onClicked: root.backend.showRelatedLogsForSelectedOperation()
                            }

                            ClassicButton {
                                theme: root.theme
                                quiet: true
                                text: root.tr("Copy tab", "Sao chép tab")
                                onClicked: root.backend.copyText(root.operationText())
                            }
                        }
                    }
                }
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+F"
        context: Qt.ApplicationShortcut
        enabled: root.backend.activePage === "activity"
        onActivated: operationSearch.forceActiveFocus()
    }
    Shortcut {
        sequence: "/"
        context: Qt.ApplicationShortcut
        enabled: root.backend.activePage === "activity"
        onActivated: operationSearch.forceActiveFocus()
    }
    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        enabled: root.backend.activePage === "activity"
        onActivated: {
            if (root.inspectorOpen) {
                root.inspectorOpen = false
            } else {
                operationSearch.text = ""
                sessionSearch.text = ""
                root.backend.setOperationSearch("")
                root.backend.setSessionSearch("")
            }
        }
    }

    Popup {
        id: sessionMenu
        x: root.theme.xl + 12
        y: Math.max(root.theme.headerHeight, root.height - 220)
        width: 200
        padding: root.theme.sm
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: root.theme.panelRaised
            radius: root.theme.popupRadius
            border.width: 1
            border.color: root.theme.border
        }

        contentItem: ColumnLayout {
            spacing: 2

            ClassicButton {
                theme: root.theme
                quiet: true
                alignLeft: true
                text: root.tr("Track", "Theo dõi")
                Layout.fillWidth: true
                enabled: root.backend.selectedSessionId !== ""
                onClicked: {
                    sessionMenu.close()
                    root.backend.enableSelectedSession()
                }
            }
            ClassicButton {
                theme: root.theme
                quiet: true
                alignLeft: true
                text: root.tr("Mute", "Tắt theo dõi")
                Layout.fillWidth: true
                enabled: root.backend.selectedSessionId !== ""
                onClicked: {
                    sessionMenu.close()
                    root.backend.disableSelectedSession()
                }
            }
            ClassicButton {
                theme: root.theme
                quiet: true
                alignLeft: true
                text: root.tr("Hide", "Ẩn")
                Layout.fillWidth: true
                enabled: root.backend.selectedSessionId !== ""
                onClicked: {
                    sessionMenu.close()
                    root.backend.closeSelectedSession()
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: root.theme.borderDark
            }
            ClassicButton {
                theme: root.theme
                quiet: true
                alignLeft: true
                text: root.tr("Rescan folders", "Quét lại thư mục")
                Layout.fillWidth: true
                onClicked: {
                    sessionMenu.close()
                    root.backend.refreshNow()
                }
            }
        }
    }
}
