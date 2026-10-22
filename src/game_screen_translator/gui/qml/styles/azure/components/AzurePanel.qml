import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property color fillColor: "#ffffff"
    property color strokeColor: "transparent"
    property real strokeWidth: 0
    property real cutTopLeft: 0
    property real cutTopRight: 0
    property real cutBottomRight: 0
    property real cutBottomLeft: 0
    property real inset: 16
    default property alias contentData: content.data

    Shape {
        anchors.fill: parent
        antialiasing: true
        ShapePath {
            fillColor: root.fillColor
            strokeColor: root.strokeColor
            strokeWidth: root.strokeWidth
            startX: root.cutTopLeft
            startY: 0
            PathLine { x: root.width - root.cutTopRight; y: 0 }
            PathLine { x: root.width; y: root.cutTopRight }
            PathLine { x: root.width; y: root.height - root.cutBottomRight }
            PathLine { x: root.width - root.cutBottomRight; y: root.height }
            PathLine { x: root.cutBottomLeft; y: root.height }
            PathLine { x: 0; y: root.height - root.cutBottomLeft }
            PathLine { x: 0; y: root.cutTopLeft }
            PathLine { x: root.cutTopLeft; y: 0 }
        }
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.margins: root.inset
    }
}
