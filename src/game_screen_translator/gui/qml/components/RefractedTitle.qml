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
    readonly property real facetWidthRatio: 0.11
    readonly property real facetAngle: 10
    readonly property real cyanFacetOpacity: theme.dark ? 0.9 : 0.72
    readonly property real spectrumFacetOpacity: theme.dark ? 0.68 : 0.56
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
        refractionShift = 6
        refractionEnergy = 0
    }

    function playRefraction() {
        if (!motionEnabled || theme.reducedMotion) {
            settleRefraction()
            return
        }
        refractionKick.restart()
    }

    onTransitionSequenceChanged: Qt.callLater(root.playRefraction)
    onMotionEnabledChanged: {
        if (!motionEnabled)
            settleRefraction()
    }
    Connections {
        target: root.theme
        function onReducedMotionChanged() {
            if (root.theme.reducedMotion)
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
        font.weight: Font.Light
        font.letterSpacing: -root.titleSize * 0.035
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
    }

    Item {
        id: heavyEffects
        objectName: "pageTitleHeavyEffects"
        x: displayTitleHeavy.x
        y: 0
        width: displayTitleHeavy.width
        height: root.height
        clip: true
        z: 2

        Item {
            id: cyanFacet
            objectName: "pageTitleCyanSlice"
            readonly property real chromaticOffset: 2.5
            x: heavyEffects.width * 0.445
            y: -heavyEffects.height * 0.08
            width: Math.max(8, heavyEffects.width * root.facetWidthRatio)
            height: heavyEffects.height * 1.16
            rotation: root.facetAngle
            transformOrigin: Item.Center
            clip: true

            Item {
                x: -cyanFacet.x
                y: -cyanFacet.y
                width: heavyEffects.width
                height: heavyEffects.height
                transform: Rotation {
                    objectName: "pageTitleCyanCounterRotation"
                    origin.x: cyanFacet.x + cyanFacet.width / 2
                    origin.y: cyanFacet.y + cyanFacet.height / 2
                    angle: -cyanFacet.rotation
                }

                Text {
                    x: root.refractionShift + cyanFacet.chromaticOffset
                    y: displayTitleHeavy.y
                    text: displayTitleHeavy.text
                    color: root.theme.accent
                    opacity: root.cyanFacetOpacity
                    font: displayTitleHeavy.font
                }
            }
        }

        Item {
            id: spectrumFacet
            objectName: "pageTitleSpectrumSlice"
            readonly property real chromaticOffset: 5.5
            x: cyanFacet.x
            y: cyanFacet.y
            width: cyanFacet.width
            height: cyanFacet.height
            rotation: cyanFacet.rotation
            transformOrigin: Item.Center
            clip: true

            Item {
                x: -spectrumFacet.x
                y: -spectrumFacet.y
                width: heavyEffects.width
                height: heavyEffects.height
                transform: Rotation {
                    objectName: "pageTitleSpectrumCounterRotation"
                    origin.x: spectrumFacet.x + spectrumFacet.width / 2
                    origin.y: spectrumFacet.y + spectrumFacet.height / 2
                    angle: -spectrumFacet.rotation
                }

                Text {
                    x: root.refractionShift + spectrumFacet.chromaticOffset
                    y: displayTitleHeavy.y
                    text: displayTitleHeavy.text
                    color: root.theme.spectrum
                    opacity: root.spectrumFacetOpacity
                    font: displayTitleHeavy.font
                }
            }
        }

        Rectangle {
            id: cyanEdge
            objectName: "pageTitleCyanEdge"
            x: heavyEffects.width * 0.49
            y: -heavyEffects.height * 0.08
            width: 1.5
            height: heavyEffects.height * 1.16
            color: root.theme.accent
            opacity: 0.72 + root.refractionEnergy * 0.18
            rotation: root.facetAngle
            transformOrigin: Item.Center
        }

        Rectangle {
            objectName: "pageTitleSpectrumEdge"
            x: cyanEdge.x + 4
            y: cyanEdge.y
            width: 1.5
            height: cyanEdge.height
            color: root.theme.spectrum
            opacity: 0.58 + root.refractionEnergy * 0.2
            rotation: root.facetAngle
            transformOrigin: Item.Center
        }
    }

    SequentialAnimation {
        id: refractionKick
        onStopped: {
            root.refractionShift = 6
            root.refractionEnergy = 0
        }
        PropertyAction { target: root; property: "refractionShift"; value: 11 }
        PropertyAction { target: root; property: "refractionEnergy"; value: 1 }
        ParallelAnimation {
            NumberAnimation {
                target: root
                property: "refractionShift"
                to: 6
                duration: 240
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: root
                property: "refractionEnergy"
                to: 0
                duration: 280
                easing.type: Easing.OutCubic
            }
        }
    }
}
