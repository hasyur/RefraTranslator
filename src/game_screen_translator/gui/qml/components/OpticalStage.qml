pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var theme
    property string page: "HOME"
    property bool reducedMotion: false
    property bool motionEnabled: false
    property real parallaxX: 0
    property real parallaxY: 0
    property string actionKind: ""
    property int actionSequence: 0
    property int pageTransitionSequence: 0
    property int startPreludeSequence: 0
    property real actionProgress: 1
    property real startProgress: 1
    readonly property bool pageTransitionRunning: pageEntry.running
    readonly property bool actionPulseRunning: actionPulse.running
    readonly property bool startPreludeRunning: startPrelude.running
    readonly property real actionEmphasis: actionPulseRunning
                                                   ? Math.sin(Math.PI * actionProgress)
                                                   : 0
    readonly property real deviceVisualOffsetX: deviceTranslate.x
    readonly property real deviceVisualOpacity: device.opacity

    clip: true

    function pulseWarning() {
        if (!reducedMotion && motionEnabled)
            warningPulse.restart()
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

    function settleMotion() {
        warningPulse.stop()
        pageEntry.stop()
        actionPulse.stop()
        startPrelude.stop()
        warningPulse.running = false
        pageEntry.running = false
        actionPulse.running = false
        startPrelude.running = false
        warningWash.opacity = 0
        movingLayer.opacity = 1
        device.opacity = 1
        deviceTranslate.x = 0
        stageSweep.opacity = 0
        actionProgress = 1
        startProgress = 1
        aura.opacity = 0.65
        cyanBeam.opacity = 0.36
        parallaxX = 0
        parallaxY = 0
        Qt.callLater(root.finishSettlingMotion)
    }

    function finishSettlingMotion() {
        if (!reducedMotion && motionEnabled)
            return
        warningPulse.stop()
        pageEntry.stop()
        actionPulse.stop()
        startPrelude.stop()
        warningPulse.running = false
        pageEntry.running = false
        actionPulse.running = false
        startPrelude.running = false
    }

    onPageChanged: {
        pageTransitionSequence += 1
        if (!reducedMotion && motionEnabled)
            pageEntry.restart()
        else {
            device.opacity = 1
            deviceTranslate.x = 0
            stageSweep.opacity = 0
        }
    }
    onReducedMotionChanged: {
        if (reducedMotion)
            settleMotion()
    }
    onMotionEnabledChanged: {
        if (!motionEnabled)
            settleMotion()
    }

    HoverHandler {
        id: hover
        acceptedDevices: PointerDevice.Mouse
        onPointChanged: {
            if (root.reducedMotion || root.width <= 0 || root.height <= 0)
                return
            root.parallaxX = Math.max(-8, Math.min(8, (point.position.x / root.width - 0.5) * 16))
            root.parallaxY = Math.max(-8, Math.min(8, (point.position.y / root.height - 0.5) * 16))
        }
        onHoveredChanged: {
            if (!hovered) {
                root.parallaxX = 0
                root.parallaxY = 0
            }
        }
    }

    Rectangle {
        objectName: "opticalStageFrame"
        anchors.fill: parent
        color: "transparent"
        border.color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.22)
        border.width: 1.5
    }

    Repeater {
        model: 11
        Rectangle {
            required property int index
            x: index * root.width / 10
            width: 1
            height: root.height
            color: root.theme.line
            opacity: 0.17
        }
    }
    Repeater {
        model: 8
        Rectangle {
            required property int index
            y: index * root.height / 7
            width: root.width
            height: 1
            color: root.theme.line
            opacity: 0.17
        }
    }

    Item {
        id: movingLayer
        anchors.fill: parent
        x: root.reducedMotion ? 0 : root.parallaxX
        y: root.reducedMotion ? 0 : root.parallaxY

        Behavior on x { NumberAnimation { duration: root.theme.panelMotion; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: root.theme.panelMotion; easing.type: Easing.OutCubic } }

        Rectangle {
            id: aura
            width: parent.width * 0.7
            height: parent.height * 0.28
            x: parent.width * 0.24
            y: -parent.height * 0.04
            rotation: -10
            color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.075 : 0.05)
            opacity: 0.65

            SequentialAnimation {
                running: root.motionEnabled
                loops: Animation.Infinite
                NumberAnimation { target: aura; property: "opacity"; to: 0.34; duration: 8000; easing.type: Easing.InOutSine }
                NumberAnimation { target: aura; property: "opacity"; to: 0.68; duration: 8000; easing.type: Easing.InOutSine }
            }
        }

        Rectangle {
            id: cyanBeam
            width: parent.width * 0.9
            height: 2
            x: parent.width * 0.06
            y: parent.height * 0.46
            rotation: 4
            color: root.theme.accent
            opacity: 0.36

            SequentialAnimation {
                running: root.motionEnabled
                loops: Animation.Infinite
                NumberAnimation { target: cyanBeam; property: "opacity"; to: 0.18; duration: 9000; easing.type: Easing.InOutSine }
                NumberAnimation { target: cyanBeam; property: "opacity"; to: 0.46; duration: 9000; easing.type: Easing.InOutSine }
            }
        }
        Rectangle {
            width: parent.width * 0.76
            height: 2
            x: parent.width * 0.19
            y: parent.height * 0.55
            rotation: -5
            color: root.theme.spectrum
            opacity: 0.3
        }

        Item {
            id: device
            width: 1000
            height: 600
            anchors.centerIn: parent
            scale: Math.min(parent.width / width, parent.height / height) * 0.94
            transform: Translate { id: deviceTranslate; x: 0 }

            // HOME / refraction core
            Item {
                anchors.fill: parent
                visible: root.page === "HOME"

                Rectangle { x: 72; y: 294; width: 360; height: 3; color: root.theme.accent; opacity: 0.7 }
                Rectangle { x: 490; y: 266; width: 438; height: 3; color: root.theme.accent; opacity: 0.6 }
                Rectangle { x: 478; y: 324; width: 450; height: 3; color: root.theme.spectrum; opacity: 0.56 }
                Shape {
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.theme.accent
                        strokeWidth: 3
                        fillColor: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.07)
                        startX: 438; startY: 86
                        PathLine { x: 532; y: 86 }
                        PathLine { x: 452; y: 520 }
                        PathLine { x: 358; y: 520 }
                        PathLine { x: 438; y: 86 }
                    }
                    ShapePath {
                        strokeColor: root.theme.spectrum
                        strokeWidth: 2
                        fillColor: "transparent"
                        startX: 448; startY: 86
                        PathLine { x: 368; y: 520 }
                    }
                }
            }

            // CAPTURE / viewfinder aperture
            Item {
                id: captureMotif
                objectName: "captureStageMotif"
                anchors.fill: parent
                visible: root.page === "CAPTURE"
                readonly property bool actionLinked: visible
                                                     && root.actionPulseRunning
                                                     && root.actionKind === "scan"
                readonly property real emphasis: actionLinked
                                                 ? root.actionEmphasis
                                                 : 0

                Rectangle {
                    objectName: "captureStageFrame"
                    x: 205
                    y: 120
                    width: 590
                    height: 350
                    color: "transparent"
                    border.color: root.theme.accent
                    border.width: 3 + captureMotif.emphasis * 2
                    opacity: 0.62 + captureMotif.emphasis * 0.3
                }
                Rectangle {
                    x: 492
                    y: 178
                    width: 3 + captureMotif.emphasis * 2
                    height: 234
                    color: root.theme.accent
                    opacity: 0.48 + captureMotif.emphasis * 0.34
                }
                Rectangle {
                    objectName: "captureStageScanLine"
                    x: captureMotif.actionLinked ? 205 : 374
                    y: captureMotif.actionLinked
                       ? 120 + 350 * root.actionProgress
                       : 294
                    width: captureMotif.actionLinked ? 590 : 238
                    height: 3 + captureMotif.emphasis * 2
                    color: root.theme.accent
                    opacity: captureMotif.actionLinked
                             ? 0.18 + captureMotif.emphasis * 0.78
                             : 0.48

                    Rectangle {
                        visible: captureMotif.actionLinked
                        anchors.centerIn: parent
                        width: parent.width
                        height: 22
                        color: Qt.rgba(root.theme.accent.r,
                                       root.theme.accent.g,
                                       root.theme.accent.b,
                                       0.12 + captureMotif.emphasis * 0.1)
                    }
                }
                Rectangle {
                    x: 448
                    y: 252
                    width: 88
                    height: 88
                    radius: 44
                    scale: 1 + captureMotif.emphasis * 0.14
                    color: "transparent"
                    border.color: root.theme.spectrum
                    border.width: 3 + captureMotif.emphasis * 1.5
                    opacity: 0.76 + captureMotif.emphasis * 0.24
                }
                Repeater {
                    model: 12
                    Rectangle {
                        required property int index
                        x: 205 + index * 53.6
                        y: 108
                        width: 1
                        height: index % 2 === 0 ? 18 : 10
                        color: root.theme.lineStrong
                        opacity: 0.65 + captureMotif.emphasis * 0.35
                    }
                }
            }

            // OCR / recognition matrix
            Item {
                id: ocrMotif
                objectName: "ocrStageMotif"
                anchors.fill: parent
                visible: root.page === "OCR"
                readonly property bool actionLinked: visible
                                                     && root.actionPulseRunning
                                                     && root.actionKind === "focus"
                readonly property real emphasis: actionLinked
                                                 ? root.actionEmphasis
                                                 : 0

                function focusAmount(index) {
                    if (!actionLinked)
                        return 0
                    const localProgress = Math.max(
                        0,
                        Math.min(1, (root.actionProgress - index * 0.12) / 0.76)
                    )
                    return Math.sin(Math.PI * localProgress)
                }

                Repeater {
                    model: [
                        {"x": 150, "y": 145, "w": 310, "h": 82},
                        {"x": 525, "y": 270, "w": 270, "h": 68},
                        {"x": 260, "y": 408, "w": 230, "h": 58}
                    ]
                    Rectangle {
                        objectName: "ocrStageFocusBox" + index
                        required property int index
                        required property var modelData
                        readonly property real focusAmount: ocrMotif.focusAmount(index)
                        x: modelData.x; y: modelData.y
                        width: modelData.w; height: modelData.h
                        scale: 1 - focusAmount * 0.07
                        color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.025)
                        border.color: root.theme.accent
                        border.width: 3 + focusAmount * 2
                        opacity: 0.68 + focusAmount * 0.3
                    }
                }
                Rectangle {
                    objectName: "ocrStageSignalLine"
                    x: 110
                    y: 302
                    width: 430 * (ocrMotif.actionLinked
                                  ? Math.max(0.08, root.actionProgress)
                                  : 1)
                    height: 3 + ocrMotif.emphasis * 1.5
                    color: root.theme.spectrum
                    opacity: 0.58 + ocrMotif.emphasis * 0.34
                }
                Rectangle {
                    x: 536
                    y: 295
                    width: 14
                    height: 14
                    radius: 7
                    scale: 1 + ocrMotif.focusAmount(1) * 0.5
                    color: root.theme.spectrum
                    opacity: 0.72 + ocrMotif.focusAmount(1) * 0.28
                }
            }

            // TRANSLATION / bilingual splitter
            Item {
                id: translationMotif
                objectName: "translationStageMotif"
                anchors.fill: parent
                visible: root.page === "TRANSLATION"
                readonly property bool actionLinked: visible
                                                     && root.actionPulseRunning
                                                     && root.actionKind === "trace"
                readonly property real emphasis: actionLinked
                                                 ? root.actionEmphasis
                                                 : 0

                function traceProgress(index) {
                    if (!actionLinked)
                        return 1
                    const delay = index * 0.1
                    return Math.max(
                        0,
                        Math.min(1, (root.actionProgress - delay) / (1 - delay))
                    )
                }

                Rectangle {
                    x: 52
                    y: 298
                    width: 350 * (translationMotif.actionLinked
                                  ? Math.min(1, root.actionProgress / 0.38)
                                  : 1)
                    height: 3 + translationMotif.emphasis
                    color: root.theme.textSoft
                    opacity: 0.5 + translationMotif.emphasis * 0.32
                }
                Rectangle {
                    objectName: "translationStageTracePrimary"
                    readonly property real drawProgress: translationMotif.traceProgress(0)
                    x: 478
                    y: 260
                    width: 472 * drawProgress
                    height: 3 + translationMotif.emphasis * 1.5
                    color: root.theme.accent
                    opacity: 0.68 + translationMotif.emphasis * 0.3
                }
                Rectangle {
                    objectName: "translationStageTraceSecondary"
                    readonly property real drawProgress: translationMotif.traceProgress(1)
                    x: 478
                    y: 302
                    width: 472 * drawProgress
                    height: 3 + translationMotif.emphasis * 1.5
                    color: root.theme.violet
                    opacity: 0.56 + translationMotif.emphasis * 0.38
                }
                Rectangle {
                    objectName: "translationStageTraceTertiary"
                    readonly property real drawProgress: translationMotif.traceProgress(2)
                    x: 478
                    y: 344
                    width: 472 * drawProgress
                    height: 3 + translationMotif.emphasis * 1.5
                    color: root.theme.spectrum
                    opacity: 0.68 + translationMotif.emphasis * 0.3
                }
                Shape {
                    anchors.fill: parent
                    scale: 1 + translationMotif.emphasis * 0.035
                    opacity: 0.72 + translationMotif.emphasis * 0.28
                    ShapePath {
                        strokeColor: root.theme.accent
                        strokeWidth: 3 + translationMotif.emphasis * 1.5
                        fillColor: Qt.rgba(root.theme.violet.r, root.theme.violet.g, root.theme.violet.b, 0.07)
                        startX: 405; startY: 96
                        PathLine { x: 512; y: 96 }
                        PathLine { x: 466; y: 510 }
                        PathLine { x: 358; y: 510 }
                        PathLine { x: 405; y: 96 }
                    }
                }
                Rectangle {
                    x: 760
                    y: 205
                    width: 190
                    height: 190
                    scale: 1 + translationMotif.emphasis * 0.08
                    color: "transparent"
                    border.color: root.theme.lineStrong
                    border.width: 1 + translationMotif.emphasis
                }
            }

            // OVERLAY / projection stack
            Item {
                id: overlayMotif
                objectName: "overlayStageMotif"
                anchors.fill: parent
                visible: root.page === "OVERLAY"
                readonly property bool actionLinked: visible
                                                     && root.actionPulseRunning
                                                     && root.actionKind === "projection"
                readonly property real emphasis: actionLinked
                                                 ? root.actionEmphasis
                                                 : 0
                readonly property real spread: emphasis * 34

                Shape {
                    objectName: "overlayStageFarPlane"
                    width: parent.width
                    height: parent.height
                    x: -overlayMotif.spread
                    y: -overlayMotif.spread * 0.22
                    opacity: 0.76 + overlayMotif.emphasis * 0.24
                    ShapePath {
                        strokeColor: root.theme.lineStrong
                        strokeWidth: 3 + overlayMotif.emphasis * 1.5
                        fillColor: Qt.rgba(root.theme.lineStrong.r,
                                           root.theme.lineStrong.g,
                                           root.theme.lineStrong.b,
                                           0.08 + overlayMotif.emphasis * 0.06)
                        startX: 172; startY: 128
                        PathLine { x: 760; y: 92 }
                        PathLine { x: 875; y: 420 }
                        PathLine { x: 282; y: 472 }
                        PathLine { x: 172; y: 128 }
                    }
                }
                Shape {
                    objectName: "overlayStageMiddlePlane"
                    width: parent.width
                    height: parent.height
                    opacity: 0.82 + overlayMotif.emphasis * 0.18
                    ShapePath {
                        strokeColor: root.theme.spectrum
                        strokeWidth: 3 + overlayMotif.emphasis * 1.5
                        fillColor: Qt.rgba(root.theme.spectrum.r,
                                           root.theme.spectrum.g,
                                           root.theme.spectrum.b,
                                           0.07 + overlayMotif.emphasis * 0.06)
                        startX: 216; startY: 170
                        PathLine { x: 804; y: 134 }
                        PathLine { x: 919; y: 462 }
                        PathLine { x: 326; y: 514 }
                        PathLine { x: 216; y: 170 }
                    }
                }
                Shape {
                    objectName: "overlayStageNearPlane"
                    width: parent.width
                    height: parent.height
                    x: overlayMotif.spread
                    y: overlayMotif.spread * 0.22
                    opacity: 0.76 + overlayMotif.emphasis * 0.24
                    ShapePath {
                        strokeColor: root.theme.accent
                        strokeWidth: 3 + overlayMotif.emphasis * 1.5
                        fillColor: Qt.rgba(root.theme.accent.r,
                                           root.theme.accent.g,
                                           root.theme.accent.b,
                                           0.08 + overlayMotif.emphasis * 0.06)
                        startX: 260; startY: 212
                        PathLine { x: 848; y: 176 }
                        PathLine { x: 963; y: 504 }
                        PathLine { x: 370; y: 556 }
                        PathLine { x: 260; y: 212 }
                    }
                }
            }

            // CACHE / spectrum memory array
            Item {
                id: cacheMotif
                objectName: "cacheStageMotif"
                anchors.fill: parent
                visible: root.page === "CACHE"
                readonly property bool actionLinked: visible
                                                     && root.actionPulseRunning
                                                     && root.actionKind === "ripple"

                function waveAmount(index) {
                    if (!actionLinked)
                        return 0
                    const localProgress = root.actionProgress * 1.5 - index * 0.12
                    if (localProgress <= 0 || localProgress >= 1)
                        return 0
                    return Math.sin(Math.PI * localProgress)
                }

                Repeater {
                    model: 5
                    Rectangle {
                        objectName: "cacheStageRail" + index
                        required property int index
                        readonly property real waveAmount: cacheMotif.waveAmount(index)
                        x: 98
                        y: 142 + index * 74
                        width: 802
                        height: 3 + waveAmount * 2
                        color: index === 2 ? root.theme.spectrum : index === 3 ? root.theme.violet : root.theme.accent
                        opacity: 0.34 + index * 0.035 + waveAmount * 0.48
                        Rectangle {
                            x: parent.width * (0.38 + parent.waveAmount * 0.18)
                            y: -4
                            width: 10
                            height: 10
                            radius: 5
                            scale: 1 + parent.waveAmount * 0.55
                            color: parent.color
                        }
                    }
                }
            }

            // SETTINGS / calibration console
            Item {
                id: settingsMotif
                objectName: "settingsStageMotif"
                anchors.fill: parent
                visible: root.page === "SETTINGS"
                readonly property bool actionLinked: visible
                                                     && root.actionPulseRunning
                                                     && root.actionKind === "calibrate"
                readonly property real emphasis: actionLinked
                                                 ? root.actionEmphasis
                                                 : 0

                function railAmount(index) {
                    if (!actionLinked)
                        return 0
                    const delay = (index % 3) * 0.08
                    const localProgress = Math.max(
                        0,
                        Math.min(1, (root.actionProgress - delay) / (1 - delay))
                    )
                    return Math.sin(Math.PI * localProgress)
                }

                Item {
                    objectName: "settingsStageCalibrationTarget"
                    x: 380
                    y: 150
                    width: 240
                    height: 240
                    rotation: settingsMotif.actionLinked
                              ? Math.sin(Math.PI * root.actionProgress) * 42
                              : 0
                    scale: 1 + settingsMotif.emphasis * 0.09

                    Rectangle {
                        anchors.centerIn: parent
                        width: 152
                        height: 152
                        radius: 76
                        color: "transparent"
                        border.color: root.theme.accent
                        border.width: 3 + settingsMotif.emphasis * 2
                        opacity: 0.62 + settingsMotif.emphasis * 0.34
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 3 + settingsMotif.emphasis * 1.5
                        height: parent.height
                        color: root.theme.accent
                        opacity: 0.48 + settingsMotif.emphasis * 0.38
                    }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: 3 + settingsMotif.emphasis * 1.5
                        color: root.theme.accent
                        opacity: 0.48 + settingsMotif.emphasis * 0.38
                    }
                }
                Repeater {
                    model: 6
                    Rectangle {
                        objectName: "settingsStageRail" + index
                        required property int index
                        readonly property real responseAmount: settingsMotif.railAmount(index)
                        x: index < 3 ? 90 : 705
                        y: 160 + (index % 3) * 110
                        width: 210 + responseAmount * 34
                        height: 2 + responseAmount * 1.5
                        color: index % 2 ? root.theme.spectrum : root.theme.lineStrong
                        opacity: 0.55 + responseAmount * 0.4
                    }
                }
            }
        }
    }

    Rectangle {
        id: stageSweep
        objectName: "stagePrismSweep"
        readonly property real accentAlpha: root.theme.sweepAccentAlpha
        readonly property real spectrumAlpha: root.theme.sweepSpectrumAlpha
        width: Math.max(150, root.width * 0.22)
        height: root.height * 1.35
        y: -root.height * 0.18
        rotation: -11
        opacity: 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 0.46; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, stageSweep.accentAlpha) }
            GradientStop { position: 0.6; color: Qt.rgba(root.theme.spectrum.r, root.theme.spectrum.g, root.theme.spectrum.b, stageSweep.spectrumAlpha) }
            GradientStop { position: 1; color: "transparent" }
        }
        Rectangle {
            objectName: "stagePrismSweepCore"
            anchors.centerIn: parent
            width: 2
            height: parent.height
            color: root.theme.text
            opacity: 0.58
        }
    }

    Rectangle {
        id: warningWash
        anchors.fill: parent
        color: root.theme.amber
        opacity: 0
    }

    SequentialAnimation {
        id: warningPulse
        PropertyAction { target: warningWash; property: "opacity"; value: 0 }
        NumberAnimation { target: warningWash; property: "opacity"; to: 0.16; duration: 190; easing.type: Easing.OutCubic }
        NumberAnimation { target: warningWash; property: "opacity"; to: 0; duration: 590; easing.type: Easing.InCubic }
    }

    ParallelAnimation {
        id: pageEntry
        SequentialAnimation {
            PropertyAction { target: movingLayer; property: "opacity"; value: 0.18 }
            NumberAnimation { target: movingLayer; property: "opacity"; to: 1; duration: root.theme.pageMotion; easing.type: Easing.OutCubic }
        }
        SequentialAnimation {
            PropertyAction { target: device; property: "opacity"; value: 0.04 }
            PropertyAction { target: deviceTranslate; property: "x"; value: 18 }
            PauseAnimation { duration: root.theme.deviceEntryDelay }
            ParallelAnimation {
                NumberAnimation { target: device; property: "opacity"; to: 1; duration: root.theme.pageMotion; easing.type: Easing.OutCubic }
                NumberAnimation { target: deviceTranslate; property: "x"; to: 0; duration: root.theme.pageMotion; easing.type: Easing.OutCubic }
            }
        }
        SequentialAnimation {
            PropertyAction { target: stageSweep; property: "x"; value: -stageSweep.width }
            PropertyAction { target: stageSweep; property: "opacity"; value: 0 }
            ParallelAnimation {
                NumberAnimation { target: stageSweep; property: "x"; to: root.width + stageSweep.width; duration: root.theme.pageMotion; easing.type: Easing.InOutCubic }
                SequentialAnimation {
                    NumberAnimation { target: stageSweep; property: "opacity"; to: 1; duration: root.theme.ui }
                    PauseAnimation { duration: root.theme.pageMotion - root.theme.ui * 2 }
                    NumberAnimation { target: stageSweep; property: "opacity"; to: 0; duration: root.theme.ui }
                }
            }
        }
    }

    SequentialAnimation {
        id: actionPulse
        PropertyAction { target: root; property: "actionProgress"; value: 0 }
        NumberAnimation { target: root; property: "actionProgress"; to: 1; duration: root.theme.actionMotion; easing.type: Easing.InOutCubic }
    }

    SequentialAnimation {
        id: startPrelude
        PropertyAction { target: root; property: "startProgress"; value: 0 }
        NumberAnimation { target: root; property: "startProgress"; to: 1; duration: root.theme.startPreludeMotion; easing.type: Easing.InOutCubic }
    }
}
