import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    required property var theme
    property string eyebrow: "DATA SOURCE"
    property string title: "暂无可用数据"
    property string detail: ""

    color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.035)
    border.color: root.theme.line
    border.width: 1
    implicitHeight: 150

    Rectangle {
        width: 3
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        color: root.theme.accent
        opacity: 0.66
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 8

        Text {
            objectName: "unavailableStateEyebrow"
            text: root.eyebrow
            color: root.theme.accent
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 11
            font.letterSpacing: 1.2
        }
        Text {
            objectName: "unavailableStateTitle"
            text: root.title
            color: root.theme.text
            font.family: root.theme.displayFontFor(text)
            font.pixelSize: 22
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            text: root.detail
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Item { Layout.fillHeight: true }
    }
}
