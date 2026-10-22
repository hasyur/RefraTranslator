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
    signal edited(int value)
    signal activated(string key)
    implicitHeight: 52
    Layout.fillWidth: true

    Shape {
        anchors.fill: parent
        visible: root.highlighted
        antialiasing: true
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
    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.highlighted ? 8 : 0
        color: root.theme.spectrum
        visible: root.highlighted
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 13 + root.stagger
        anchors.rightMargin: 12
        spacing: 8
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 85
            spacing: 2
            Text {
                text: root.title
                color: root.highlighted ? "#ffffff" : root.theme.text
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: root.highlighted ? 14 : 13
                font.weight: root.highlighted ? Font.DemiBold : Font.Medium
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Text {
                text: root.description
                color: root.highlighted ? "#dce8ff" : root.theme.textDim
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: 10
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
            Layout.preferredWidth: 176
            Layout.minimumWidth: 146
            Layout.preferredHeight: 32
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
