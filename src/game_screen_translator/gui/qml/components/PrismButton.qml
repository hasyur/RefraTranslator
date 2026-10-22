import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Button {
    id: root

    required property var theme
    property bool primary: false
    property string settingDescription: ""
    property string settingKey: ""
    property bool quiet: false
    property bool navigation: false
    property string navigationNumber: ""
    property string navigationCode: ""
    property string navigationSubtitle: ""
    property bool navigationCool: false
    property real navigationTilt: 0
    property bool navigationHero: false
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
    implicitHeight: root.theme.dohna && root.navigation
                    ? Math.ceil(navigationTextMetrics.tightBoundingRect.height / 0.85)
                    : root.navigation ? (root.theme.refraDark ? (root.navigationHero ? 60 : 66) : 52) : 42
    verticalPadding: root.theme.dohna && root.navigation ? 0 : padding
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    // Rotate the menu control itself so its label and hit target follow the bar.
    rotation: root.theme.dohna && root.navigation ? 12
              : root.theme.refraDark && root.navigation ? root.navigationTilt : 0
    scale: root.theme.dohna ? 1 : (root.down ? 0.994 : root.hovered && root.enabled ? 1.004 : 1)

    Behavior on scale {
        NumberAnimation { duration: root.theme.fast; easing.type: Easing.OutCubic }
    }

    onPressedChanged: {
        if (!root.theme.dohna || root.theme.reducedMotion) {
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
        function onDohnaChanged() {
            if (!root.theme.dohna) {
                dohnaPressPulse.stop()
                root.dohnaImpact = 0
            }
        }
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
        implicitWidth: root.navigation && !root.theme.dohna
                       ? (root.theme.refraDark ? (root.navigationHero ? 520 : 160) : 150)
                       : buttonLabel.implicitWidth
        implicitHeight: root.navigation && !root.theme.dohna ? (root.theme.refraDark ? (root.navigationHero ? 58 : 64) : 42) : buttonLabel.implicitHeight

        Text {
            id: buttonLabel
            objectName: "prismButtonLabel"
            anchors.fill: parent
            visible: !root.navigation || root.theme.dohna
            text: root.text
            color: !root.enabled ? root.theme.textDim
                  : root.tone === "danger" ? root.theme.danger
                  : root.theme.dohna && root.navigation
                    && (root.primary || root.hovered || root.down || root.activeFocus) ? root.theme.ink
                  : root.theme.dohna && root.quiet ? root.theme.navigationText
                  : root.primary ? (root.theme.dohna ? root.theme.ink : root.theme.buttonPrimaryText)
                  : root.theme.text
            font.family: root.theme.dohna
                         ? root.theme.monoFontFor(text)
                         : root.theme.uiFontFor(text)
            font.pixelSize: root.theme.dohna && root.navigation ? 24 : 13
            font.weight: root.theme.dohna && root.navigation ? Font.Bold : Font.DemiBold
            font.letterSpacing: root.theme.dohna
                                ? (root.navigation ? 0.4 : 0.9)
                                : 0.2
            fontSizeMode: Text.FixedSize
            leftPadding: root.theme.dohna && root.navigation ? 10 : 0
            rightPadding: leftPadding
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
        }

        Text {
            objectName: "navigationNumberLabel"
            visible: root.navigation && !root.theme.dohna
            x: 7
            y: 8
            width: 24
            height: 18
            text: root.navigationNumber
            color: root.theme.refraDark && root.primary ? root.theme.ink
                  : root.primary ? root.theme.accent : root.theme.textDim
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 12
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            id: navigationTitleLabel
            objectName: "navigationTitleLabel"
            visible: root.navigation && !root.theme.dohna
            x: 37
            y: root.theme.refraDark && !root.navigationHero ? 1 : (root.theme.refraDark ? 0 : 3)
            width: root.theme.refraDark && root.navigationHero
                   ? Math.min(parent.width - x - 10, implicitWidth)
                   : Math.max(0, parent.width - x - (root.theme.refraDark ? 10 : 5))
            height: root.theme.refraDark ? (root.navigationHero ? 52 : 36) : 24
            text: root.text
            color: root.theme.refraDark && root.primary ? root.theme.ink
                  : !root.enabled ? root.theme.textDim
                  : root.theme.refraDark && root.navigationCool ? root.theme.electric
                  : root.theme.text
            font.family: root.theme.refraDark && !root.theme.containsCjk(text)
                         ? "Arial Black" : root.theme.displayFontFor(text)
            font.pixelSize: root.theme.refraDark
                            ? (root.navigationHero
                               ? Math.max(32, Math.min(48, root.width * 0.092))
                               : Math.max(15, Math.min(24, (root.width - 56)
                                                       / Math.max(5, String(text).length * 0.58)))
                              )
                            : 15
            font.weight: root.theme.refraDark
                         ? Font.Black : root.primary ? Font.Bold : Font.DemiBold
            font.italic: root.theme.refraDark
            font.letterSpacing: root.theme.refraDark ? -1.4 : 0
            verticalAlignment: Text.AlignVCenter
            elide: root.theme.refraDark ? Text.ElideNone : Text.ElideRight
            transform: Scale {
                xScale: root.theme.refraDark ? 0.78 : 1
                origin.x: 0
                origin.y: navigationTitleLabel.height / 2
            }
        }

        Text {
            id: navigationSubtitleLabel
            objectName: "navigationSubtitleLabel"
            visible: root.navigation && !root.theme.dohna && root.theme.refraDark
            x: root.navigationHero
               ? Math.min(parent.width - implicitWidth - 5,
                          navigationTitleLabel.x + navigationTitleLabel.width + 16)
               : 37
            y: root.navigationHero ? 0 : 35
            width: Math.max(0, Math.min(root.navigationHero ? 100 : parent.width - x - 5,
                                        implicitWidth))
            height: root.navigationHero ? 52 : 25
            text: root.navigationSubtitle
            color: root.primary ? root.theme.ink
                  : root.navigationCool ? root.theme.electric : root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: root.navigationHero ? 18 : 14
            font.weight: Font.Bold
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        Text {
            objectName: "navigationCodeLabel"
            visible: root.navigation && !root.theme.dohna && !root.theme.refraDark
            x: 37
            y: 26
            width: Math.max(0, parent.width - x - 5)
            height: 13
            text: root.navigationCode
            color: root.theme.textDim
            font.family: root.theme.displayFontFor(text)
            font.pixelSize: 12
            font.letterSpacing: 0.1
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    background: Rectangle {
        id: buttonSurface
        clip: !root.theme.dohna
        transform: Translate {
            y: root.theme.dohna ? root.dohnaImpact * 2 : 0
        }
        color: !root.enabled ? "transparent"
              : root.navigation ? "transparent"
              : root.theme.dohna ? "transparent"
              : root.primary ? root.theme.buttonPrimary
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.12)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.065)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: root.theme.dohna || root.navigation ? "transparent"
                    : root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
                    : root.primary && root.theme.dohna ? root.theme.selectionEdge
                    : root.primary ? root.theme.accent
                    : root.theme.lineStrong
        border.width: root.theme.dohna || root.navigation ? 0 : (root.activeFocus ? 2 : root.primary ? 1.5 : 1)
        opacity: root.dohnaGroupFrame
                 ? (root.dohnaGroupEnabled ? 1 : 0.55)
                 : root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.ui } }
        Behavior on border.color { ColorAnimation { duration: root.theme.ui } }

        Rectangle {
            objectName: "prismButtonLightEdge"
            visible: !root.theme.dohna && !root.theme.refraDark
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.primary ? 2 : 1
            color: root.primary && root.theme.dohna ? root.theme.selectionEdge
                 : root.primary ? root.theme.accent : root.theme.lineStrong
            opacity: root.enabled ? (root.primary || root.hovered || root.activeFocus ? 0.9 : 0.24) : 0.15
            Behavior on opacity { NumberAnimation { duration: root.theme.ui } }
        }

        Rectangle {
            objectName: "prismNavigationMagentaOffset"
            visible: root.theme.refraDark && root.navigation && root.primary && root.enabled
            x: 10
            y: 7
            width: root.navigationHero
                   ? Math.max(360, Math.min(parent.width - 26,
                                            navigationTitleLabel.x + navigationTitleLabel.implicitWidth
                                            + 16 + navigationSubtitleLabel.implicitWidth + 14))
                   : Math.max(0, parent.width - 27)
            height: parent.height - 11
            color: root.theme.spectrum
            rotation: -1.4
        }
        Rectangle {
            objectName: "prismNavigationActivePlate"
            visible: root.theme.refraDark && root.navigation && root.primary && root.enabled
            x: 4
            y: 4
            width: root.navigationHero
                   ? Math.max(360, Math.min(parent.width - 26,
                                            navigationTitleLabel.x + navigationTitleLabel.implicitWidth
                                            + 16 + navigationSubtitleLabel.implicitWidth + 14))
                   : Math.max(0, parent.width - 26)
            height: parent.height - 6
            color: root.theme.accent
            rotation: -1.4
        }

        Shape {
            objectName: "prismButtonPrimaryFacet"
            visible: !root.theme.dohna && root.primary && root.enabled && !root.navigation
            anchors.right: parent.right
            anchors.top: parent.top
            width: 14
            height: 11
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.accent
                startX: 5
                startY: 0
                PathLine { x: 14; y: 0 }
                PathLine { x: 14; y: 11 }
                PathLine { x: 0; y: 11 }
                PathLine { x: 5; y: 0 }
            }
        }

        Shape {
            objectName: "prismButtonDohnaShadow"
            visible: root.theme.dohna
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
                objectName: "prismButtonDohnaShadowPath"
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
            objectName: "prismNavigationCut"
            visible: root.theme.dohna && root.navigation
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: "prismNavigationDohnaPath"
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
            objectName: "prismButtonDohnaCut"
            visible: root.theme.dohna
                     && root.enabled
                     && !root.navigation
                     && !root.dohnaEmbedded
                     && !root.dohnaGroupFrame
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: "prismButtonDohnaPath"
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
            objectName: "prismButtonDohnaGroupShadow"
            visible: root.theme.dohna && root.dohnaGroupVisible
            x: 5
            y: 5
            width: root.dohnaGroupWidth
            height: root.dohnaGroupHeight
            z: -2
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: "prismButtonDohnaGroupShadowPath"
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
            objectName: "prismButtonDohnaGroupSurface"
            visible: root.theme.dohna && root.dohnaGroupVisible
            width: root.dohnaGroupWidth
            height: root.dohnaGroupHeight
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: "prismButtonDohnaGroupPath"
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
            objectName: "prismButtonDohnaGroupDivider1"
            visible: root.theme.dohna
                     && root.dohnaGroupVisible
                     && root.dohnaGroupDivider1X >= 0
            x: root.dohnaGroupDivider1X
            y: 4
            width: 2
            height: Math.max(0, root.dohnaGroupHeight - 8)
            color: root.theme.ink
        }

        Rectangle {
            objectName: "prismButtonDohnaGroupDivider2"
            visible: root.theme.dohna
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
