import QtQuick

Item {
    id: root

    required property var theme
    // Keep the existing layout slot; only the neutral divider is painted.
    implicitHeight: 7
    clip: true

    Rectangle {
        objectName: root.theme.active ? ("prismDividerLine") : ""
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: 1
        color: root.theme.line
    }

}
