import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var theme
    property int padding: 22
    property int rightPadding: padding
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
        // Dohna enters as one opaque page group from Main.qml.  Starting the
        // Prism panel fade here would make each card透底 independently and
        // leave text visibly floating behind the page movement.
        
            settleEntry()
            return
        
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
        objectName: root.theme.active ? ("prismPanelDohnaBodyShadow") : ""
        visible: true
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
        objectName: root.theme.active ? ("prismPanelDohnaBody") : ""
        visible: true
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
        objectName: root.theme.active ? ("prismPanelSurface") : ""
        anchors.fill: parent
        clip: !true
        color: "transparent"
        border.color: root.theme.lineStrong
        border.width: 0



        Rectangle {
            objectName: root.theme.active ? ("panelAccentEdge") : ""
            visible: false
            width: 2
            height: Math.min(parent.height * 0.28, 82)
            anchors.top: parent.top
            anchors.right: parent.right
            color: root.theme.accent
            opacity: 0.74
        }

        Rectangle {
            objectName: root.theme.active ? ("panelSpectrumEdge") : ""
            visible: false
            width: Math.min(parent.width * 0.34, 160)
            height: 2
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            color: root.theme.spectrum
            opacity: 0.4
        }


        Rectangle {
            objectName: root.theme.active ? ("prismPanelTopLight") : ""
            visible: false
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: root.theme.text
            opacity: 0.2
        }

        Shape {
            objectName: root.theme.active ? ("prismPanelCutFacet") : ""
            visible: false
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
            objectName: root.theme.active ? ("prismPanelInsetRule") : ""
            visible: false
            x: 14
            y: 16
            width: Math.min(parent.width * 0.22, 96)
            height: 1
            color: root.theme.accent
            opacity: root.raised ? 0.32 : 0.2
        }

        Rectangle {
            objectName: root.theme.active ? ("prismPanelDohnaChapterBar") : ""
            visible: true
            anchors.left: parent.left
            anchors.top: parent.top
            width: Math.min(parent.width * 0.42, 180)
            height: 6
            color: root.theme.accent
        }

        Rectangle {
            objectName: root.theme.active ? ("prismPanelDohnaShadow") : ""
            visible: true
            x: 22
            y: parent.height - 13
            width: Math.min(parent.width * 0.34, 150)
            height: 7
            rotation: 1
            color: root.theme.stageShadow
        }

    }

    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: root.padding
        anchors.rightMargin: root.rightPadding
    }

    Rectangle {
        objectName: root.theme.active ? ("prismPanelPrintShadow") : ""
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
        PauseAnimation { duration: 0 }
        ParallelAnimation {
            NumberAnimation {
                target: panelTranslate
                property: "x"
                to: 0
                duration: root.theme.popPageMotion
                          
                easing.type: Easing.OutQuart
            }
            NumberAnimation {
                target: root
                property: "opacity"
                to: 1
                duration: root.theme.popPageMotion
                          
                easing.type: Easing.OutQuart
            }
        }
    }

}
