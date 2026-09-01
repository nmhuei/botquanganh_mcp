pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: window
    objectName: "bqaCenterWindow"
    required property var center

    width: window.center.initialWindowWidth
    height: window.center.initialWindowHeight
    minimumWidth: 960
    minimumHeight: 650
    visible: true
    title: "BQA Center"
    color: theme.window

    Theme {
        id: theme
        variant: window.center.themeName
        density: window.center.density
        fontScale: window.center.fontScale
    }

    DomainLabels {
        id: labels
        language: window.center.language
    }

    property bool readyForPersistence: false
    property string primaryPage: "overview"
    // Kept for compatibility with older viewport probes. Primary navigation is
    // no longer a sidebar and therefore never enters icon-only mode.
    property bool compactNavigation: false

    function tr(en, vi) {
        return window.center.language === "vi" ? vi : en
    }

    function isPrimary(page) {
        return page === "overview" || page === "activity" || page === "logs"
    }

    function pageIndex(page) {
        if (page === "activity") return 1
        if (page === "logs") return 2
        return 0
    }

    function navigate(page) {
        if (window.isPrimary(page))
            window.primaryPage = page
        window.center.setActivePage(page)
    }

    function closeSecondaryPopups() {
        if (workspacePopup.opened) workspacePopup.close()
        if (diagnosticsPopup.opened) diagnosticsPopup.close()
        if (settingsPopup.opened) settingsPopup.close()
    }

    function syncBackendPage() {
        const page = window.center.activePage
        if (window.isPrimary(page)) {
            window.primaryPage = page
            window.closeSecondaryPopups()
        } else if (page === "workspaces") {
            if (!workspacePopup.opened) workspacePopup.open()
            if (diagnosticsPopup.opened) diagnosticsPopup.close()
            if (settingsPopup.opened) settingsPopup.close()
        } else if (page === "diagnostics") {
            if (!diagnosticsPopup.opened) diagnosticsPopup.open()
            if (workspacePopup.opened) workspacePopup.close()
            if (settingsPopup.opened) settingsPopup.close()
        } else if (page === "settings") {
            if (!settingsPopup.opened) settingsPopup.open()
            if (workspacePopup.opened) workspacePopup.close()
            if (diagnosticsPopup.opened) diagnosticsPopup.close()
        }
    }

    Timer {
        id: geometrySaveTimer
        interval: 450
        repeat: false
        onTriggered: window.center.saveWindowGeometry(window.width, window.height)
    }

    Timer {
        id: toastTimer
        interval: 3200
        repeat: false
        onTriggered: window.center.clearToast()
    }

    Connections {
        target: window.center
        function onToastChanged() {
            if (window.center.toastText.length > 0)
                toastTimer.restart()
        }
        function onActivePageChanged() {
            window.syncBackendPage()
        }
    }

    Component.onCompleted: {
        if (window.isPrimary(window.center.activePage))
            window.primaryPage = window.center.activePage
        readyForPersistence = true
        window.syncBackendPage()
    }

    onWidthChanged: {
        if (readyForPersistence) geometrySaveTimer.restart()
    }
    onHeightChanged: {
        if (readyForPersistence) geometrySaveTimer.restart()
    }
    onClosing: {
        window.center.saveWindowGeometry(width, height)
        window.center.shutdown()
    }

    Shortcut { sequence: "Ctrl+1"; context: Qt.ApplicationShortcut; autoRepeat: false; onActivated: window.navigate("overview") }
    Shortcut { sequence: "Ctrl+2"; context: Qt.ApplicationShortcut; autoRepeat: false; onActivated: window.navigate("activity") }
    Shortcut { sequence: "Ctrl+3"; context: Qt.ApplicationShortcut; autoRepeat: false; onActivated: window.navigate("logs") }
    Shortcut { sequence: "Ctrl+,"; context: Qt.ApplicationShortcut; autoRepeat: false; onActivated: window.navigate("settings") }
    Shortcut { sequence: "Ctrl+Shift+D"; context: Qt.ApplicationShortcut; autoRepeat: false; onActivated: window.navigate("diagnostics") }
    Shortcut {
        sequences: [StandardKey.Refresh, "Ctrl+R"]
        context: Qt.ApplicationShortcut
        autoRepeat: false
        onActivated: {
            if (window.primaryPage === "logs" && window.center.logsMode === "runtime")
                window.center.refreshRuntimeLogs()
            else
                window.center.refreshNow()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: theme.window

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: theme.headerHeight
                color: theme.navigation
                border.width: 0
                gradient: Gradient {
                    GradientStop { position: 0.0; color: theme.chromeTop }
                    GradientStop { position: 1.0; color: theme.chromeBottom }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: theme.borderDark
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: theme.lg
                    anchors.rightMargin: theme.md
                    spacing: theme.sm

                    RowLayout {
                        Layout.preferredWidth: 154
                        spacing: 9

                        Rectangle {
                            Layout.preferredWidth: 22
                            Layout.preferredHeight: 22
                            radius: 7
                            color: theme.accent
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: theme.accentLight }
                                GradientStop { position: 1.0; color: theme.accentDark }
                            }

                            Text {
                                anchors.centerIn: parent
                                text: "B"
                                color: "#FFFFFF"
                                font.pixelSize: theme.font(10)
                                font.weight: Font.Bold
                            }
                        }

                        ColumnLayout {
                            spacing: 0
                            Text {
                                text: "BQA"
                                color: theme.text
                                font.pixelSize: theme.font(11)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: window.tr("Center", "Trung tâm")
                                color: theme.textDim
                                font.pixelSize: theme.font(8)
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.xs

                        NavItem {
                            objectName: "navOverview"
                            theme: theme
                            text: window.tr("Monitor", "Theo dõi")
                            selected: window.primaryPage === "overview"
                            onClicked: window.navigate("overview")
                        }
                        NavItem {
                            objectName: "navActivity"
                            theme: theme
                            text: window.tr("Activity", "Hoạt động")
                            selected: window.primaryPage === "activity"
                            onClicked: window.navigate("activity")
                        }
                        NavItem {
                            objectName: "navLogs"
                            theme: theme
                            text: window.tr("Logs", "Nhật ký")
                            selected: window.primaryPage === "logs"
                            onClicked: window.navigate("logs")
                        }

                        Item { Layout.fillWidth: true }
                    }

                    StatusLamp {
                        theme: theme
                        text: labels.runtimeState(window.center.overallState, window.center.runtimeBadge)
                        tone: window.center.runtimeTone
                    }

                    ClassicButton {
                        objectName: "appMenuButton"
                        theme: theme
                        text: "•••"
                        quiet: true
                        implicitWidth: 42
                        Accessible.name: window.tr("Application menu", "Menu ứng dụng")
                        onClicked: appMenu.open()
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: window.pageIndex(window.primaryPage)

                OverviewPage {
                    theme: theme
                    backend: window.center
                    tr: window.tr
                    labels: labels
                }

                ActivityPage {
                    theme: theme
                    backend: window.center
                    tr: window.tr
                    labels: labels
                }

                LogsPage {
                    theme: theme
                    backend: window.center
                    tr: window.tr
                    labels: labels
                }
            }
        }
    }

    Popup {
        id: appMenu
        x: Math.max(theme.md, window.width - width - theme.md)
        y: theme.headerHeight - 2
        width: 238
        padding: theme.sm
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: theme.panelRaised
            radius: theme.popupRadius
            border.width: 1
            border.color: theme.border
        }

        contentItem: ColumnLayout {
            spacing: 2

            Text {
                text: window.tr("Operations", "Vận hành")
                color: theme.textDim
                font.pixelSize: theme.font(8)
                font.weight: Font.DemiBold
                Layout.leftMargin: theme.sm
                Layout.topMargin: theme.xs
            }

            ClassicButton {
                theme: theme
                quiet: true
                alignLeft: true
                text: window.tr("Refresh now", "Làm mới ngay")
                Layout.fillWidth: true
                onClicked: {
                    appMenu.close()
                    window.center.refreshNow()
                }
            }
            ClassicButton {
                theme: theme
                quiet: true
                alignLeft: true
                text: window.tr("Restart connector", "Khởi động lại connector")
                Layout.fillWidth: true
                enabled: !window.center.actionBusy
                onClicked: {
                    appMenu.close()
                    window.center.restartBridge()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: theme.xs
                Layout.bottomMargin: theme.xs
                color: theme.borderDark
            }

            ClassicButton {
                objectName: "menuDiagnostics"
                theme: theme
                quiet: true
                alignLeft: true
                text: window.tr("Diagnostics…", "Chẩn đoán…")
                Layout.fillWidth: true
                onClicked: {
                    appMenu.close()
                    window.navigate("diagnostics")
                }
            }
            ClassicButton {
                objectName: "menuWorkspaces"
                theme: theme
                quiet: true
                alignLeft: true
                text: window.tr("Manage workspaces…", "Quản lý workspace…")
                Layout.fillWidth: true
                onClicked: {
                    appMenu.close()
                    window.navigate("workspaces")
                }
            }
            ClassicButton {
                objectName: "menuPreferences"
                theme: theme
                quiet: true
                alignLeft: true
                text: window.tr("Preferences…", "Tùy chọn…")
                Layout.fillWidth: true
                onClicked: {
                    appMenu.close()
                    window.navigate("settings")
                }
            }

            Text {
                text: "BQA Center  ·  v" + window.center.serviceVersion
                color: theme.textDim
                font.pixelSize: theme.font(8)
                Layout.leftMargin: theme.sm
                Layout.topMargin: theme.sm
                Layout.bottomMargin: theme.xs
            }
        }
    }

    Popup {
        id: workspacePopup
        modal: true
        focus: true
        x: Math.round(window.width * 0.04)
        y: Math.round(window.height * 0.05)
        width: Math.round(window.width * 0.92)
        height: Math.round(window.height * 0.90)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: {
            if (window.center.activePage === "workspaces")
                window.center.setActivePage(window.primaryPage)
        }
        background: Rectangle {
            color: theme.panel
            radius: theme.popupRadius
            border.width: 1
            border.color: theme.border
        }

        contentItem: ColumnLayout {
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                color: theme.panelRaised
                radius: theme.popupRadius

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: theme.popupRadius
                    color: theme.panelRaised
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: theme.lg
                    anchors.rightMargin: theme.sm
                    Text {
                        text: window.tr("Manage workspaces", "Quản lý workspace")
                        color: theme.text
                        font.pixelSize: theme.font(11)
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    ClassicButton {
                        theme: theme
                        quiet: true
                        text: "×"
                        implicitWidth: 36
                        onClicked: workspacePopup.close()
                    }
                }
            }
            WorkspacesPage {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: theme
                backend: window.center
                tr: window.tr
                labels: labels
            }
        }
    }

    Popup {
        id: diagnosticsPopup
        modal: true
        focus: true
        x: Math.round(window.width * 0.10)
        y: Math.round(window.height * 0.08)
        width: Math.round(window.width * 0.80)
        height: Math.round(window.height * 0.84)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onOpened: {
            if (window.center.doctorChecksModel.rowCount === undefined)
                return
        }
        onClosed: {
            if (window.center.activePage === "diagnostics")
                window.center.setActivePage(window.primaryPage)
        }
        background: Rectangle {
            color: theme.panel
            radius: theme.popupRadius
            border.width: 1
            border.color: theme.border
        }

        contentItem: ColumnLayout {
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                color: theme.panelRaised
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: theme.lg
                    anchors.rightMargin: theme.sm
                    Text {
                        text: window.tr("Diagnostics", "Chẩn đoán")
                        color: theme.text
                        font.pixelSize: theme.font(11)
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    ClassicButton {
                        theme: theme
                        quiet: true
                        text: "×"
                        implicitWidth: 36
                        onClicked: diagnosticsPopup.close()
                    }
                }
            }
            DiagnosticsPage {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: theme
                backend: window.center
                tr: window.tr
                labels: labels
            }
        }
    }

    Popup {
        id: settingsPopup
        modal: true
        focus: true
        x: Math.round(window.width * 0.17)
        y: Math.round(window.height * 0.10)
        width: Math.round(window.width * 0.66)
        height: Math.round(window.height * 0.80)
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: {
            if (window.center.activePage === "settings")
                window.center.setActivePage(window.primaryPage)
        }
        background: Rectangle {
            color: theme.panel
            radius: theme.popupRadius
            border.width: 1
            border.color: theme.border
        }

        contentItem: ColumnLayout {
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                color: theme.panelRaised
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: theme.lg
                    anchors.rightMargin: theme.sm
                    Text {
                        text: window.tr("Preferences", "Tùy chọn")
                        color: theme.text
                        font.pixelSize: theme.font(11)
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    ClassicButton {
                        theme: theme
                        quiet: true
                        text: "×"
                        implicitWidth: 36
                        onClicked: settingsPopup.close()
                    }
                }
            }
            SettingsPage {
                Layout.fillWidth: true
                Layout.fillHeight: true
                theme: theme
                backend: window.center
                tr: window.tr
                labels: labels
            }
        }
    }

    Rectangle {
        visible: window.center.toastText.length > 0
        z: 1000
        width: Math.min(420, toastText.implicitWidth + 32)
        height: 42
        radius: 10
        color: theme.panelRaised
        border.width: 1
        border.color: theme.border
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: theme.lg
        anchors.bottomMargin: theme.lg

        Text {
            id: toastText
            anchors.centerIn: parent
            width: parent.width - 24
            text: window.center.toastText
            color: theme.text
            font.pixelSize: theme.font(9)
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }
}
