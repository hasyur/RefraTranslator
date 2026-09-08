import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root

    required property var theme
    property string title: ""
    property string meta: ""
    spacing: 2
    Layout.fillWidth: true

    Text {
        text: root.title
        color: root.theme.text
        font.family: root.theme.uiFontFor(text)
        font.pixelSize: 13
        font.weight: Font.Medium
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: root.meta.length > 0
        text: root.meta
        color: root.theme.textDim
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: 9
        font.letterSpacing: 0.7
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
    }
}
