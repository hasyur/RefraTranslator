import QtQuick

// A Prism-only motion host. The same child button stays interactive while its
// geometry moves between the HomePage stage slot and the navigation rail.
Item {
    id: root
    objectName: motionObjectName

    required property var theme
    property string motionObjectName: "prismNavigationMotion"
    property string buttonObjectName: ""
    property string text: ""
    property string subtitle: ""
    property string number: ""
    property string code: ""
    property bool cool: false
    property bool slashVisible: false
    property bool selected: false
    property bool positionMotionEnabled: false
    property real targetX: 0
    property real targetY: 0
    property real targetWidth: 0
    property real targetHeight: 0
    property real targetPresentation: 0
    property real presentation: 0
    property real targetTilt: 0
    property real tilt: 0
    property real heroFontSize: 0
    property bool initialized: false
    readonly property bool positionAnimationRunning: xMotion.running || yMotion.running
                                                      || widthMotion.running || heightMotion.running
                                                      || tiltMotion.running
    readonly property bool presentationAnimationRunning: presentationMotion.running

    function stopAnimations() {
        xMotion.stop()
        yMotion.stop()
        widthMotion.stop()
        heightMotion.stop()
        presentationMotion.stop()
        tiltMotion.stop()
    }

    function settle() {
        stopAnimations()
        x = targetX
        y = targetY
        width = targetWidth
        height = targetHeight
        presentation = targetPresentation
        tilt = targetTilt
        initialized = true
    }

    function animateTo(animation, propertyName, targetValue) {
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

    function retarget() {
        if (!initialized || !positionMotionEnabled) {
            settle()
            return
        }
        retargetX()
        retargetY()
        retargetWidth()
        retargetHeight()
        retargetPresentation()
        retargetTilt()
    }

    function retargetX() { retargetProperty(xMotion, "x", targetX) }
    function retargetY() { retargetProperty(yMotion, "y", targetY) }
    function retargetWidth() { retargetProperty(widthMotion, "width", targetWidth) }
    function retargetHeight() { retargetProperty(heightMotion, "height", targetHeight) }
    function retargetPresentation() { retargetProperty(presentationMotion, "presentation", targetPresentation) }
    function retargetTilt() { retargetProperty(tiltMotion, "tilt", targetTilt) }

    function retargetProperty(animation, propertyName, targetValue) {
        if (!initialized || !positionMotionEnabled) {
            root[propertyName] = targetValue
            return
        }
        animateTo(animation, propertyName, targetValue)
    }

    NumberAnimation { id: xMotion; objectName: "p3NavigationXMotion"; target: root; property: "x"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: yMotion; objectName: "p3NavigationYMotion"; target: root; property: "y"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: widthMotion; objectName: "p3NavigationWidthMotion"; target: root; property: "width"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: heightMotion; objectName: "p3NavigationHeightMotion"; target: root; property: "height"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: presentationMotion; objectName: "p3NavigationPresentationMotion"; target: root; property: "presentation"; duration: 220; easing.type: Easing.OutCubic }
    NumberAnimation { id: tiltMotion; objectName: "p3NavigationTiltMotion"; target: root; property: "tilt"; duration: 220; easing.type: Easing.OutCubic }

    Component.onCompleted: settle()
    onPositionMotionEnabledChanged: if (!positionMotionEnabled) settle()
    onTargetXChanged: retargetX()
    onTargetYChanged: retargetY()
    onTargetWidthChanged: retargetWidth()
    onTargetHeightChanged: retargetHeight()
    onTargetPresentationChanged: retargetPresentation()
    onTargetTiltChanged: retargetTilt()

    PrismButton {
        objectName: root.buttonObjectName
        anchors.fill: parent
        theme: root.theme
        navigation: true
        navigationHero: false
        navigationPresentationProgress: root.presentation
        navigationTilt: root.tilt
        navigationHeroFontSize: root.heroFontSize
        navigationSlashVisible: root.slashVisible
        navigationNumber: root.number
        navigationCode: root.code
        navigationSubtitle: root.subtitle
        navigationCool: root.cool
        text: root.text
        primary: root.selected
        quiet: !root.selected
        onClicked: root.clicked()
    }

    signal clicked()
}
