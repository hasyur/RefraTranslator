import QtQuick

Item {
    id: root

    required property var theme
    property string lightText: ""
    property string heavyText: ""
    property real titleSize: 64
    property int transitionSequence: 0
    property bool motionEnabled: false
    readonly property real heavyTitleSize: titleSize * 0.94
    readonly property bool refractionRunning: refractionKick.running
    property real refractionShift: 6
    property real refractionEnergy: 0

    implicitWidth: displayTitleHeavy.x + displayTitleHeavy.implicitWidth
    implicitHeight: Math.ceil(Math.max(
        displayTitleLight.implicitHeight,
        displayTitleHeavy.implicitHeight
    ) + 10)
    clip: false

    function settleRefraction() {
        refractionKick.stop()
        refractionShift = 3
        refractionEnergy = 0
    }

    function playRefraction() {
        if (!theme.dohna || !motionEnabled || theme.reducedMotion) {
            settleRefraction()
            return
        }
        refractionKick.restart()
    }

    onTransitionSequenceChanged: Qt.callLater(root.playRefraction)
    onMotionEnabledChanged: {
        if (!motionEnabled)
            settleRefraction()
        else
            playRefraction()
    }
    Connections {
        target: root.theme
        function onReducedMotionChanged() {
            if (root.theme.reducedMotion)
                root.settleRefraction()
        }
        function onDohnaChanged() {
            root.settleRefraction()
        }
    }

    Text {
        id: displayTitleLight
        objectName: "pageDisplayTitleLight"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        text: root.lightText
        color: root.theme.text
        font.family: root.theme.displayFontFor(text)
        font.pixelSize: root.titleSize
        font.weight: Font.Bold
        font.letterSpacing: 0
        renderType: Text.CurveRendering
        renderTypeQuality: Text.VeryHighRenderTypeQuality
        transform: Translate {
            x: root.theme.dohna ? -root.refractionEnergy * 10 : 0
            y: root.theme.dohna ? -root.refractionEnergy * 2 : 0
        }
    }

    Text {
        id: displayTitleHeavy
        objectName: "pageDisplayTitleHeavy"
        anchors.left: displayTitleLight.right
        anchors.leftMargin: root.titleSize * 0.1
        anchors.verticalCenter: parent.verticalCenter
        text: root.heavyText
        color: root.theme.text
        font.family: root.theme.displayFontFor(text)
        font.pixelSize: root.heavyTitleSize
        font.weight: Font.Bold
        font.letterSpacing: -root.titleSize * 0.035
        renderType: Text.CurveRendering
        renderTypeQuality: Text.VeryHighRenderTypeQuality
    }

    SequentialAnimation {
        id: refractionKick
        onStopped: {
            root.refractionShift = 3
            root.refractionEnergy = 0
        }
        PropertyAction { target: root; property: "refractionShift"; value: 6 }
        PropertyAction { target: root; property: "refractionEnergy"; value: 1 }
        ParallelAnimation {
            NumberAnimation {
                target: root
                property: "refractionShift"
                to: 3
                duration: root.theme.dohna ? root.theme.popActionMotion : 175
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: root
                property: "refractionEnergy"
                to: 0
                duration: root.theme.dohna ? root.theme.popPageMotion : 205
                easing.type: Easing.OutCubic
            }
        }
    }
}
