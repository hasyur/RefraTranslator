import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property var theme
    property real facetWidth: 42

    implicitHeight: 7
    clip: true

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: 1
        color: root.theme.line
    }

    Shape {
        id: facet
        objectName: "prismFoldRuleFacet"
        visible: !root.theme.dohna
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(root.facetWidth, parent.width)
        height: 7
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.theme.accent
            strokeWidth: 1
            fillColor: "transparent"
            startX: 0
            startY: 6
            PathLine { x: facet.width * 0.24; y: 1 }
            PathLine { x: facet.width * 0.52; y: 1 }
        }
        ShapePath {
            strokeColor: root.theme.refractionSpectrum
            strokeWidth: 1
            fillColor: "transparent"
            startX: facet.width * 0.29
            startY: 6
            PathLine { x: facet.width * 0.53; y: 1 }
            PathLine { x: facet.width * 0.81; y: 1 }
        }
    }
}
