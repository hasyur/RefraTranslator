pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var theme
    property bool reducedMotion: false
    property bool motionEnabled: false
    property string actionKind: ""
    property int actionSequence: 0
    property int warningSequence: 0
    property int startSequence: 0
    property real actionProgress: 1
    property real warningProgress: 1
    property real startProgress: 1
    property bool actionActive: false
    property bool warningActive: false
    property bool startActive: false
    readonly property bool actionPulseRunning: actionPulse.running && actionActive
    readonly property bool warningPulseRunning: warningPulse.running && warningActive
    readonly property bool startPulseRunning: startPulse.running && startActive

    enabled: false
    z: 20
    visible: root.theme.dohna && root.motionEnabled

    function settle() {
        actionPulse.stop()
        warningPulse.stop()
        startPulse.stop()
        actionActive = false
        warningActive = false
        startActive = false
        actionProgress = 1
        warningProgress = 1
        startProgress = 1
    }

    function pulseAction(kind) {
        actionKind = kind
        actionSequence += 1
        if (reducedMotion || !motionEnabled || !theme.dohna) {
            actionPulse.stop()
            actionActive = false
            actionProgress = 1
            return
        }
        actionPulse.stop()
        actionActive = true
        actionPulse.start()
    }

    function pulseWarning() {
        warningSequence += 1
        if (reducedMotion || !motionEnabled || !theme.dohna) {
            warningPulse.stop()
            warningActive = false
            warningProgress = 1
            return
        }
        warningPulse.stop()
        warningActive = true
        warningPulse.start()
    }

    function pulseStart() {
        startSequence += 1
        if (reducedMotion || !motionEnabled || !theme.dohna) {
            startPulse.stop()
            startActive = false
            startProgress = 1
            return
        }
        startPulse.stop()
        startActive = true
        startPulse.start()
    }

    function actionColor() {
        if (actionKind === "scan")
            return theme.accent
        if (actionKind === "focus")
            return theme.spectrum
        return theme.violet
    }

    onReducedMotionChanged: {
        if (reducedMotion)
            root.settle()
    }
    onMotionEnabledChanged: {
        if (!motionEnabled)
            root.settle()
    }

    Connections {
        target: root.theme
        function onDohnaChanged() {
            if (!root.theme.dohna)
                root.settle()
        }
    }

    // Action feedback is a sticker-sized hit near the workbench edge. The
    // real button/capture event remains the source of the action kind.
    Rectangle {
        objectName: "dohnaActionImpactShadow"
        visible: root.actionPulseRunning
        x: root.width * 0.62 - 6 + root.actionProgress * 16
        y: root.height * 0.35 + 5
        width: 148
        height: 18
        rotation: 4
        color: root.theme.stageShadow
    }

    Rectangle {
        objectName: "dohnaActionImpact"
        visible: root.actionPulseRunning
        x: root.width * 0.62 + root.actionProgress * 16
        y: root.height * 0.35
        width: 148
        height: 18
        rotation: 4
        color: root.actionColor()
    }

    Rectangle {
        objectName: "dohnaActionImpactTag"
        visible: root.actionPulseRunning
        x: root.width * 0.62 + 112 + root.actionProgress * 16
        y: root.height * 0.35 - 5
        width: 26
        height: 8
        rotation: -8
        color: root.theme.violet
    }

    // Start feedback uses two offset marks instead of a full-window beam.
    Rectangle {
        objectName: "dohnaStartImpact"
        visible: root.startPulseRunning
        x: -width + (root.width * 0.7 + width) * root.startProgress
        y: root.height * 0.56
        width: Math.min(230, root.width * 0.28)
        height: 10
        rotation: -5
        color: root.theme.accent
    }

    Rectangle {
        objectName: "dohnaStartImpactTag"
        visible: root.startPulseRunning
        x: -width + (root.width * 0.7 + width) * root.startProgress + 34
        y: root.height * 0.56 + 12
        width: Math.min(150, root.width * 0.2)
        height: 7
        rotation: -5
        color: root.theme.spectrum
    }

    // Warnings are a yellow paper tab, never a screen flash.
    Shape {
        objectName: "dohnaWarningImpact"
        visible: root.warningPulseRunning
        x: root.width * 0.44
        y: 18
        width: 180
        height: 30
        rotation: 3
        opacity: Math.sin(Math.PI * root.warningProgress)
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.theme.ink
            strokeWidth: 2
            fillColor: root.theme.violet
            startX: 0
            startY: 0
            PathLine { x: 164; y: 0 }
            PathLine { x: 180; y: 30 }
            PathLine { x: 12; y: 30 }
            PathLine { x: 0; y: 0 }
        }
    }

    SequentialAnimation {
        id: actionPulse
        onStopped: root.actionActive = false
        PropertyAction { target: root; property: "actionProgress"; value: 0 }
        NumberAnimation {
            target: root
            property: "actionProgress"
            to: 1
            duration: root.theme.popActionMotion
            easing.type: Easing.OutBack
        }
    }

    SequentialAnimation {
        id: startPulse
        onStopped: root.startActive = false
        PropertyAction { target: root; property: "startProgress"; value: 0 }
        NumberAnimation {
            target: root
            property: "startProgress"
            to: 1
            duration: root.theme.popStartMotion
            easing.type: Easing.OutCubic
        }
    }

    SequentialAnimation {
        id: warningPulse
        onStopped: root.warningActive = false
        PropertyAction { target: root; property: "warningProgress"; value: 0 }
        NumberAnimation {
            target: root
            property: "warningProgress"
            to: 1
            duration: root.theme.popWarningMotion
            easing.type: Easing.InOutCubic
        }
    }
}
