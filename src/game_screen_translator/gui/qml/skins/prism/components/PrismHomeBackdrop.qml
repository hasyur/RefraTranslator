import QtQuick
import QtQuick.Shapes

// Static, decorative layers for the Prism HOME stage. The profile and
// logo art sit above this layer; it has no input handlers or business state.
Item {
    id: root

    required property bool dark
    required property real prismTipX
    required property real prismTipY
    objectName: "prismHomeBackdrop"
    enabled: false
    clip: true

    readonly property real edgeTop: width < 1100 ? 0.66 : 0.73
    readonly property real edgeBottom: width < 1100 ? 0.50 : 0.53
    readonly property real edgeSpan: edgeTop - edgeBottom
    readonly property real stageHeight: height
    readonly property real scatterOriginX: prismTipX
    readonly property real scatterOriginY: prismTipY
    readonly property real scatterEndX: width + 1
    readonly property real scatterEndY: stageHeight * 0.915
    readonly property real scatterCenterX: (scatterOriginX + scatterEndX) * 0.5
    readonly property real scatterCenterY: (scatterOriginY + scatterEndY) * 0.5
    readonly property real scatterDeltaX: scatterEndX - scatterOriginX
    readonly property real scatterDeltaY: scatterEndY - scatterOriginY
    readonly property real scatterLength: Math.max(1, Math.sqrt(scatterDeltaX * scatterDeltaX
                                                                + scatterDeltaY * scatterDeltaY))
    readonly property real scatterNormalX: -scatterDeltaY / scatterLength
    readonly property real scatterNormalY: scatterDeltaX / scatterLength
    readonly property real scatterHalfSpan: stageHeight * 0.38

    Rectangle {
        anchors.fill: parent
        color: root.dark ? "#071a42" : "#f6f9ff"
    }

    // The main field cuts down from the top-right and carries a blue spectrum
    // that changes across both axes instead of reading as a flat panel.
    Shape {
        objectName: "prismHomeBlueField"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.width * 0.50
                y1: root.stageHeight
                x2: root.width * 0.91
                y2: 0
                GradientStop { position: 0.0; color: root.dark ? "#10366f" : "#33a2ff" }
                GradientStop { position: 0.42; color: root.dark ? "#0b2a60" : "#187dff" }
                GradientStop { position: 0.76; color: root.dark ? "#12479a" : "#075fff" }
                GradientStop { position: 1.0; color: root.dark ? "#0a2a67" : "#0754ec" }
            }
            startX: root.width * root.edgeTop
            startY: 0
            PathLine { x: root.width + 2; y: 0 }
            PathLine { x: root.width + 2; y: root.stageHeight + 2 }
            PathLine { x: root.width * root.edgeBottom; y: root.stageHeight + 2 }
            PathLine { x: root.width * root.edgeTop; y: 0 }
        }
    }

    // The gradient crosses the slanted edge at a right angle. Its cyan center
    // fades on both sides before reaching the clipping edge of this shape.
    Shape {
        objectName: "prismHomeEdgeGlow"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.width * (root.edgeTop + root.edgeBottom) * 0.5 - root.stageHeight * 0.5
                y1: root.stageHeight * 0.5 - root.width * root.edgeSpan * 0.5
                x2: root.width * (root.edgeTop + root.edgeBottom) * 0.5 + root.stageHeight * 0.5
                y2: root.stageHeight * 0.5 + root.width * root.edgeSpan * 0.5
                GradientStop { position: 0.0; color: "#00bcefff" }
                GradientStop { position: 0.34; color: "#00bcefff" }
                GradientStop { position: 0.5; color: root.dark ? "#3b72cfff" : "#5acaf0ff" }
                GradientStop { position: 0.66; color: "#00bcefff" }
                GradientStop { position: 1.0; color: "#00bcefff" }
            }
            startX: root.width * (root.edgeTop - 0.18)
            startY: 0
            PathLine { x: root.width * (root.edgeTop + 0.18); y: 0 }
            PathLine { x: root.width * (root.edgeBottom + 0.18); y: root.stageHeight }
            PathLine { x: root.width * (root.edgeBottom - 0.18); y: root.stageHeight }
            PathLine { x: root.width * (root.edgeTop - 0.18); y: 0 }
        }
    }

    // Long, transparent facets give the blue field depth without adding
    // borders or card-like blocks behind the real HOME controls.
    Shape {
        objectName: "prismHomeBlueFacets"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.width * 0.7; y1: 0
                x2: root.width * 0.7; y2: root.stageHeight
                GradientStop { position: 0.0; color: "#00168bff" }
                GradientStop { position: 0.22; color: root.dark ? "#0c168bff" : "#0f61adff" }
                GradientStop { position: 0.68; color: root.dark ? "#17168bff" : "#1877c8ff" }
                GradientStop { position: 0.92; color: root.dark ? "#09168bff" : "#0c77c8ff" }
                GradientStop { position: 1.0; color: "#00168bff" }
            }
            startX: root.width * 0.79; startY: 0
            PathLine { x: root.width * 0.87; y: 0 }
            PathLine { x: root.width * 0.62; y: root.stageHeight }
            PathLine { x: root.width * 0.54; y: root.stageHeight }
            PathLine { x: root.width * 0.79; y: 0 }
        }
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.width * 0.89; y1: 0
                x2: root.width * 0.89; y2: root.stageHeight * 0.83
                GradientStop { position: 0.0; color: "#00001b49" }
                GradientStop { position: 0.24; color: root.dark ? "#11001b49" : "#0b004cff" }
                GradientStop { position: 0.64; color: root.dark ? "#16001b49" : "#10004cff" }
                GradientStop { position: 1.0; color: "#00001b49" }
            }
            startX: root.width * 0.89; startY: 0
            PathLine { x: root.width + 1; y: 0 }
            PathLine { x: root.width + 1; y: root.stageHeight * 0.83 }
            PathLine { x: root.width * 0.76; y: root.stageHeight * 0.69 }
            PathLine { x: root.width * 0.89; y: 0 }
        }
    }

    // The lower diagonal answers the broad facet in the reference image and
    // begins below the last menu row, keeping its lettering unobstructed.
    Shape {
        objectName: "prismHomeLowerFacet"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.width * 0.33
                y1: root.stageHeight
                x2: root.width
                y2: root.stageHeight * 0.78
                GradientStop { position: 0.0; color: root.dark ? "#123166" : "#86caff" }
                GradientStop { position: 0.58; color: root.dark ? "#0d397e" : "#55adff" }
                GradientStop { position: 1.0; color: root.dark ? "#0a2a67" : "#0b62f6" }
            }
            startX: root.width * 0.34; startY: root.stageHeight + 1
            PathLine { x: root.width * 0.84; y: root.stageHeight * 0.78 }
            PathLine { x: root.width + 1; y: root.stageHeight * 0.94 }
            PathLine { x: root.width + 1; y: root.stageHeight + 1 }
            PathLine { x: root.width * 0.34; y: root.stageHeight + 1 }
        }
    }

    // A quiet blue wash fades along the broad lower fan. A second gradient
    // crosses the fan so its center catches the light while both edges fade.
    Shape {
        objectName: "prismHomeScatteredLight"
        anchors.fill: parent
        readonly property real rayOriginX: root.scatterOriginX
        readonly property real rayOriginY: root.scatterOriginY
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.scatterOriginX; y1: root.scatterOriginY
                x2: root.width * 1.04; y2: root.stageHeight * 0.96
                GradientStop { position: 0.0; color: root.dark ? "#0e00a9ff" : "#1600bfff" }
                GradientStop { position: 0.24; color: root.dark ? "#16008dff" : "#1b178fff" }
                GradientStop { position: 0.72; color: root.dark ? "#0c0065d9" : "#10005fd9" }
                GradientStop { position: 1.0; color: "#00005fd9" }
            }
            startX: root.scatterOriginX; startY: root.scatterOriginY
            PathLine { x: root.width + 1; y: root.stageHeight * 0.82 }
            PathLine { x: root.width + 1; y: root.stageHeight * 1.01 }
            PathLine { x: root.scatterOriginX; y: root.scatterOriginY }
        }
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                x1: root.scatterCenterX - root.scatterNormalX * root.scatterHalfSpan
                y1: root.scatterCenterY - root.scatterNormalY * root.scatterHalfSpan
                x2: root.scatterCenterX + root.scatterNormalX * root.scatterHalfSpan
                y2: root.scatterCenterY + root.scatterNormalY * root.scatterHalfSpan
                GradientStop { position: 0.0; color: "#0000bfff" }
                GradientStop { position: 0.42; color: "#0000bfff" }
                GradientStop { position: 0.5; color: root.dark ? "#347fcfff" : "#4d7feaff" }
                GradientStop { position: 0.58; color: "#0000bfff" }
                GradientStop { position: 1.0; color: "#0000bfff" }
            }
            startX: root.scatterOriginX; startY: root.scatterOriginY
            PathLine { x: root.width + 1; y: root.stageHeight * 0.82 }
            PathLine { x: root.width + 1; y: root.stageHeight * 1.01 }
            PathLine { x: root.scatterOriginX; y: root.scatterOriginY }
        }
    }
}
