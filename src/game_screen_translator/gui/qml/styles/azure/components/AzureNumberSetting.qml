import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes

Item {
    id: root
    required property var theme
    required property string title
    property string description: ""
    property int value: 0
    property int minimum: 0
    property int maximum: 100
    property int stepSize: 1
    property string suffix: ""
    property bool highlighted: false
    property string settingKey: ""
    property int stagger: 0
    readonly property real stepperPreferredWidth: root.highlighted ? 250 : 184
    readonly property real stepperMinimumWidth: root.highlighted ? 248 : 180
    readonly property real layoutRowWidth: parent
                                               ? Math.max(0, Math.min(parent.width - root.stagger,
                                                   root.highlighted ? 520 : (parent.width < 500 ? 360 : 430)))
                                               : 0
    signal edited(int value)
    signal activated(string key)
    implicitHeight: 48
    Layout.fillWidth: false
    Layout.preferredWidth: root.layoutRowWidth
    Layout.minimumWidth: Math.min(root.layoutRowWidth, root.highlighted ? 360 : 330)
    Layout.leftMargin: root.stagger

    Shape {
        id: selectionOffset
        x: 5
        y: 4
        width: root.width - 2
        height: root.height
        visible: root.highlighted
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: root.theme.spectrum
            strokeWidth: 0
            startX: 0; startY: 0
            PathLine { x: selectionOffset.width - 12; y: 0 }
            PathLine { x: selectionOffset.width; y: selectionOffset.height }
            PathLine { x: 0; y: selectionOffset.height }
            PathLine { x: 0; y: 0 }
        }
    }

    Shape {
        id: selectionShape
        x: -7
        y: 0
        width: root.width + 14
        height: root.height
        visible: root.highlighted
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: root.theme.accent
            strokeWidth: 0
            startX: 0; startY: 0
            PathLine { x: root.width - 12; y: 0 }
            PathLine { x: root.width; y: root.height }
            PathLine { x: 0; y: root.height }
            PathLine { x: 0; y: 0 }
        }
    }
    Shape {
        id: highlightPointer
        x: 0
        y: 10
        width: 11
        height: 31
        visible: root.highlighted
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: "#ff3153"
            strokeWidth: 0
            startX: 0; startY: 0
            PathLine { x: highlightPointer.width; y: highlightPointer.height * 0.5 }
            PathLine { x: 0; y: highlightPointer.height }
            PathLine { x: 0; y: 0 }
        }
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 13
        anchors.rightMargin: 12
        spacing: 8
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 100
            spacing: 2
            Text {
                text: root.title
                color: root.highlighted ? "#ffffff" : root.theme.text
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: root.highlighted ? 22 : 16
                font.weight: root.highlighted ? Font.DemiBold : Font.Medium
                maximumLineCount: 1
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Text {
                text: root.description
                color: root.highlighted ? "#dce8ff" : root.theme.textDim
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: 11
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
        AzureNumberStepper {
            objectName: root.settingKey + "Control"
            theme: root.theme
            accessibleName: root.title
            value: root.value
            minimum: root.minimum
            maximum: root.maximum
            stepSize: root.stepSize
            suffix: root.suffix
            highlighted: root.highlighted
            Layout.preferredWidth: root.stepperPreferredWidth
            Layout.minimumWidth: root.stepperMinimumWidth
            Layout.preferredHeight: 40
            onEdited: next => {
                root.activated(root.settingKey)
                root.edited(next)
            }
        }
    }

    TapHandler {
        onTapped: root.activated(root.settingKey)
    }
}
