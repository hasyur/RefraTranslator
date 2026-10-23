import QtQuick

Item {
    id: root

    width: 0
    height: 0
    visible: false

    required property var appShell
    required property var flickable
    required property string pageKey
    required property string scrollKey
    property bool active: false
    property bool restoring: false
    property int restoreGeneration: 0

    function scheduleRestorePosition() {
        if (!active || !flickable || !flickable.visible)
            return
        restoring = true
        ++restoreGeneration
        restoreTimer.restart()
    }

    function restorePosition(generation) {
        if (generation !== restoreGeneration)
            return
        if (!active || !flickable || !flickable.visible) {
            restoring = false
            return
        }
        const maximum = Math.max(0, flickable.contentHeight - flickable.height)
        const saved = appShell.scrollPosition(pageKey, scrollKey)
        flickable.contentY = Math.max(0, Math.min(maximum, saved))
        Qt.callLater(function() {
            if (generation === root.restoreGeneration && !restoreTimer.running)
                root.restoring = false
        })
    }

    Timer {
        id: restoreTimer
        interval: 32
        repeat: false
        onTriggered: root.restorePosition(root.restoreGeneration)
    }

    Component.onCompleted: {
        Qt.callLater(scheduleRestorePosition)
    }
    onActiveChanged: {
        if (active)
            scheduleRestorePosition()
        else {
            restoreTimer.stop()
            ++restoreGeneration
            restoring = false
        }
    }

    Connections {
        target: root.flickable
        ignoreUnknownSignals: true

        function onContentHeightChanged() {
            if (root.active) {
                root.scheduleRestorePosition()
            }
        }

        function onHeightChanged() {
            if (root.active) {
                root.scheduleRestorePosition()
            }
        }

        function onVisibleChanged() {
            if (root.active && root.flickable && root.flickable.visible) {
                root.scheduleRestorePosition()
            }
        }
    }
}
