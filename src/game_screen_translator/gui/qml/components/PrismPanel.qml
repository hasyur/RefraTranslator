import QtQuick
import QtQuick.Shapes

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
    property real dohnaStamp: 1
    default property alias contentData: contentItem.data

    implicitWidth: 320
    implicitHeight: 240
    transform: Translate { id: panelTranslate }

    function settleEntry() {
        panelEntry.stop()
        panelEntry.running = false
        panelTranslate.x = 0
        root.opacity = 1
        dohnaStamp = 1
    }

    function playEntry() {
        // Dohna enters as one opaque page group from Main.qml.  Starting the
        // Prism panel fade here would make each card透底 independently and
        // leave text visibly floating behind the page movement.
        if (theme.dohna || !motionEnabled || reducedMotion) {
            settleEntry()
            return
        }
        panelEntry.restart()
    }

    onTransitionSerialChanged: Qt.callLater(root.playEntry)
    onMotionEnabledChanged: {
        if (motionEnabled)
            root.playEntry()
        else
            settleEntry()
    }
    onReducedMotionChanged: {
        if (reducedMotion)
            settleEntry()
    }

    Connections {
        target: root.theme
        function onDohnaChanged() {
            root.settleEntry()
        }
    }

    Shape {
        objectName: "prismPanelDohnaBodyShadow"
        visible: root.theme.dohna
        x: 6
        y: 6
        width: root.width
        height: root.height
        z: -2
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.theme.stageShadow
            startX: 12
            startY: 0
            PathLine { x: root.width - 8; y: 0 }
            PathLine { x: root.width; y: 12 }
            PathLine { x: root.width; y: root.height - 10 }
            PathLine { x: root.width - 10; y: root.height }
            PathLine { x: 12; y: root.height }
            PathLine { x: 0; y: root.height - 10 }
            PathLine { x: 0; y: 12 }
            PathLine { x: 12; y: 0 }
        }
    }

    Shape {
        objectName: "prismPanelDohnaBody"
        visible: root.theme.dohna
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.theme.ink
            strokeWidth: 3
            fillColor: root.theme.white
            startX: 12
            startY: 0
            PathLine { x: root.width - 8; y: 0 }
            PathLine { x: root.width; y: 12 }
            PathLine { x: root.width; y: root.height - 10 }
            PathLine { x: root.width - 10; y: root.height }
            PathLine { x: 12; y: root.height }
            PathLine { x: 0; y: root.height - 10 }
            PathLine { x: 0; y: 12 }
            PathLine { x: 12; y: 0 }
        }
    }

    Rectangle {
        objectName: "prismPanelSurface"
        anchors.fill: parent
        clip: !root.theme.dohna
        color: root.theme.dohna ? "transparent" : (root.raised ? root.theme.glassRaised : root.theme.glass)
        border.color: root.theme.lineStrong
        border.width: root.theme.dohna ? 0 : 1

        Rectangle {
            objectName: "panelAccentEdge"
            visible: !root.theme.dohna
            width: 2
            height: Math.min(parent.height * 0.28, 82)
            anchors.top: parent.top
            anchors.right: parent.right
            color: root.theme.accent
            opacity: 0.74
        }

        Rectangle {
            objectName: "panelSpectrumEdge"
            visible: !root.theme.dohna
            width: Math.min(parent.width * 0.34, 160)
            height: 2
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            color: root.theme.spectrum
            opacity: 0.4
        }


        Rectangle {
            objectName: "prismPanelTopLight"
            visible: !root.theme.dohna
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: root.theme.text
            opacity: root.theme.dark ? 0.12 : 0.2
        }

        Shape {
            objectName: "prismPanelCutFacet"
            visible: !root.theme.dohna
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillColor: Qt.rgba(root.theme.accent.r,
                                   root.theme.accent.g,
                                   root.theme.accent.b,
                                   root.raised ? 0.075 : 0.045)
                startX: root.width * 0.76; startY: 0
                PathLine { x: root.width; y: 0 }
                PathLine { x: root.width; y: root.height * 0.2 }
                PathLine { x: root.width * 0.91; y: root.height * 0.13 }
                PathLine { x: root.width * 0.76; y: 0 }
            }
        }

        Rectangle {
            objectName: "prismPanelInsetRule"
            visible: !root.theme.dohna
            x: 14
            y: 16
            width: Math.min(parent.width * 0.22, 96)
            height: 1
            color: root.theme.accent
            opacity: root.raised ? 0.32 : 0.2
        }

        Rectangle {
            objectName: "prismPanelDohnaChapterBar"
            visible: root.theme.dohna
            anchors.left: parent.left
            anchors.top: parent.top
            width: Math.min(parent.width * 0.42, 180)
            height: 6
            color: root.theme.accent
        }

        Rectangle {
            objectName: "prismPanelDohnaShadow"
            visible: root.theme.dohna
            x: 22
            y: parent.height - 13
            width: Math.min(parent.width * 0.34, 150)
            height: 7
            rotation: 1
            color: root.theme.stageShadow
        }

        Rectangle {
            objectName: "prismPanelDohnaStampShadow"
            visible: root.theme.dohna
            x: parent.width - 91
            y: -3
            width: 88
            height: 24
            rotation: -6
            color: root.theme.stageShadow
            opacity: root.dohnaStamp
        }

        Shape {
            objectName: "prismPanelDohnaStamp"
            visible: root.theme.dohna
            x: parent.width - 96
            y: -8
            width: 88
            height: 24
            rotation: -6 + root.dohnaStamp * 2
            opacity: root.dohnaStamp
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.theme.ink
                strokeWidth: 2
                fillColor: root.theme.violet
                startX: 0
                startY: 2
                PathLine { x: 78; y: 0 }
                PathLine { x: 88; y: 22 }
                PathLine { x: 8; y: 24 }
                PathLine { x: 0; y: 2 }
            }
        }
    }

    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: root.padding
    }

    Rectangle {
        objectName: "prismPanelPrintShadow"
        visible: false
        x: 5
        y: 5
        width: root.width
        height: root.height
        color: root.theme.stageShadow
        z: -1
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
        PauseAnimation { duration: root.theme.dohna ? 0 : (root.motionRole === "secondary" ? 58 : 0) }
        ParallelAnimation {
            NumberAnimation {
                target: panelTranslate
                property: "x"
                to: 0
                duration: root.theme.dohna
                          ? root.theme.popPageMotion
                          : (root.motionRole === "secondary" ? root.theme.pageSecondaryMotion : root.theme.pageMotion)
                easing.type: Easing.OutQuart
            }
            NumberAnimation {
                target: root
                property: "opacity"
                to: 1
                duration: root.theme.dohna
                          ? root.theme.popPageMotion
                          : (root.motionRole === "secondary" ? root.theme.pageSecondaryMotion : root.theme.pageMotion)
                easing.type: Easing.OutQuart
            }
        }
    }

}
