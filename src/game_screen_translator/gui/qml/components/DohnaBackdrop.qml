pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var theme
    clip: true

    Rectangle {
        anchors.fill: parent
        color: root.theme.paper
    }

    // A small, static halftone field keeps the printed look legible behind the
    // real workbench surfaces without introducing another image dependency.
    Repeater {
        model: 72
        delegate: Rectangle {
            required property int index
            width: 4
            height: 4
            radius: 2
            x: 22 + (index % 12) * 44
            y: 20 + Math.floor(index / 12) * 42
            color: index % 3 === 0 ? root.theme.accent : root.theme.ink
            opacity: index % 3 === 0 ? 0.18 : 0.10
        }
    }

    Rectangle {
        objectName: "dohnaPinkSlash"
        x: root.width * 0.48
        y: -root.height * 0.14
        width: Math.max(220, root.width * 0.45)
        height: 54
        rotation: -7
        color: root.theme.accent
        opacity: 0.88
    }

    Rectangle {
        objectName: "dohnaCyanSlash"
        x: root.width * 0.68
        y: root.height * 0.78
        width: Math.max(180, root.width * 0.34)
        height: 22
        rotation: -7
        color: root.theme.spectrum
        opacity: 0.86
    }

    Shape {
        objectName: "dohnaPrintFacet"
        anchors.fill: parent
        opacity: 0.78
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.theme.violet
            startX: root.width * 0.05
            startY: root.height * 0.12
            PathLine { x: root.width * 0.22; y: root.height * 0.05 }
            PathLine { x: root.width * 0.13; y: root.height * 0.42 }
            PathLine { x: root.width * 0.01; y: root.height * 0.34 }
            PathLine { x: root.width * 0.05; y: root.height * 0.12 }
        }
    }

    Rectangle {
        objectName: "dohnaPrintRule"
        x: 24
        y: root.height * 0.22
        width: Math.min(260, root.width * 0.26)
        height: 6
        color: root.theme.ink
        opacity: 0.9
    }
}
