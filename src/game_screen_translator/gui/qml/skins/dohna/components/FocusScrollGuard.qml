import QtQuick

QtObject {
    id: root

    required property Flickable flickable
    readonly property var focusWindow: root.flickable.Window.window
    property int margin: 10

    function revealActiveFocus() {
        const focusItem = root.focusWindow ? root.focusWindow.activeFocusItem : null
        if (!focusItem || !focusItem.visible)
            return

        let ancestor = focusItem
        while (ancestor && ancestor !== root.flickable.contentItem)
            ancestor = ancestor.parent
        if (!ancestor)
            return

        const point = focusItem.mapToItem(root.flickable.contentItem, 0, 0)
        const top = point.y - root.margin
        const bottom = point.y + focusItem.height + root.margin
        const viewportTop = root.flickable.contentY
        const viewportBottom = viewportTop + root.flickable.height
        const maximum = Math.max(0, root.flickable.contentHeight - root.flickable.height)
        if (top < viewportTop)
            root.flickable.contentY = Math.max(0, top)
        else if (bottom > viewportBottom)
            root.flickable.contentY = Math.min(maximum, bottom - root.flickable.height)
    }

    property Connections focusWatcher: Connections {
        target: root.focusWindow
        ignoreUnknownSignals: true

        function onActiveFocusItemChanged() {
            Qt.callLater(root.revealActiveFocus)
        }
    }
}
