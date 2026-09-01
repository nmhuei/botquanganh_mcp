pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "logsPage"

    required property var theme
    required property var backend
    required property var tr
    required property var labels

    property int detailTab: 0
    property bool inspectorOpen: false
    property string runtimeSelectedLine: ""
    property string runtimeSelectedSource: ""
    property string runtimeSelectedTime: ""
    property bool compactLayout: width < 1120

    function detailText() {
        if (detailTab === 0) return backend.logSummary
        if (detailTab === 1) return backend.logMetadata
        return backend.logPayload
    }

    function filtersActive() {
        if (backend.logsMode === "runtime")
            return backend.runtimeLogSource !== "all"
        return backend.logCategoryFilter !== "all" || backend.logOutcomeFilter !== "all"
    }

    Connections {
        target: root.backend
        function onSelectionChanged() {
            if (root.backend.activePage === "logs" && root.backend.selectedLogId !== "")
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
                        text: root.tr("Logs", "Nhật ký")
                        color: root.theme.text
                        font.pixelSize: root.theme.font(18)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: root.tr(
                            "Evidence for events and runtime services.",
                            "Bằng chứng sự kiện và dịch vụ runtime."
                        )
                        color: root.theme.textMuted
                        font.pixelSize: root.theme.font(13)
                    }
                }

                RowLayout {
                    spacing: 2
                    NavItem {
                        objectName: "logsEventsMode"
                        theme: root.theme
                        text: root.tr("Events", "Sự kiện")
                        selected: root.backend.logsMode === "events"
                        onClicked: {
                            root.backend.setLogsMode("events")
                            root.inspectorOpen = false
                        }
                    }
                    NavItem {
                        objectName: "logsRuntimeMode"
                        theme: root.theme
                        text: root.tr("Runtime", "Runtime")
                        selected: root.backend.logsMode === "runtime"
                        onClicked: {
                            root.backend.setLogsMode("runtime")
                            root.inspectorOpen = false
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: root.theme.md

                ClassicPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 520
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
                                id: eventSearch
                                objectName: "eventLogSearch"
                                visible: root.backend.logsMode === "events"
                                theme: root.theme
                                Layout.fillWidth: true
                                Layout.maximumWidth: 430
                                placeholderText: root.tr("Search events…", "Tìm sự kiện…")
                                onSearchRequested: function(value) {
                                    root.backend.setLogSearch(value)
                                }
                            }

                            ClassicSearch {
                                id: runtimeSearch
                                objectName: "runtimeLogSearch"
                                visible: root.backend.logsMode === "runtime"
                                theme: root.theme
                                Layout.fillWidth: true
                                Layout.maximumWidth: 430
                                placeholderText: root.tr("Search runtime logs…", "Tìm runtime log…")
                                onSearchRequested: function(value) {
                                    root.backend.setRuntimeLogSearch(value)
                                }
                            }

                            Item { Layout.fillWidth: true }

                            ClassicButton {
                                objectName: "logsFilterButton"
                                theme: root.theme
                                quiet: !root.filtersActive()
                                primary: root.filtersActive()
                                text: root.filtersActive()
                                    ? root.tr("Filter · active", "Lọc · đang bật")
                                    : root.tr("Filter", "Lọc")
                                onClicked: filterPopup.open()
                            }

                            ClassicButton {
                                visible: root.backend.logsMode === "runtime"
                                theme: root.theme
                                quiet: true
                                text: "↻"
                                implicitWidth: 38
                                Accessible.name: root.tr("Refresh runtime logs", "Làm mới runtime log")
                                onClicked: root.backend.refreshRuntimeLogs()
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: root.theme.borderDark
                        }

                        StackLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            currentIndex: root.backend.logsMode === "runtime" ? 1 : 0

                            Item {
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 0

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: root.theme.xs
                                        Layout.rightMargin: root.theme.xs
                                        spacing: 0

                                        Item {
                                            Layout.preferredWidth: 118
                                            Layout.preferredHeight: 30
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                text: root.tr("Time", "Thời gian")
                                                color: root.theme.textMuted
                                                font.pixelSize: root.theme.font(13)
                                                font.weight: Font.Medium
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                        }
                                        Item {
                                            Layout.preferredWidth: 82
                                            Layout.preferredHeight: 30
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                text: root.tr("Level", "Mức")
                                                color: root.theme.textMuted
                                                font.pixelSize: root.theme.font(13)
                                                font.weight: Font.Medium
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                        }
                                        Item {
                                            Layout.preferredWidth: root.compactLayout ? 132 : 170
                                            Layout.preferredHeight: 30
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                text: root.tr("Action", "Hành động")
                                                color: root.theme.textMuted
                                                font.pixelSize: root.theme.font(13)
                                                font.weight: Font.Medium
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                        }
                                        Item {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 30
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                text: root.tr("Summary", "Tóm tắt")
                                                color: root.theme.textMuted
                                                font.pixelSize: root.theme.font(13)
                                                font.weight: Font.Medium
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                        }
                                        Item {
                                            visible: !root.compactLayout
                                            Layout.preferredWidth: 118
                                            Layout.preferredHeight: 30
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                text: root.tr("Workspace", "Workspace")
                                                color: root.theme.textMuted
                                                font.pixelSize: root.theme.font(13)
                                                font.weight: Font.Medium
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 1
                                        color: root.theme.borderDark
                                    }

                                    ListView {
                                        id: eventList
                                        objectName: "eventLogList"
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        model: root.backend.logsModel
                                        clip: true
                                        reuseItems: true
                                        activeFocusOnTab: true
                                        keyNavigationEnabled: true
                                        boundsBehavior: Flickable.StopAtBounds
                                        property bool followLive: true
                                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                                        onCurrentIndexChanged: {
                                            if (activeFocus && currentIndex >= 0)
                                                root.backend.selectLogAt(currentIndex)
                                        }
                                        onMovementEnded: {
                                            followLive = contentY <= 2
                                            root.backend.setLogsAtLiveEdge(followLive)
                                        }
                                        onCountChanged: {
                                            if (followLive) {
                                                Qt.callLater(function() {
                                                    eventList.positionViewAtBeginning()
                                                    root.backend.setLogsAtLiveEdge(true)
                                                })
                                            }
                                        }

                                        delegate: Rectangle {
                                            id: eventRow
                                            required property int index
                                            required property string eventId
                                            required property string utc
                                            required property string severity
                                            required property string category
                                            required property string action
                                            required property string outcome
                                            required property string duration
                                            required property string chatId
                                            required property string operationId
                                            required property string summary

                                            width: eventList.width
                                            height: root.theme.rowHeight
                                            color: root.backend.selectedLogId === eventRow.eventId
                                                ? root.theme.navigationSelected
                                                : eventMouse.containsMouse
                                                ? root.theme.rowHover
                                                : "transparent"

                                            Accessible.role: Accessible.ListItem
                                            Accessible.name: eventRow.severity + ", " + eventRow.action
                                            Accessible.description: eventRow.summary
                                            Accessible.selected: root.backend.selectedLogId === eventRow.eventId

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: root.theme.md
                                                anchors.rightMargin: root.theme.sm
                                                spacing: 0

                                                Text {
                                                    text: eventRow.utc
                                                    color: root.theme.textDim
                                                    font.family: root.backend.monoFontFamily
                                                    font.pixelSize: root.theme.font(8)
                                                    Layout.preferredWidth: 110
                                                    elide: Text.ElideRight
                                                }

                                                RowLayout {
                                                    Layout.preferredWidth: 82
                                                    spacing: 6
                                                    Rectangle {
                                                        Layout.preferredWidth: 7
                                                        Layout.preferredHeight: 7
                                                        radius: 4
                                                        color: eventRow.severity === "ERROR" || eventRow.outcome === "failure"
                                                            ? root.theme.error
                                                            : eventRow.severity === "WARNING"
                                                            ? root.theme.warning
                                                            : root.theme.info
                                                    }
                                                    Text {
                                                        text: eventRow.severity
                                                        color: eventRow.severity === "ERROR" || eventRow.outcome === "failure"
                                                            ? root.theme.error
                                                            : eventRow.severity === "WARNING"
                                                            ? root.theme.warning
                                                            : root.theme.textMuted
                                                        font.pixelSize: root.theme.font(8)
                                                        font.weight: Font.DemiBold
                                                    }
                                                }

                                                Text {
                                                    text: eventRow.action
                                                    color: root.theme.text
                                                    font.family: root.backend.monoFontFamily
                                                    font.pixelSize: root.theme.font(8)
                                                    Layout.preferredWidth: root.compactLayout ? 124 : 162
                                                    elide: Text.ElideRight
                                                }

                                                Text {
                                                    text: eventRow.summary ? eventRow.summary.replace(/\n+/g, " · ") : ""
                                                    color: root.theme.textMuted
                                                    font.pixelSize: root.theme.font(8)
                                                    Layout.fillWidth: true
                                                    elide: Text.ElideRight
                                                    maximumLineCount: 1
                                                }


                                                Text {
                                                    visible: !root.compactLayout
                                                    text: eventRow.chatId
                                                    color: root.theme.textDim
                                                    font.pixelSize: root.theme.font(8)
                                                    Layout.preferredWidth: 110
                                                    elide: Text.ElideMiddle
                                                }
                                            }

                                            MouseArea {
                                                id: eventMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    eventList.currentIndex = eventRow.index
                                                    root.backend.selectLog(eventRow.eventId)
                                                    root.inspectorOpen = true
                                                }
                                            }
                                        }

                                        EmptyState {
                                            anchors.fill: parent
                                            visible: eventList.count === 0
                                            theme: root.theme
                                            title: root.tr("No matching events", "Không có sự kiện phù hợp")
                                            detail: root.tr(
                                                "Try clearing the current filters or search.",
                                                "Hãy thử xóa bộ lọc hoặc nội dung tìm kiếm."
                                            )
                                        }
                                    }

                                    ClassicButton {
                                        visible: root.backend.logsNewCount > 0
                                        theme: root.theme
                                        primary: true
                                        text: "↓ " + root.backend.logsNewCount + " " + root.tr("new events", "sự kiện mới")
                                        Layout.alignment: Qt.AlignHCenter
                                        Layout.bottomMargin: root.theme.sm
                                        onClicked: {
                                            eventList.followLive = true
                                            eventList.positionViewAtBeginning()
                                            root.backend.setLogsAtLiveEdge(true)
                                            root.backend.clearLogsNewCount()
                                        }
                                    }
                                }
                            }

                            Item {
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 0

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: root.theme.md
                                        Layout.rightMargin: root.theme.md
                                        Layout.preferredHeight: 30
                                        spacing: root.theme.md

                                        Text {
                                            text: root.tr("Source", "Nguồn")
                                            color: root.theme.textMuted
                                            font.pixelSize: root.theme.font(13)
                                            font.weight: Font.Medium
                                            Layout.preferredWidth: 104
                                        }
                                        Text {
                                            text: root.tr("Time", "Thời gian")
                                            color: root.theme.textMuted
                                            font.pixelSize: root.theme.font(13)
                                            font.weight: Font.Medium
                                            Layout.preferredWidth: 136
                                        }
                                        Text {
                                            text: root.tr("Message", "Nội dung")
                                            color: root.theme.textMuted
                                            font.pixelSize: root.theme.font(13)
                                            font.weight: Font.Medium
                                            Layout.fillWidth: true
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 1
                                        color: root.theme.borderDark
                                    }

                                    ListView {
                                        id: runtimeList
                                        objectName: "runtimeLogList"
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        model: root.backend.runtimeLogsModel
                                        clip: true
                                        reuseItems: true
                                        boundsBehavior: Flickable.StopAtBounds
                                        activeFocusOnTab: true
                                        keyNavigationEnabled: true
                                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                                        delegate: Rectangle {
                                            id: runtimeRow
                                            required property int index
                                            required property string source
                                            required property string timestamp
                                            required property string line

                                            width: runtimeList.width
                                            height: root.theme.rowHeight
                                            color: runtimeList.currentIndex === runtimeRow.index
                                                ? root.theme.navigationSelected
                                                : runtimeMouse.containsMouse
                                                ? root.theme.rowHover
                                                : "transparent"

                                            ListView.onIsCurrentItemChanged: {
                                                if (ListView.isCurrentItem && runtimeList.activeFocus) {
                                                    root.runtimeSelectedLine = runtimeRow.line
                                                    root.runtimeSelectedSource = runtimeRow.source
                                                    root.runtimeSelectedTime = runtimeRow.timestamp
                                                    root.inspectorOpen = true
                                                }
                                            }

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: root.theme.md
                                                anchors.rightMargin: root.theme.md
                                                spacing: root.theme.md

                                                Text {
                                                    text: runtimeRow.source
                                                    color: root.theme.info
                                                    font.family: root.backend.monoFontFamily
                                                    font.pixelSize: root.theme.font(8)
                                                    font.weight: Font.DemiBold
                                                    Layout.preferredWidth: 92
                                                    elide: Text.ElideRight
                                                }
                                                Text {
                                                    text: runtimeRow.timestamp
                                                    color: root.theme.textDim
                                                    font.family: root.backend.monoFontFamily
                                                    font.pixelSize: root.theme.font(8)
                                                    Layout.preferredWidth: 124
                                                    elide: Text.ElideRight
                                                }
                                                Text {
                                                    text: runtimeRow.line
                                                    color: runtimeRow.line.toLowerCase().includes("error")
                                                        ? root.theme.error
                                                        : runtimeRow.line.toLowerCase().includes("warning")
                                                        ? root.theme.warning
                                                        : root.theme.textMuted
                                                    font.family: root.backend.monoFontFamily
                                                    font.pixelSize: root.theme.font(8)
                                                    Layout.fillWidth: true
                                                    elide: Text.ElideRight
                                                }
                                            }

                                            MouseArea {
                                                id: runtimeMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    root.runtimeSelectedLine = runtimeRow.line
                                                    root.runtimeSelectedSource = runtimeRow.source
                                                    root.runtimeSelectedTime = runtimeRow.timestamp
                                                    root.inspectorOpen = true
                                                }
                                            }
                                        }

                                        EmptyState {
                                            anchors.fill: parent
                                            visible: runtimeList.count === 0
                                            theme: root.theme
                                            title: root.tr("No runtime logs", "Không có runtime log")
                                            detail: root.tr(
                                                "Refresh the snapshot or change the current source filter.",
                                                "Làm mới snapshot hoặc đổi bộ lọc nguồn."
                                            )
                                        }
                                    }

                                    Text {
                                        visible: root.backend.lastRuntimeLogRefreshTime.length > 0
                                        text: root.tr("Snapshot ", "Snapshot ") + root.backend.lastRuntimeLogRefreshTime
                                        color: root.theme.textDim
                                        font.pixelSize: root.theme.font(8)
                                        Layout.leftMargin: root.theme.md
                                        Layout.bottomMargin: root.theme.sm
                                    }
                                }
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
                                    text: root.backend.logsMode === "events"
                                        ? root.tr("Event detail", "Chi tiết sự kiện")
                                        : root.tr("Runtime line", "Dòng runtime")
                                    color: root.theme.textDim
                                    font.pixelSize: root.theme.font(8)
                                }
                                Text {
                                    text: root.backend.logsMode === "events"
                                        ? root.backend.selectedLogId
                                        : root.runtimeSelectedSource + " · " + root.runtimeSelectedTime
                                    color: root.theme.text
                                    font.family: root.backend.monoFontFamily
                                    font.pixelSize: root.theme.font(13)
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
                            visible: root.backend.logsMode === "events"
                            Layout.fillWidth: true
                            Layout.leftMargin: root.theme.sm
                            Layout.rightMargin: root.theme.sm
                            Layout.topMargin: root.theme.sm
                            Layout.bottomMargin: root.theme.sm
                            spacing: 2

                            Repeater {
                                model: [
                                    root.tr("Summary", "Tóm tắt"),
                                    root.tr("Metadata", "Metadata"),
                                    root.tr("Payload", "Payload")
                                ]

                                ClassicButton {
                                    required property int index
                                    required property string modelData
                                    theme: root.theme
                                    text: modelData
                                    quiet: root.detailTab !== index
                                    primary: root.detailTab === index
                                    Layout.fillWidth: true
                                    onClicked: root.detailTab = index
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.leftMargin: root.theme.sm
                            Layout.rightMargin: root.theme.sm
                            Layout.topMargin: root.backend.logsMode === "runtime" ? root.theme.sm : 0
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
                                    text: root.backend.logsMode === "events"
                                        ? root.detailText()
                                        : root.runtimeSelectedLine
                                    color: root.theme.text
                                    selectionColor: root.theme.accent
                                    selectedTextColor: "#FFFFFF"
                                    readOnly: true
                                    wrapMode: TextEdit.WrapAnywhere
                                    font.family: root.backend.monoFontFamily
                                    font.pixelSize: root.theme.font(13)
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
                                visible: root.backend.logsMode === "events"
                                objectName: "openOperationButton"
                                theme: root.theme
                                quiet: true
                                text: root.tr("Open operation", "Mở tác vụ")
                                Layout.fillWidth: true
                                enabled: root.backend.selectedLogId !== ""
                                onClicked: root.backend.openOperationForSelectedLog()
                            }

                            ClassicButton {
                                theme: root.theme
                                quiet: true
                                text: root.tr("Copy tab", "Sao chép tab")
                                onClicked: root.backend.copyText(
                                    root.backend.logsMode === "events"
                                        ? root.detailText()
                                        : root.runtimeSelectedLine
                                )
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
        enabled: root.backend.activePage === "logs"
        onActivated: {
            if (root.backend.logsMode === "runtime")
                runtimeSearch.forceActiveFocus()
            else
                eventSearch.forceActiveFocus()
        }
    }
    Shortcut {
        sequence: "/"
        context: Qt.ApplicationShortcut
        enabled: root.backend.activePage === "logs"
        onActivated: {
            if (root.backend.logsMode === "runtime")
                runtimeSearch.forceActiveFocus()
            else
                eventSearch.forceActiveFocus()
        }
    }
    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        enabled: root.backend.activePage === "logs"
        onActivated: {
            if (filterPopup.opened) {
                filterPopup.close()
            } else if (root.inspectorOpen) {
                root.inspectorOpen = false
            } else if (root.backend.logsMode === "runtime") {
                runtimeSearch.text = ""
                root.backend.setRuntimeLogSearch("")
                root.backend.setRuntimeLogSource("all")
            } else {
                eventSearch.text = ""
                root.backend.setLogSearch("")
                root.backend.setLogChatSearch("")
                root.backend.clearLogFilters()
            }
        }
    }

    Popup {
        id: filterPopup
        x: Math.max(root.theme.xl, root.width - width - root.theme.xl)
        y: 78
        width: 260
        padding: root.theme.md
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: root.theme.panelRaised
            radius: root.theme.popupRadius
            border.width: 1
            border.color: root.theme.border
        }

        contentItem: ColumnLayout {
            spacing: root.theme.sm

            Text {
                text: root.tr("Filters", "Bộ lọc")
                color: root.theme.text
                font.pixelSize: root.theme.font(11)
                font.weight: Font.DemiBold
            }

            ColumnLayout {
                visible: root.backend.logsMode === "events"
                Layout.fillWidth: true
                spacing: root.theme.xs

                Text {
                    text: root.tr("Category", "Danh mục")
                    color: root.theme.textDim
                    font.pixelSize: root.theme.font(8)
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: root.theme.xs
                    rowSpacing: root.theme.xs

                    Repeater {
                        model: [
                            {label: root.tr("All", "Tất cả"), value: "all"},
                            {label: root.tr("Errors", "Lỗi"), value: "error"},
                            {label: root.tr("Process", "Tiến trình"), value: "process"},
                            {label: root.tr("File", "Tệp"), value: "file"},
                            {label: root.tr("Session", "Phiên"), value: "session"},
                            {label: "API", value: "api"}
                        ]

                        ClassicButton {
                            required property var modelData
                            theme: root.theme
                            text: modelData.label
                            primary: root.backend.logCategoryFilter === modelData.value
                            quiet: root.backend.logCategoryFilter !== modelData.value
                            Layout.fillWidth: true
                            onClicked: root.backend.setLogCategory(modelData.value)
                        }
                    }
                }

                Text {
                    text: root.tr("Outcome", "Kết quả")
                    color: root.theme.textDim
                    font.pixelSize: root.theme.font(8)
                    Layout.topMargin: root.theme.xs
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: root.theme.xs

                    Repeater {
                        model: [
                            {label: root.tr("All", "Tất cả"), value: "all"},
                            {label: root.tr("Success", "Thành công"), value: "success"},
                            {label: root.tr("Failure", "Thất bại"), value: "failure"}
                        ]

                        ClassicButton {
                            required property var modelData
                            theme: root.theme
                            text: modelData.label
                            primary: root.backend.logOutcomeFilter === modelData.value
                            quiet: root.backend.logOutcomeFilter !== modelData.value
                            Layout.fillWidth: true
                            onClicked: root.backend.setLogOutcome(modelData.value)
                        }
                    }
                }

                ClassicSearch {
                    theme: root.theme
                    Layout.fillWidth: true
                    placeholderText: root.tr("Workspace / chat…", "Workspace / chat…")
                    onSearchRequested: function(value) {
                        root.backend.setLogChatSearch(value)
                    }
                }

                ClassicButton {
                    theme: root.theme
                    quiet: true
                    text: root.tr("Clear filters", "Xóa bộ lọc")
                    Layout.fillWidth: true
                    onClicked: root.backend.clearLogFilters()
                }
            }

            ColumnLayout {
                visible: root.backend.logsMode === "runtime"
                Layout.fillWidth: true
                spacing: root.theme.xs

                Text {
                    text: root.tr("Source", "Nguồn")
                    color: root.theme.textDim
                    font.pixelSize: root.theme.font(8)
                }

                Repeater {
                    model: [
                        {label: root.tr("All services", "Tất cả dịch vụ"), value: "all"},
                        {label: "Server", value: "server"},
                        {label: "Tunnel", value: "tunnel"},
                        {label: "Launcher", value: "launcher"},
                        {label: "Audit", value: "audit"},
                        {label: "Desktop", value: "desktop"}
                    ]

                    ClassicButton {
                        required property var modelData
                        theme: root.theme
                        text: modelData.label
                        primary: root.backend.runtimeLogSource === modelData.value
                        quiet: root.backend.runtimeLogSource !== modelData.value
                        Layout.fillWidth: true
                        onClicked: root.backend.setRuntimeLogSource(modelData.value)
                    }
                }
            }
        }
    }
}
