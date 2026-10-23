import QtQuick

// Prism-only shared CTA host. One real button moves between the Home stage
// and the inner-page footer while its Layout slots reserve the endpoint space.
Item {
    id: root
    objectName: root.theme.active ? (actionObjectName) : ""

    required property var theme
    property string actionObjectName: "prismActionMotion"
    property string buttonObjectName: ""
    property string text: ""
    property bool primary: false
    property bool positionMotionEnabled: false
    property real targetX: 0
    property real targetY: 0
    property real targetWidth: 0
    property real targetHeight: 0
    property bool initialized: false

    function stopAnimations() {
        xMotion.stop()
        yMotion.stop()
        widthMotion.stop()
        heightMotion.stop()
    }

    function settle() {
        stopAnimations()
        x = targetX
        y = targetY
        width = targetWidth
        height = targetHeight
        initialized = true
    }

    function retargetProperty(animation, propertyName, targetValue) {
        if (!initialized || !positionMotionEnabled) {
            root[propertyName] = targetValue
            return
        }
        const currentValue = root[propertyName]
        animation.stop()
        if (Math.abs(currentValue - targetValue) < 0.05) {
            root[propertyName] = targetValue
            return
        }
        animation.from = currentValue
        animation.to = targetValue
        animation.restart()
    }

    function retargetX() { retargetProperty(xMotion, "x", targetX) }
    function retargetY() { retargetProperty(yMotion, "y", targetY) }
    function retargetWidth() { retargetProperty(widthMotion, "width", targetWidth) }
    function retargetHeight() { retargetProperty(heightMotion, "height", targetHeight) }

    NumberAnimation { id: xMotion; target: root; property: "x"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: yMotion; target: root; property: "y"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: widthMotion; target: root; property: "width"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: heightMotion; target: root; property: "height"; duration: 220; easing.type: Easing.OutCubic }

    Component.onCompleted: settle()
    onPositionMotionEnabledChanged: if (!positionMotionEnabled) settle()
    onTargetXChanged: retargetX()
    onTargetYChanged: retargetY()
    onTargetWidthChanged: retargetWidth()
    onTargetHeightChanged: retargetHeight()

    PrismButton {
        objectName: root.theme.active ? (root.buttonObjectName) : ""
        anchors.fill: parent
        theme: root.theme
        p3Action: true
        primary: root.primary
        text: root.text
        enabled: root.enabled
        onClicked: root.clicked()
    }

    signal clicked()
}
