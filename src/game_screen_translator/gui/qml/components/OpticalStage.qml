pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Shapes
import QtQuick.Window

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
    readonly property real devicePixelRatio: Math.max(1, Screen.devicePixelRatio)
    readonly property real hairlineWidth: 1 / devicePixelRatio
    readonly property real actionEmphasis: actionPulseRunning
                                                   ? Math.sin(Math.PI * actionProgress)
                                                   : 0
    readonly property real deviceVisualOffsetX: deviceTranslate.x
    readonly property real deviceVisualOpacity: device.opacity

    clip: true

    function snapToDevicePixel(value) {
        return Math.round(value * devicePixelRatio) / devicePixelRatio
    }

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
        actionProgress = 1
        startProgress = 1
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

    onPageTransitionSequenceChanged: {
        if (!reducedMotion && motionEnabled)
            pageEntry.restart()
        else {
            device.opacity = 1
            deviceTranslate.x = 0
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

    Rectangle {
        objectName: "opticalStageFrame"
        anchors.fill: parent
        color: "transparent"
        border.color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.22)
        border.width: 1.5
    }

    Item {
        id: movingLayer
        anchors.fill: parent
        x: 0
        y: 0

        Rectangle {
            id: aura
            objectName: "opticalAmbientAura"
            width: parent.width * 0.7
            height: parent.height * 0.28
            x: parent.width * 0.24
            y: -parent.height * 0.04
            rotation: -10
            antialiasing: true
            color: "transparent"
            opacity: 0.72
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.48; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.11 : 0.075) }
                GradientStop { position: 0.72; color: Qt.rgba(root.theme.violet.r, root.theme.violet.g, root.theme.violet.b, root.theme.dark ? 0.075 : 0.05) }
                GradientStop { position: 1; color: "transparent" }
            }
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
                objectName: "homeStageMotif"
                anchors.fill: parent
                visible: root.page === "HOME"

                Shape {
                    objectName: "homeRefractionHousing"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: root.theme.lineStrong
                        strokeWidth: 1
                        fillColor: Qt.rgba(root.theme.accent.r,
                                           root.theme.accent.g,
                                           root.theme.accent.b,
                                           root.theme.dark ? 0.24 : 0.18)
                        startX: 255; startY: 300
                        PathLine { x: 414; y: 104 }
                        PathLine { x: 566; y: 104 }
                        PathLine { x: 745; y: 300 }
                        PathLine { x: 562; y: 500 }
                        PathLine { x: 412; y: 500 }
                        PathLine { x: 255; y: 300 }
                    }
                    ShapePath {
                        strokeColor: "transparent"
                        fillColor: Qt.rgba(root.theme.spectrum.r,
                                           root.theme.spectrum.g,
                                           root.theme.spectrum.b,
                                           root.theme.dark ? 0.26 : 0.19)
                        startX: 414; startY: 104
                        PathLine { x: 490; y: 104 }
                        PathLine { x: 412; y: 500 }
                        PathLine { x: 338; y: 500 }
                        PathLine { x: 414; y: 104 }
                    }
                }
                Rectangle {
                    objectName: "homeRefractionTopGlint"
                    x: 422
                    y: 108
                    width: 126
                    height: 2
                    color: root.theme.text
                    opacity: 0.68
                }

                Rectangle { x: 72; y: 294; width: 360; height: 3; color: root.theme.accent; opacity: 0.7 }
                Rectangle { x: 490; y: 266; width: 438; height: 3; color: root.theme.accent; opacity: 0.6 }
                Rectangle { x: 478; y: 324; width: 450; height: 3; color: root.theme.spectrum; opacity: 0.56 }
                Shape {
                    objectName: "homeRefractionShape"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
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
                    objectName: "captureApertureShadow"
                    x: 196
                    y: 132
                    width: 608
                    height: 364
                    radius: 4
                        color: root.theme.stageShadow
                        opacity: 0.9
                }
                Rectangle {
                    objectName: "captureApertureGlass"
                    x: 205
                    y: 120
                    width: 590
                    height: 350
                    radius: 3
                    border.color: root.theme.lineStrong
                    border.width: 1
                    gradient: Gradient {
                        GradientStop { position: 0; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.28 : 0.21) }
                        GradientStop { position: 0.56; color: Qt.rgba(root.theme.panel.r, root.theme.panel.g, root.theme.panel.b, 0.22) }
                        GradientStop { position: 1; color: Qt.rgba(root.theme.spectrum.r, root.theme.spectrum.g, root.theme.spectrum.b, root.theme.dark ? 0.22 : 0.15) }
                    }
                }
                Rectangle {
                    objectName: "captureApertureTopFacet"
                    x: 205
                    y: 120
                    width: 590
                    height: 2
                    color: root.theme.text
                    opacity: 0.72
                }

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

                Shape {
                    objectName: "ocrMatrixBackplane"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: root.theme.lineStrong
                        strokeWidth: 1
                        fillColor: Qt.rgba(root.theme.violet.r,
                                           root.theme.violet.g,
                                           root.theme.violet.b,
                                           root.theme.dark ? 0.13 : 0.085)
                        startX: 146; startY: 122
                        PathLine { x: 850; y: 172 }
                        PathLine { x: 806; y: 470 }
                        PathLine { x: 196; y: 516 }
                        PathLine { x: 146; y: 122 }
                    }
                }

                Repeater {
                    model: [
                        {"x": 150, "y": 145, "w": 310, "h": 82},
                        {"x": 525, "y": 270, "w": 270, "h": 68},
                        {"x": 260, "y": 408, "w": 230, "h": 58}
                    ]
                    Rectangle {
                        required property var modelData
                        x: modelData.x + 9
                        y: modelData.y + 12
                        width: modelData.w
                        height: modelData.h
                        color: root.theme.stageShadow
                        opacity: 0.82
                    }
                }
                Repeater {
                    model: [
                        {"x": 150, "y": 145, "w": 310, "h": 82},
                        {"x": 525, "y": 270, "w": 270, "h": 68},
                        {"x": 260, "y": 408, "w": 230, "h": 58}
                    ]
                    Rectangle {
                        required property var modelData
                        x: modelData.x
                        y: modelData.y
                        width: modelData.w
                        height: modelData.h
                        color: "transparent"
                        border.color: root.theme.lineStrong
                        border.width: 1
                        gradient: Gradient {
                            GradientStop { position: 0; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.28 : 0.19) }
                            GradientStop { position: 1; color: Qt.rgba(root.theme.spectrum.r, root.theme.spectrum.g, root.theme.spectrum.b, root.theme.dark ? 0.15 : 0.1) }
                        }
                    }
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

                Shape {
                    objectName: "translationSplitterShadow"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: "transparent"
                        fillColor: root.theme.stageShadow
                        startX: 417; startY: 112
                        PathLine { x: 536; y: 112 }
                        PathLine { x: 490; y: 526 }
                        PathLine { x: 370; y: 526 }
                        PathLine { x: 417; y: 112 }
                    }
                }
                Shape {
                    objectName: "translationSplitterBody"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: root.theme.lineStrong
                        strokeWidth: 1
                        fillColor: Qt.rgba(root.theme.accent.r,
                                           root.theme.accent.g,
                                           root.theme.accent.b,
                                           root.theme.dark ? 0.29 : 0.2)
                        startX: 405; startY: 96
                        PathLine { x: 512; y: 96 }
                        PathLine { x: 466; y: 510 }
                        PathLine { x: 358; y: 510 }
                        PathLine { x: 405; y: 96 }
                    }
                    ShapePath {
                        strokeColor: "transparent"
                        fillColor: Qt.rgba(root.theme.spectrum.r,
                                           root.theme.spectrum.g,
                                           root.theme.spectrum.b,
                                           root.theme.dark ? 0.22 : 0.15)
                        startX: 512; startY: 96
                        PathLine { x: 466; y: 510 }
                        PathLine { x: 412; y: 510 }
                        PathLine { x: 458; y: 96 }
                        PathLine { x: 512; y: 96 }
                    }
                }
                Rectangle {
                    objectName: "translationSplitterTopGlint"
                    x: 408
                    y: 100
                    width: 96
                    height: 2
                    color: root.theme.text
                    opacity: 0.46
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
                    objectName: "translationRefractionShape"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
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
                    objectName: "overlayStageShadow"
                    preferredRendererType: Shape.CurveRenderer
                    width: parent.width
                    height: parent.height
                    x: 14
                    y: 16
                    ShapePath {
                        strokeColor: "transparent"
                        fillColor: root.theme.stageShadow
                        startX: 172; startY: 128
                        PathLine { x: 760; y: 92 }
                        PathLine { x: 875; y: 420 }
                        PathLine { x: 282; y: 472 }
                        PathLine { x: 172; y: 128 }
                    }
                }

                Shape {
                    objectName: "overlayStageFarPlane"
                    preferredRendererType: Shape.CurveRenderer
                    width: parent.width
                    height: parent.height
                    x: -overlayMotif.spread
                    y: -overlayMotif.spread * 0.22
                    opacity: 0.76 + overlayMotif.emphasis * 0.24
                    ShapePath {
                        strokeColor: root.theme.lineStrong
                        strokeWidth: 1.5 + overlayMotif.emphasis
                        fillColor: Qt.rgba(root.theme.lineStrong.r,
                                           root.theme.lineStrong.g,
                                           root.theme.lineStrong.b,
                                           0.2 + overlayMotif.emphasis * 0.06)
                        startX: 172; startY: 128
                        PathLine { x: 760; y: 92 }
                        PathLine { x: 875; y: 420 }
                        PathLine { x: 282; y: 472 }
                        PathLine { x: 172; y: 128 }
                    }
                }
                Shape {
                    objectName: "overlayStageMiddlePlane"
                    preferredRendererType: Shape.CurveRenderer
                    width: parent.width
                    height: parent.height
                    opacity: 0.82 + overlayMotif.emphasis * 0.18
                    ShapePath {
                        strokeColor: root.theme.spectrum
                        strokeWidth: 1.5 + overlayMotif.emphasis
                        fillColor: Qt.rgba(root.theme.spectrum.r,
                                           root.theme.spectrum.g,
                                           root.theme.spectrum.b,
                                           0.2 + overlayMotif.emphasis * 0.06)
                        startX: 216; startY: 170
                        PathLine { x: 804; y: 134 }
                        PathLine { x: 919; y: 462 }
                        PathLine { x: 326; y: 514 }
                        PathLine { x: 216; y: 170 }
                    }
                }
                Shape {
                    objectName: "overlayStageNearPlane"
                    preferredRendererType: Shape.CurveRenderer
                    width: parent.width
                    height: parent.height
                    x: overlayMotif.spread
                    y: overlayMotif.spread * 0.22
                    opacity: 0.76 + overlayMotif.emphasis * 0.24
                    ShapePath {
                        strokeColor: root.theme.accent
                        strokeWidth: 1.5 + overlayMotif.emphasis
                        fillColor: Qt.rgba(root.theme.accent.r,
                                           root.theme.accent.g,
                                           root.theme.accent.b,
                                           0.28 + overlayMotif.emphasis * 0.06)
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
                        objectName: "cacheStageTray" + index
                        required property int index
                        x: 88
                        y: 130 + index * 74
                        width: 822
                        height: 52
                        radius: 2
                        color: root.theme.stageShadow
                        opacity: 0.9
                    }
                }
                Repeater {
                    model: 5
                    Rectangle {
                        required property int index
                        x: 98
                        y: 126 + index * 74
                        width: 802
                        height: 48
                        radius: 1
                        border.color: root.theme.lineStrong
                        border.width: 1
                        gradient: Gradient {
                            GradientStop { position: 0; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.19 : 0.13) }
                            GradientStop { position: 0.52; color: Qt.rgba(root.theme.panel.r, root.theme.panel.g, root.theme.panel.b, 0.4) }
                            GradientStop { position: 1; color: Qt.rgba(root.theme.violet.r, root.theme.violet.g, root.theme.violet.b, root.theme.dark ? 0.15 : 0.1) }
                        }
                    }
                }

                Repeater {
                    model: 5
                    Rectangle {
                        objectName: "cacheStageRail" + index
                        required property int index
                        readonly property real waveAmount: cacheMotif.waveAmount(index)
                        x: 98
                        y: 146 + index * 74
                        width: 802
                        height: 7 + waveAmount * 3
                        color: index === 2 ? root.theme.spectrum : index === 3 ? root.theme.violet : root.theme.accent
                        opacity: 0.34 + index * 0.035 + waveAmount * 0.48
                        Rectangle {
                            x: parent.width * (0.38 + parent.waveAmount * 0.18)
                            y: -2
                            width: 8
                            height: 8
                            radius: 4
                            scale: 1 + parent.waveAmount * 0.42
                            color: parent.color
                        }
                        Rectangle {
                            x: 0
                            y: 0
                            width: parent.width
                            height: 1
                            color: root.theme.text
                            opacity: 0.42
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

                Shape {
                    objectName: "settingsCalibrationDeck"
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: root.theme.lineStrong
                        strokeWidth: 1
                        fillColor: Qt.rgba(root.theme.violet.r,
                                           root.theme.violet.g,
                                           root.theme.violet.b,
                                           root.theme.dark ? 0.13 : 0.085)
                        startX: 304; startY: 84
                        PathLine { x: 686; y: 116 }
                        PathLine { x: 714; y: 456 }
                        PathLine { x: 284; y: 492 }
                        PathLine { x: 304; y: 84 }
                    }
                }
                Repeater {
                    model: 6
                    Rectangle {
                        required property int index
                        x: index < 3 ? 78 : 693
                        y: 140 + (index % 3) * 110
                        width: 235
                        height: 42
                        radius: 1
                        border.color: root.theme.lineStrong
                        border.width: 1
                        gradient: Gradient {
                            GradientStop { position: 0; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.17 : 0.11) }
                            GradientStop { position: 1; color: Qt.rgba(root.theme.panel.r, root.theme.panel.g, root.theme.panel.b, 0.24) }
                        }
                    }
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
                        width: 224
                        height: 224
                        radius: 112
                        border.color: root.theme.lineStrong
                        border.width: 1
                        gradient: Gradient {
                            GradientStop { position: 0; color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.22 : 0.15) }
                            GradientStop { position: 0.62; color: Qt.rgba(root.theme.panel.r, root.theme.panel.g, root.theme.panel.b, 0.22) }
                            GradientStop { position: 1; color: Qt.rgba(root.theme.violet.r, root.theme.violet.g, root.theme.violet.b, root.theme.dark ? 0.18 : 0.12) }
                        }
                    }
                    Repeater {
                        model: 24
                        Item {
                            required property int index
                            anchors.fill: parent
                            rotation: index * 15
                            Rectangle {
                                x: parent.width / 2 - width / 2
                                y: 9
                                width: 1.5
                                height: index % 3 === 0 ? 12 : 7
                                color: root.theme.textSoft
                                opacity: 0.62
                            }
                        }
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 188
                        height: 188
                        radius: 94
                        color: "transparent"
                        border.color: root.theme.accent
                        border.width: 1
                        opacity: 0.74
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 152
                        height: 152
                        radius: 76
                        color: "transparent"
                        border.color: root.theme.accent
                        border.width: 2 + settingsMotif.emphasis * 1.5
                        opacity: 0.62 + settingsMotif.emphasis * 0.34
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 2 + settingsMotif.emphasis
                        height: parent.height
                        color: root.theme.accent
                        opacity: 0.48 + settingsMotif.emphasis * 0.38
                    }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: 2 + settingsMotif.emphasis
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
            NumberAnimation { target: movingLayer; property: "opacity"; to: 1; duration: root.theme.backgroundMotion; easing.type: Easing.OutCubic }
        }
        SequentialAnimation {
            PropertyAction { target: device; property: "opacity"; value: 0.04 }
            PropertyAction { target: deviceTranslate; property: "x"; value: 18 }
            PauseAnimation { duration: root.theme.deviceEntryDelay }
            ParallelAnimation {
                NumberAnimation { target: device; property: "opacity"; to: 1; duration: root.theme.backgroundMotion - root.theme.deviceEntryDelay; easing.type: Easing.OutCubic }
                NumberAnimation { target: deviceTranslate; property: "x"; to: 0; duration: root.theme.backgroundMotion - root.theme.deviceEntryDelay; easing.type: Easing.OutCubic }
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
