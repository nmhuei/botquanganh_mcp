pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    objectName: "workspacesPage"

    required property var theme
    required property var backend
    required property var tr
    required property var labels

    property string pendingAction: ""

    Rectangle {
        anchors.fill: parent
        color: root.theme.window

        RowLayout {
            anchors.fill: parent
            anchors.margins: root.theme.lg
            spacing: root.theme.md

            ClassicPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 500
                theme: root.theme
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
                            id: workspaceSearch
                            objectName: "workspaceSearch"
                            theme: root.theme
                            Layout.fillWidth: true
                            Layout.maximumWidth: 360
                            placeholderText: root.tr("Search workspaces…", "Tìm workspace…")
                            onSearchRequested: function(value) { root.backend.setWorkspaceSearch(value) }
                        }

                        Item { Layout.fillWidth: true }

                        Repeater {
                            model: [
                                {label: root.tr("All", "Tất cả"), value: "all"},
                                {label: root.tr("Active", "Đang dùng"), value: "active"},
                                {label: root.tr("Archived", "Đã lưu"), value: "archived"}
                            ]

                            NavItem {
                                required property var modelData
                                theme: root.theme
                                text: modelData.label
                                selected: root.backend.workspaceStateFilter === modelData.value
                                onClicked: root.backend.setWorkspaceStateFilter(modelData.value)
                            }
                        }

                        ClassicButton {
                            theme: root.theme
                            quiet: true
                            text: "↻"
                            implicitWidth: 38
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
                        Layout.leftMargin: root.theme.md
                        Layout.rightMargin: root.theme.md
                        Layout.preferredHeight: 30
                        spacing: root.theme.md

                        Text {
                            text: root.tr("Workspace", "Workspace")
                            color: root.theme.textMuted
                            font.pixelSize: root.theme.font(9)
                            font.weight: Font.Medium
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.tr("State", "Trạng thái")
                            color: root.theme.textMuted
                            font.pixelSize: root.theme.font(9)
                            Layout.preferredWidth: 90
                        }
                        Text {
                            text: root.tr("Size", "Dung lượng")
                            color: root.theme.textMuted
                            font.pixelSize: root.theme.font(9)
                            Layout.preferredWidth: 80
                            horizontalAlignment: Text.AlignRight
                        }
                        Text {
                            text: root.tr("Ops", "Tác vụ")
                            color: root.theme.textMuted
                            font.pixelSize: root.theme.font(9)
                            Layout.preferredWidth: 54
                            horizontalAlignment: Text.AlignRight
                        }
                        Text {
                            text: root.tr("Fail", "Lỗi")
                            color: root.theme.textMuted
                            font.pixelSize: root.theme.font(9)
                            Layout.preferredWidth: 48
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: root.theme.borderDark
                    }

                    ListView {
                        id: workspaceList
                        objectName: "workspaceList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: root.backend.workspacesModel
                        clip: true
                        reuseItems: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: workspaceRow
                            required property int index
                            required property string chatId
                            required property string label
                            required property string workspaceState
                            required property string sizeText
                            required property int operations
                            required property int failures

                            width: workspaceList.width
                            height: root.theme.rowHeight
                            color: root.backend.selectedWorkspaceId === workspaceRow.chatId
                                ? root.theme.navigationSelected
                                : workspaceMouse.containsMouse
                                ? root.theme.rowHover
                                : "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: root.theme.md
                                anchors.rightMargin: root.theme.md
                                spacing: root.theme.md

                                Text {
                                    text: workspaceRow.label
                                    color: root.theme.text
                                    font.pixelSize: root.theme.font(9)
                                    font.weight: root.backend.selectedWorkspaceId === workspaceRow.chatId
                                        ? Font.DemiBold : Font.Medium
                                    Layout.fillWidth: true
                                    elide: Text.ElideMiddle
                                }

                                StatusLamp {
                                    theme: root.theme
                                    text: root.labels.workspaceState(workspaceRow.workspaceState)
                                    tone: workspaceRow.workspaceState === "archived" ? "info" : "success"
                                    Layout.preferredWidth: 90
                                }

                                Text {
                                    text: workspaceRow.sizeText
                                    color: root.theme.textMuted
                                    font.pixelSize: root.theme.font(8)
                                    Layout.preferredWidth: 80
                                    horizontalAlignment: Text.AlignRight
                                }
                                Text {
                                    text: workspaceRow.operations
                                    color: root.theme.textMuted
                                    font.pixelSize: root.theme.font(8)
                                    Layout.preferredWidth: 54
                                    horizontalAlignment: Text.AlignRight
                                }
                                Text {
                                    text: workspaceRow.failures
                                    color: workspaceRow.failures > 0 ? root.theme.error : root.theme.textDim
                                    font.pixelSize: root.theme.font(8)
                                    Layout.preferredWidth: 48
                                    horizontalAlignment: Text.AlignRight
                                }
                            }

                            MouseArea {
                                id: workspaceMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    workspaceList.currentIndex = workspaceRow.index
                                    root.backend.selectWorkspace(workspaceRow.chatId)
                                }
                            }
                        }

                        EmptyState {
                            anchors.fill: parent
                            visible: workspaceList.count === 0
                            theme: root.theme
                            title: root.tr("No matching workspaces", "Không có workspace phù hợp")
                            detail: root.tr("Change the search or state filter.", "Hãy đổi nội dung tìm kiếm hoặc bộ lọc trạng thái.")
                        }
                    }
                }
            }

            ClassicPanel {
                Layout.preferredWidth: 330
                Layout.fillHeight: true
                theme: root.theme
                raised: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: root.theme.lg
                    spacing: root.theme.md

                    Text {
                        text: root.backend.selectedWorkspaceId === ""
                            ? root.tr("Select a workspace", "Chọn một workspace")
                            : root.backend.selectedWorkspaceId
                        color: root.theme.text
                        font.pixelSize: root.theme.font(11)
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                    }

                    Text {
                        text: root.backend.selectedWorkspacePath
                        color: root.theme.textDim
                        font.family: root.backend.monoFontFamily
                        font.pixelSize: root.theme.font(8)
                        Layout.fillWidth: true
                        wrapMode: Text.WrapAnywhere
                        maximumLineCount: 3
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: root.theme.borderDark
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: root.theme.md
                        rowSpacing: root.theme.sm

                        Text { text: root.tr("State", "Trạng thái"); color: root.theme.textDim; font.pixelSize: root.theme.font(8) }
                        Text { text: root.labels.workspaceState(root.backend.selectedWorkspaceState); color: root.theme.text; font.pixelSize: root.theme.font(9) }
                        Text { text: root.tr("Last active", "Hoạt động cuối"); color: root.theme.textDim; font.pixelSize: root.theme.font(8) }
                        Text { text: root.backend.selectedWorkspaceLastActive; color: root.theme.text; font.pixelSize: root.theme.font(9); elide: Text.ElideRight; Layout.fillWidth: true }
                        Text { text: root.tr("Size", "Dung lượng"); color: root.theme.textDim; font.pixelSize: root.theme.font(8) }
                        Text { text: root.backend.selectedWorkspaceSizeText; color: root.theme.text; font.pixelSize: root.theme.font(9) }
                        Text { text: root.tr("Operations", "Tác vụ"); color: root.theme.textDim; font.pixelSize: root.theme.font(8) }
                        Text { text: root.backend.selectedWorkspaceOperations; color: root.theme.text; font.pixelSize: root.theme.font(9) }
                        Text { text: root.tr("Failures", "Lỗi"); color: root.theme.textDim; font.pixelSize: root.theme.font(8) }
                        Text { text: root.backend.selectedWorkspaceFailures; color: root.backend.selectedWorkspaceFailures > 0 ? root.theme.error : root.theme.text; font.pixelSize: root.theme.font(9) }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.theme.xs

                        ClassicButton {
                            objectName: "workspaceOpenActivity"
                            theme: root.theme
                            primary: true
                            text: root.tr("Activity", "Hoạt động")
                            Layout.fillWidth: true
                            enabled: root.backend.selectedWorkspaceId !== ""
                            onClicked: root.backend.openSelectedWorkspaceActivity()
                        }
                        ClassicButton {
                            objectName: "workspaceOpenEvents"
                            theme: root.theme
                            quiet: true
                            text: root.tr("Events", "Sự kiện")
                            Layout.fillWidth: true
                            enabled: root.backend.selectedWorkspaceId !== ""
                            onClicked: root.backend.openSelectedWorkspaceLogs()
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Text {
                        text: root.tr("Lifecycle", "Vòng đời")
                        color: root.theme.textDim
                        font.pixelSize: root.theme.font(8)
                    }

                    ClassicButton {
                        visible: root.backend.selectedWorkspaceState !== "archived"
                        theme: root.theme
                        quiet: true
                        text: root.tr("Archive workspace", "Lưu trữ workspace")
                        Layout.fillWidth: true
                        enabled: root.backend.selectedWorkspaceId !== "" && !root.backend.actionBusy
                        onClicked: archiveDialog.open()
                    }

                    ClassicButton {
                        visible: root.backend.selectedWorkspaceState === "archived"
                        theme: root.theme
                        quiet: true
                        text: root.tr("Restore workspace", "Khôi phục workspace")
                        Layout.fillWidth: true
                        enabled: root.backend.selectedWorkspaceId !== "" && !root.backend.actionBusy
                        onClicked: root.backend.restoreSelectedWorkspace()
                    }

                    ClassicButton {
                        visible: root.backend.selectedWorkspaceState === "archived"
                        theme: root.theme
                        danger: true
                        text: root.tr("Delete permanently", "Xóa vĩnh viễn")
                        Layout.fillWidth: true
                        enabled: root.backend.selectedWorkspaceId !== "" && !root.backend.actionBusy
                        onClicked: deleteDialog.open()
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: root.theme.borderDark
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.theme.xs

                        ClassicButton {
                            theme: root.theme
                            quiet: true
                            text: root.tr("Preview prune", "Xem trước prune")
                            Layout.fillWidth: true
                            enabled: !root.backend.actionBusy
                            onClicked: root.backend.pruneWorkspaces(false)
                        }
                        ClassicButton {
                            theme: root.theme
                            danger: true
                            text: root.tr("Apply prune", "Thực hiện prune")
                            Layout.fillWidth: true
                            enabled: !root.backend.actionBusy
                            onClicked: pruneDialog.open()
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: archiveDialog
        modal: true
        title: root.tr("Archive workspace?", "Lưu trữ workspace?")
        standardButtons: Dialog.Cancel | Dialog.Ok
        onAccepted: root.backend.archiveSelectedWorkspace()
    }

    Dialog {
        id: deleteDialog
        modal: true
        title: root.tr("Delete workspace permanently?", "Xóa workspace vĩnh viễn?")
        standardButtons: Dialog.Cancel | Dialog.Ok
        onAccepted: root.backend.deleteSelectedWorkspace()
    }

    Dialog {
        id: pruneDialog
        modal: true
        title: root.tr("Prune archived workspaces?", "Prune workspace đã lưu?")
        standardButtons: Dialog.Cancel | Dialog.Ok
        onAccepted: root.backend.pruneWorkspaces(true)
    }
}
