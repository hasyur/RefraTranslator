import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root

    required property var theme
    property string title: ""
    property string meta: ""
    property string description: ""
    property string settingKey: ""
    spacing: 2
    Layout.fillWidth: true

    Text {
        id: titleText
        text: root.title
        color: root.theme.text
        font.family: root.theme.uiFontFor(text)
        font.pixelSize: 13
        font.weight: Font.Medium
        wrapMode: Text.WordWrap
        Layout.fillWidth: true

        SettingHint {
            theme: root.theme
            target: titleText
            description: root.description
            settingKey: root.settingKey
            settingPart: "label"
        }
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
