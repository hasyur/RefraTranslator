import QtQuick
import QtQuick.Controls

ComboBox {
    id: root

    required property var theme
    property var itemEnabled: []
    property string accessibleName: ""

    Accessible.name: root.accessibleName.length > 0 ? root.accessibleName : root.displayText

    function isItemEnabled(index) {
        return !root.itemEnabled
                || root.itemEnabled.length <= index
                || Boolean(root.itemEnabled[index])
    }

    implicitHeight: 42
    leftPadding: 12
    rightPadding: 34
    font.family: root.theme.uiFontFor(root.displayText)
    font.pixelSize: 13
    hoverEnabled: true

    contentItem: Text {
        leftPadding: 0
        rightPadding: root.indicator.width + root.spacing
        text: root.displayText
        color: root.enabled ? root.theme.text : root.theme.textDim
        font: root.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Text {
        x: root.width - width - 12
        y: (root.height - height) / 2
        text: "⌄"
        color: root.theme.accent
        font.pixelSize: 16
    }

    background: Rectangle {
        color: root.theme.dark ? "#8f0b1016" : "#b8eef2f3"
        border.color: root.activeFocus ? root.theme.accent : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : 1
    }

    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: root.width
        enabled: root.isItemEnabled(index)
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: String(modelData)
            color: parent.enabled ? root.theme.text : root.theme.textDim
            font: root.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            color: highlighted
                   ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.14)
                   : root.theme.inkRaised
        }
    }

    popup: Popup {
        y: root.height + 2
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + 2, 260)
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }

        background: Rectangle {
            color: root.theme.inkRaised
            border.color: root.theme.lineStrong
        }
    }
}
