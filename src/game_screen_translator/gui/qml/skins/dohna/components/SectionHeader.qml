import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root

    required property var theme
    property string title: ""
    property string meta: ""

    spacing: 12
    implicitHeight: 30

    Text {
        objectName: root.theme.active ? ("sectionHeaderTitle") : ""
        text: root.title
        color: root.theme.text
        font.family: root.theme.displayFontFor(text)
        font.pixelSize: 18
        font.weight: Font.DemiBold
        font.letterSpacing: 2
    }

    Rectangle {
        visible: true
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: root.theme.line
    }



    Text {
        visible: root.meta.length > 0
        text: root.meta
        color: root.theme.accentText
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: 12
        font.letterSpacing: 1
    }
}
