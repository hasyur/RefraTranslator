import QtQuick
import QtQuick.Controls

HoverHandler {
    id: root

    required property var theme
    property string description: ""
    property string settingKey: ""
    property string settingPart: "control"
    readonly property bool hintVisible: hintPopup.visible
    readonly property real hintX: hintPopup.x
    readonly property real hintY: hintPopup.y
    readonly property real hintWidth: hintPopup.width
    readonly property real hintHeight: hintPopup.height

    objectName: settingKey.length > 0
                ? "settingHint-" + settingKey + "-" + settingPart
                : ""
    enabled: description.length > 0

    function itemRectInOverlay(item, overlay) {
        const first = item.mapToItem(overlay, 0, 0)
        const second = item.mapToItem(overlay, item.width, item.height)
        return Qt.rect(
            Math.min(first.x, second.x),
            Math.min(first.y, second.y),
            Math.abs(second.x - first.x),
            Math.abs(second.y - first.y)
        )
    }

    function intersect(first, second) {
        const left = Math.max(first.x, second.x)
        const top = Math.max(first.y, second.y)
        const right = Math.min(first.x + first.width, second.x + second.width)
        const bottom = Math.min(first.y + first.height, second.y + second.height)
        return Qt.rect(left, top, Math.max(0, right - left), Math.max(0, bottom - top))
    }

    function targetIsVisible() {
        let current = target
        while (current) {
            if (!current.visible || current.opacity <= 0)
                return false
            current = current.parent
        }
        return true
    }

    function visibleBounds(overlay) {
        let bounds = Qt.rect(0, 0, overlay.width, overlay.height)
        let current = target ? target.parent : null
        while (current && current !== overlay) {
            if (current.clip)
                bounds = intersect(bounds, itemRectInOverlay(current, overlay))
            current = current.parent
        }
        return bounds
    }

    function reposition() {
        const overlay = hintPopup.parent
        if (!target || !overlay || !targetIsVisible()) {
            hintPopup.close()
            return
        }

        const bounds = visibleBounds(overlay)
        if (bounds.width <= 0 || bounds.height <= 0) {
            hintPopup.close()
            return
        }
        const targetRect = intersect(bounds, itemRectInOverlay(target, overlay))
        if (targetRect.width <= 0 || targetRect.height <= 0) {
            hintPopup.close()
            return
        }

        const horizontalInset = Math.min(8, bounds.width / 4)
        const verticalInset = Math.min(8, bounds.height / 4)
        const gap = 8
        const left = bounds.x + horizontalInset
        const top = bounds.y + verticalInset
        const right = bounds.x + bounds.width - horizontalInset
        const bottom = bounds.y + bounds.height - verticalInset

        hintPopup.width = Math.min(280, right - left)
        const maximumX = Math.max(left, right - hintPopup.width)
        hintPopup.x = Math.max(left, Math.min(maximumX, targetRect.x))

        const desiredHeight = Math.min(hintPopup.implicitHeight, bottom - top)
        const targetBottom = targetRect.y + targetRect.height
        const spaceBelow = bottom - targetBottom - gap
        const spaceAbove = targetRect.y - top - gap
        let placeBelow = false
        if (desiredHeight <= spaceBelow) {
            placeBelow = true
        } else if (desiredHeight > spaceAbove) {
            placeBelow = spaceBelow >= spaceAbove
        }
        const sideSpace = placeBelow ? spaceBelow : spaceAbove
        if (sideSpace <= 0) {
            hintPopup.close()
            return
        }
        hintPopup.height = Math.min(desiredHeight, sideSpace)
        if (placeBelow) {
            hintPopup.y = targetBottom + gap
        } else {
            hintPopup.y = targetRect.y - gap - hintPopup.height
        }
    }

    onHoveredChanged: {
        if (hovered) {
            showTimer.restart()
        } else {
            showTimer.stop()
            hintPopup.close()
        }
    }

    property Timer showTimer: Timer {
        interval: 400
        repeat: false
        onTriggered: {
            if (!root.hovered || !root.targetIsVisible())
                return
            root.reposition()
            root.hintPopup.open()
            Qt.callLater(root.reposition)
        }
    }

    property FrameAnimation positionTracker: FrameAnimation {
        running: root.hintPopup.visible
        onTriggered: root.reposition()
    }

    property Popup hintPopup: Popup {
        parent: Overlay.overlay
        width: 280
        padding: 10
        modal: false
        focus: false
        closePolicy: Popup.NoAutoClose

        contentItem: Text {
            text: root.description
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            clip: true
            width: root.hintPopup.width
                   - root.hintPopup.leftPadding
                   - root.hintPopup.rightPadding
        }

        background: Rectangle {
            color: root.theme.inkRaised
            border.color: root.theme.accent
            border.width: 1
            radius: 3
        }
    }
}
