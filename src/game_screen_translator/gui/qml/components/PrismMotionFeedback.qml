import QtQuick

Item {
    id: root

    required property var theme
    property bool reducedMotion: false
    property bool motionEnabled: false
    property int pageTransitionSequence: 0
    property int actionSequence: 0
    property int startPreludeSequence: 0
    property int warningSequence: 0
    property string actionKind: ""
    property real actionProgress: 1
    property real startProgress: 1
    property real warningProgress: 1

    readonly property bool pageTransitionRunning: false
    readonly property bool actionPulseRunning: actionPulse.running
    readonly property bool startPreludeRunning: startPrelude.running
    readonly property bool warningPulseRunning: warningPulse.running

    visible: false

    function pulseAction(kind) {
        actionKind = kind
        actionSequence += 1
        if (reducedMotion || !motionEnabled) {
            actionPulse.stop()
            actionProgress = 1
            return
        }
        actionPulse.restart()
    }

    function pulseStart() {
        startPreludeSequence += 1
        if (reducedMotion || !motionEnabled) {
            startPrelude.stop()
            startProgress = 1
            return
        }
        startPrelude.restart()
    }

    function pulseWarning() {
        warningSequence += 1
        if (reducedMotion || !motionEnabled) {
            warningPulse.stop()
            warningProgress = 1
            return
        }
        warningPulse.restart()
    }

    function settleMotion() {
        actionPulse.stop()
        startPrelude.stop()
        warningPulse.stop()
        actionProgress = 1
        startProgress = 1
        warningProgress = 1
    }

    onReducedMotionChanged: {
        if (reducedMotion)
            settleMotion()
    }
    onMotionEnabledChanged: {
        if (!motionEnabled)
            settleMotion()
    }

    SequentialAnimation {
        id: actionPulse
        PropertyAction { target: root; property: "actionProgress"; value: 0 }
        NumberAnimation {
            target: root
            property: "actionProgress"
            to: 1
            duration: root.theme.actionMotion
            easing.type: Easing.OutCubic
        }
    }

    SequentialAnimation {
        id: startPrelude
        PropertyAction { target: root; property: "startProgress"; value: 0 }
        NumberAnimation {
            target: root
            property: "startProgress"
            to: 1
            duration: root.theme.startPreludeMotion
            easing.type: Easing.InOutCubic
        }
    }

    SequentialAnimation {
        id: warningPulse
        PropertyAction { target: root; property: "warningProgress"; value: 0 }
        NumberAnimation {
            target: root
            property: "warningProgress"
            to: 1
            duration: root.theme.warningMotion
            easing.type: Easing.OutCubic
        }
    }
}
