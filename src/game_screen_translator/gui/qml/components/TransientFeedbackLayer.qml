import QtQuick

Item {
    id: root

    required property var theme
    property real startProgress: 1
    property bool startRunning: false
    property bool reducedMotion: false
    readonly property real lineWidth: theme.feedbackLineWidth

    enabled: false
    z: 10
    visible: !reducedMotion && startRunning

    Item {
        id: startFeedback
        objectName: "startPreludeFeedback"
        anchors.fill: parent
        visible: root.startRunning && !root.reducedMotion
        Rectangle {
            objectName: "startFeedbackBeam"
            x: root.width * 0.06
            y: root.height * 0.49
            width: root.width * 0.88 * root.startProgress
            height: root.lineWidth + 1
            color: root.theme.accent
            opacity: 0.25 + Math.sin(Math.PI * root.startProgress) * 0.75
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                y: 6
                height: 2
                color: root.theme.spectrum
                opacity: 0.78
            }
        }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(root.width, root.height) * (0.12 + root.startProgress * 0.45)
            height: width
            radius: width / 2
            color: "transparent"
            border.color: root.theme.spectrum
            border.width: root.lineWidth
            opacity: 1 - root.startProgress
        }
    }
}
