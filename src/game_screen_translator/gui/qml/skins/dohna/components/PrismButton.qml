import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import QtQuick.Window

Button {
    id: root

    required property var theme
    property bool primary: false
    property string settingDescription: ""
    property string settingKey: ""
    property bool quiet: false
    property bool navigation: false
    property string tone: "neutral"
    property real dohnaImpact: 0
    // NumberStepper embeds its two actions in one shared Dohna surface.  The
    // defaults keep every existing Prism and standalone Dohna button intact.
    property bool dohnaEmbedded: false
    property bool dohnaGroupFrame: false
    property bool dohnaGroupVisible: dohnaGroupFrame
    property bool dohnaGroupEnabled: true
    property real dohnaGroupWidth: width
    property real dohnaGroupHeight: height
    property bool dohnaGroupHovered: hovered
    property bool dohnaGroupPressed: down
    property real dohnaGroupDivider1X: -1
    property real dohnaGroupDivider2X: -1

    implicitWidth: Math.max(112, contentItem.implicitWidth + 30)
    implicitHeight: root.navigation
                    ? Math.ceil(navigationTextMetrics.tightBoundingRect.height / 0.85)
                    : 42
    verticalPadding: root.navigation ? 0 : padding
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    rotation: root.navigation ? 12
              : 0
    onPressedChanged: {
        if (root.theme.reducedMotion) {
            dohnaPressPulse.stop()
            dohnaImpact = 0
        } else if (root.pressed) {
            dohnaPressPulse.restart()
        } else {
            dohnaPressPulse.stop()
            dohnaImpact = 0
        }
    }

    Connections {
        target: root.theme
        function onReducedMotionChanged() {
            if (root.theme.reducedMotion) {
                dohnaPressPulse.stop()
                root.dohnaImpact = 0
            }
        }
    }

    TextMetrics {
        id: navigationTextMetrics
        font: buttonLabel.font
        text: buttonLabel.text
    }

    contentItem: Item {
        implicitWidth: buttonLabel.implicitWidth
        implicitHeight: buttonLabel.implicitHeight

        Text {
            id: buttonLabel
            objectName: root.theme.active ? ("prismButtonLabel") : ""
            anchors.fill: parent
            visible: true
            text: root.text
            color: !root.enabled ? root.theme.textDim
                  : root.tone === "danger" ? root.theme.danger
                  : root.navigation
                    && (root.primary || root.hovered || root.down || root.activeFocus) ? root.theme.ink
                  : root.quiet ? root.theme.navigationText
                  : root.primary ? ( root.theme.ink )
                  : root.theme.text
            font.family: root.theme.monoFontFor(text)
                         
            font.pixelSize: root.navigation ? 24 : 13
            font.weight: root.navigation ? Font.Bold : Font.DemiBold
            font.letterSpacing: (root.navigation ? 0.4 : 0.9)
                                
            fontSizeMode: Text.FixedSize
            leftPadding: root.navigation ? 10
                         : 0
            rightPadding: leftPadding
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
        }










    }

    background: Rectangle {
        id: buttonSurface
        clip: false
        transform: Translate {
            y: root.dohnaImpact * 2 }
        color: "transparent"
        border.color: "transparent"
                    
        border.width: 0
                      
        opacity: root.dohnaGroupFrame
                 ? (root.dohnaGroupEnabled ? 1 : 0.55)
                 : root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.ui } }
        Behavior on border.color { ColorAnimation { duration: root.theme.ui } }


















        Shape {
            objectName: root.theme.active ? ("prismButtonDohnaShadow") : ""
            visible: true
                     && root.enabled
                     && !root.navigation
                     && !root.dohnaEmbedded
                     && !root.dohnaGroupFrame
            x: 5
            y: 5
            width: parent.width
            height: parent.height
            z: -1
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: root.theme.active ? ("prismButtonDohnaShadowPath") : ""
                strokeColor: "transparent"
                fillColor: root.theme.stageShadow
                startX: 0
                startY: 0
                PathLine { x: root.width - 14; y: 0 }
                PathLine { x: root.width; y: root.height }
                PathLine { x: 14; y: root.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: root.theme.active ? ("prismNavigationCut") : ""
            visible: true && root.navigation
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: root.theme.active ? ("prismNavigationDohnaPath") : ""
                strokeColor: "transparent"
                strokeWidth: 0
                fillColor: root.primary || root.hovered || root.activeFocus
                           ? root.theme.violet : Qt.darker(root.theme.ink, 1.8)
                startX: 0
                startY: 0
                PathLine { x: root.width; y: 0 }
                PathLine { x: root.width; y: root.height }
                PathLine { x: 0; y: root.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: root.theme.active ? ("prismButtonDohnaCut") : ""
            visible: true
                     && root.enabled
                     && !root.navigation
                     && !root.dohnaEmbedded
                     && !root.dohnaGroupFrame
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: root.theme.active ? ("prismButtonDohnaPath") : ""
                strokeColor: root.activeFocus || root.down ? root.theme.selectionEdge : root.theme.ink
                strokeWidth: root.activeFocus || root.down ? 3 : 2
                fillColor: root.primary ? root.theme.accent
                           : root.down ? root.theme.accent
                           : root.hovered ? root.theme.violet
                           : root.theme.white
                startX: 0
                startY: 0
                PathLine { x: root.width - 14; y: 0 }
                PathLine { x: root.width; y: root.height }
                PathLine { x: 14; y: root.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: root.theme.active ? ("prismButtonDohnaGroupShadow") : ""
            visible: true && root.dohnaGroupVisible
            x: 5
            y: 5
            width: root.dohnaGroupWidth
            height: root.dohnaGroupHeight
            z: -2
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: root.theme.active ? ("prismButtonDohnaGroupShadowPath") : ""
                strokeColor: "transparent"
                fillColor: root.theme.stageShadow
                startX: 0
                startY: 0
                PathLine { x: root.dohnaGroupWidth - 14; y: 0 }
                PathLine { x: root.dohnaGroupWidth; y: root.dohnaGroupHeight }
                PathLine { x: 14; y: root.dohnaGroupHeight }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: root.theme.active ? ("prismButtonDohnaGroupSurface") : ""
            visible: true && root.dohnaGroupVisible
            width: root.dohnaGroupWidth
            height: root.dohnaGroupHeight
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: root.theme.active ? ("prismButtonDohnaGroupPath") : ""
                strokeColor: root.dohnaGroupPressed || root.activeFocus
                             ? root.theme.selectionEdge : root.theme.ink
                strokeWidth: root.dohnaGroupPressed || root.activeFocus ? 3 : 2
                fillColor: root.dohnaGroupPressed
                           ? root.theme.accent
                           : root.dohnaGroupHovered
                             ? root.theme.violet
                             : root.theme.white
                startX: 0
                startY: 0
                PathLine { x: root.dohnaGroupWidth - 14; y: 0 }
                PathLine { x: root.dohnaGroupWidth; y: root.dohnaGroupHeight }
                PathLine { x: 14; y: root.dohnaGroupHeight }
                PathLine { x: 0; y: 0 }
            }
            opacity: root.dohnaGroupEnabled ? 1 : 0.55
        }

        Rectangle {
            objectName: root.theme.active ? ("prismButtonDohnaGroupDivider1") : ""
            visible: true
                     && root.dohnaGroupVisible
                     && root.dohnaGroupDivider1X >= 0
            x: root.dohnaGroupDivider1X
            y: 4
            width: 2
            height: Math.max(0, root.dohnaGroupHeight - 8)
            color: root.theme.ink
        }

        Rectangle {
            objectName: root.theme.active ? ("prismButtonDohnaGroupDivider2") : ""
            visible: true
                     && root.dohnaGroupVisible
                     && root.dohnaGroupDivider2X >= 0
            x: root.dohnaGroupDivider2X
            y: 4
            width: 2
            height: Math.max(0, root.dohnaGroupHeight - 8)
            color: root.theme.ink
        }

    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }

    SequentialAnimation {
        id: dohnaPressPulse
        PropertyAction { target: root; property: "dohnaImpact"; value: 1 }
        NumberAnimation {
            target: root
            property: "dohnaImpact"
            to: 0
            duration: root.theme.popPressMotion
            easing.type: Easing.OutBack
        }
    }
}
