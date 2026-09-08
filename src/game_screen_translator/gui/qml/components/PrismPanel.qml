import QtQuick

Item {
    id: root

    required property var theme
    property int padding: 22
    property bool raised: false
    property string motionRole: "primary"
    property int transitionSerial: 0
    property bool motionEnabled: false
    readonly property bool reducedMotion: theme.reducedMotion
    readonly property bool entryRunning: panelEntry.running
    readonly property real visualOffsetX: panelTranslate.x
    default property alias contentData: contentItem.data

    implicitWidth: 320
    implicitHeight: 240
    transform: Translate { id: panelTranslate }

    function settleEntry() {
        panelEntry.stop()
        panelEntry.running = false
        panelTranslate.x = 0
        root.opacity = 1
    }

    function playEntry() {
        if (!motionEnabled || reducedMotion) {
            settleEntry()
            return
        }
        panelEntry.restart()
    }

    onTransitionSerialChanged: Qt.callLater(root.playEntry)
    onReducedMotionChanged: {
        if (reducedMotion)
            settleEntry()
    }
    onMotionEnabledChanged: {
        if (!motionEnabled)
            settleEntry()
    }

    Rectangle {
        objectName: "prismPanelSurface"
        anchors.fill: parent
        clip: true
        color: root.raised ? root.theme.glassRaised : root.theme.glass
        border.color: root.theme.lineStrong
        border.width: 1

        Rectangle {
            objectName: "panelAccentEdge"
            width: 2
            height: Math.min(parent.height * 0.28, 82)
            anchors.top: parent.top
            anchors.right: parent.right
            color: root.theme.accent
            opacity: 0.74
        }

        Rectangle {
            objectName: "panelSpectrumEdge"
            width: Math.min(parent.width * 0.34, 160)
            height: 2
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            color: root.theme.spectrum
            opacity: 0.4
        }


        Rectangle {
            width: Math.min(parent.width * 0.24, 110)
            height: 2
            x: -12
            y: 18
            rotation: -12
            color: root.theme.accent
            opacity: root.raised ? 0.5 : 0.32
        }
    }

    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: root.padding
    }

    SequentialAnimation {
        id: panelEntry
        onStopped: {
            panelTranslate.x = 0
            root.opacity = 1
        }
        PropertyAction {
            target: panelTranslate
            property: "x"
            value: root.motionRole === "secondary" ? 18 : 15
        }
        PropertyAction { target: root; property: "opacity"; value: root.motionRole === "secondary" ? 0 : 0.1 }
        PauseAnimation { duration: root.motionRole === "secondary" ? 110 : 0 }
        ParallelAnimation {
            NumberAnimation {
                target: panelTranslate
                property: "x"
                to: 0
                duration: root.motionRole === "secondary" ? root.theme.pageSecondaryMotion : root.theme.pageMotion
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: root
                property: "opacity"
                to: 1
                duration: root.motionRole === "secondary" ? root.theme.pageSecondaryMotion : root.theme.pageMotion
                easing.type: Easing.OutCubic
            }
        }
    }
}
