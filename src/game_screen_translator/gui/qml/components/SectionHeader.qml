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
        objectName: "sectionHeaderTitle"
        text: root.title
        color: root.theme.text
        font.family: root.theme.displayFontFor(text)
        font.pixelSize: 16
        font.weight: Font.DemiBold
        font.letterSpacing: 2
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: root.theme.line
    }

    Text {
        visible: root.meta.length > 0
        text: root.meta
        color: root.theme.accent
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: 10
        font.letterSpacing: 1
    }
}
