pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var theme
    property bool reducedMotion: false
    property bool motionEnabled: false
    property int warningSequence: 0
    property real warningProgress: 1
    property bool warningActive: false
    readonly property bool warningPulseRunning: warningPulse.running && warningActive

    enabled: false
    z: 20
    visible: root.theme.dohna && root.motionEnabled

    function settle() {
        warningPulse.stop()
        warningActive = false
        warningProgress = 1
    }

    function pulseAction(kind) {
        // Dohna controls provide their feedback locally; global action strips
        // obscured unrelated controls because this layer spans the whole page.
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
        // Starting translation keeps the button's own pressed state and the
        // existing prelude timing, without a page-wide colored strip.
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
