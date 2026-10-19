import QtQuick

Item {
    id: root

    required property var theme
    property real startProgress: 1
    property bool startRunning: false
    property real actionProgress: 1
    property bool actionRunning: false
    property string actionKind: ""
    property real warningProgress: 1
    property bool warningRunning: false
    property bool reducedMotion: false

    enabled: false
    z: 10
    visible: !root.reducedMotion
              && (root.startRunning || root.actionRunning || root.warningRunning)

    Rectangle {
        objectName: "prismStartProgressRule"
        x: 18
        y: root.height - 4
        width: root.startRunning ? 104 * root.startProgress : 0
        height: 2
        color: root.theme.accent
        visible: root.startRunning && !root.reducedMotion
    }

    Rectangle {
        objectName: "prismActionFeedbackRule"
        x: 18
        y: root.height - 4
        width: root.actionRunning ? 16 + 58 * (1 - root.actionProgress) : 0
        height: 2
        color: root.theme.accent
        visible: root.actionRunning && !root.reducedMotion
    }

    Rectangle {
        objectName: "prismWarningFeedbackRule"
        x: 18
        y: root.height - 4
        width: root.warningRunning ? 12 + 20 * (1 - root.warningProgress) : 0
        height: 2
        color: root.theme.amber
        visible: root.warningRunning && !root.reducedMotion
    }
}
