import QtQuick
import QtQuick.Controls

Item {
    id: root

    required property var theme
    property Item target: null
    property string description: ""
    property string settingKey: ""
    property string settingPart: "control"
    readonly property bool hintVisible: popup.visible

    objectName: settingKey.length > 0
                ? "settingHint-" + settingKey + "-" + settingPart
                : ""
    visible: target !== null && description.length > 0 && target.visible
    enabled: true
    z: 10000

    x: target && parent ? target.mapToItem(parent, 0, 0).x : 0
    y: target && parent ? target.mapToItem(parent, 0, 0).y : 0
    width: target ? target.width : 0
    height: target ? target.height : 0

    HoverHandler {
        id: hoverHandler

        onHoveredChanged: {
            if (hovered) {
                showTimer.restart()
            } else {
                showTimer.stop()
                popup.close()
            }
        }
    }

    Timer {
        id: showTimer
        interval: 400
        repeat: false
        onTriggered: {
            if (hoverHandler.hovered)
                popup.open()
        }
    }

    Popup {
        id: popup

        parent: Overlay.overlay
        width: 280
        padding: 10
        modal: false
        focus: false
        closePolicy: Popup.NoAutoClose
        x: {
            if (!root.target || !parent)
                return 12
            const point = root.target.mapToItem(parent, 0, root.target.height + 8)
            return Math.max(12, Math.min(parent.width - width - 12, point.x))
        }
        y: {
            if (!root.target || !parent)
                return 12
            const point = root.target.mapToItem(parent, 0, root.target.height + 8)
            return Math.max(12, Math.min(parent.height - height - 12, point.y))
        }

        contentItem: Text {
            text: root.description
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            width: popup.width - popup.leftPadding - popup.rightPadding
        }

        background: Rectangle {
            color: root.theme.inkRaised
            border.color: root.theme.accent
            border.width: 1
            radius: 3
        }
    }
}
