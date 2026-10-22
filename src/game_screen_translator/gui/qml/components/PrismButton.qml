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
    property string navigationNumber: ""
    property string navigationCode: ""
    property string navigationSubtitle: ""
    property bool navigationCool: false
    property real navigationTilt: 0
    property bool navigationHero: false
    property real navigationHeroFontSize: 0
    property bool navigationSlashVisible: false
    property bool p3Action: false
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
                    : root.navigation ? (root.theme.refraStyle ? (root.navigationHero ? 60 : 66) : 52) : 42
    verticalPadding: root.theme.dohna && root.navigation ? 0 : padding
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    // Rotate the menu control itself so its label and hit target follow the bar.
    rotation: root.theme.dohna && root.navigation ? 12
              : root.theme.refraStyle && root.navigation ? root.navigationTilt : 0
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
                       ? (root.theme.refraStyle ? (root.navigationHero ? 520 : 160) : 150)
                       : buttonLabel.implicitWidth
        implicitHeight: root.navigation && !root.theme.dohna ? (root.theme.refraStyle ? (root.navigationHero ? 58 : 64) : 42) : buttonLabel.implicitHeight

        TextMetrics {
            id: navigationHeroTitleMetrics
            font: navigationTitleLabel.font
            text: navigationTitleLabel.text
        }

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
            font.pixelSize: root.theme.refraStyle && root.p3Action
                            ? (root.primary ? 20 : 17)
                            : root.theme.dohna && root.navigation ? 24 : 13
            font.weight: root.theme.refraStyle && root.p3Action ? Font.Bold
                         : root.theme.dohna && root.navigation ? Font.Bold : Font.DemiBold
            font.letterSpacing: root.theme.dohna
                                ? (root.navigation ? 0.4 : 0.9)
                                : 0.2
            fontSizeMode: Text.FixedSize
            leftPadding: root.theme.dohna && root.navigation ? 10
                         : root.theme.refraStyle && root.p3Action && root.primary ? 35 : 0
            rightPadding: leftPadding
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
        }

        Text {
            objectName: "navigationNumberLabel"
            visible: root.navigation && !root.theme.dohna
            x: root.navigationHero ? 10 : 7
            y: root.navigationHero ? Math.max(0, (parent.height - height) / 2) : 8
            width: root.navigationHero ? 34 : 24
            height: root.navigationHero ? 28 : 18
            text: root.navigationNumber
            color: root.theme.refraStyle && root.primary ? root.theme.ink
                  : root.primary ? root.theme.accent : root.theme.textDim
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: root.navigationHero ? 16 : 12
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            id: navigationTitleLabel
            objectName: "navigationTitleLabel"
            visible: root.navigation && !root.theme.dohna
            x: root.navigationHero ? 54 : 37
            y: root.theme.refraStyle && !root.navigationHero ? 1 : (root.theme.refraStyle ? 0 : 3)
            width: root.theme.refraStyle && root.navigationHero
                   ? Math.min(parent.width - x - 8,
                              navigationHeroTitleMetrics.tightBoundingRect.width + 6)
                   : Math.max(0, parent.width - x - (root.theme.refraStyle ? 10 : 5))
            height: root.theme.refraStyle ? (root.navigationHero ? parent.height : 36) : 24
            text: root.text
            color: root.theme.refraStyle && root.primary ? root.theme.ink
                  : !root.enabled ? root.theme.textDim
                  : root.theme.refraStyle && root.navigationCool ? root.theme.electric
                  : root.theme.text
            font.family: root.theme.refraStyle && !root.theme.containsCjk(text)
                         ? "Arial Black" : root.theme.displayFontFor(text)
            font.pixelSize: root.theme.refraStyle
                            ? (root.navigationHero
                               ? (root.navigationHeroFontSize > 0
                                  ? root.navigationHeroFontSize
                                  : Math.max(64, Math.min(96, (root.width - 126) / 5.5)))
                               : Math.max(16, Math.min(28, (root.width - 52)
                                                       / Math.max(5, String(text).length * 0.67)))
                              )
                            : 15
            font.weight: root.theme.refraStyle
                         ? Font.Black : root.primary ? Font.Bold : Font.DemiBold
            font.italic: root.theme.refraStyle
            font.letterSpacing: root.theme.refraStyle ? (root.navigationHero ? -2.8 : -1.4) : 0
            fontSizeMode: root.theme.refraStyle && root.navigation && !root.navigationHero
                          ? Text.HorizontalFit : Text.FixedSize
            minimumPixelSize: root.theme.refraStyle && root.navigation && !root.navigationHero ? 16 : 1
            verticalAlignment: Text.AlignVCenter
            elide: root.theme.refraStyle ? Text.ElideNone : Text.ElideRight
        }

        Text {
            id: navigationSubtitleLabel
            objectName: "navigationSubtitleLabel"
            visible: root.navigation && !root.theme.dohna && root.theme.refraStyle
            x: root.navigationHero
               ? Math.min(parent.width - implicitWidth - 5,
                          navigationTitleLabel.x
                          + navigationHeroTitleMetrics.tightBoundingRect.width + 12)
               : 37
            y: root.navigationHero ? 0 : 35
            width: root.navigationHero
                   ? Math.max(0, Math.min(parent.width - x - 5, implicitWidth))
                   : Math.max(0, Math.min(parent.width - x - 5, implicitWidth))
            height: root.navigationHero ? parent.height : 25
            text: root.navigationSubtitle
            color: root.primary ? root.theme.ink
                  : root.navigationCool ? root.theme.electric : root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: root.navigationHero ? 24 : 14
            font.weight: Font.Bold
            verticalAlignment: Text.AlignVCenter
            elide: root.navigationHero ? Text.ElideNone : Text.ElideRight
        }

        Shape {
            id: navigationHeroSlash
            objectName: "navigationHeroSlash"
            visible: root.theme.refraStyle && root.navigation && root.navigationHero
                     && root.navigationSlashVisible
            readonly property real edgePadding: 2
            readonly property real visualX: navigationSubtitleLabel.x + navigationSubtitleLabel.width + 10
            readonly property real visualY: parent.height * 0.80
            x: visualX - edgePadding
            y: visualY - edgePadding
            width: Math.max(0, parent.width - visualX - 5) + edgePadding * 2
            height: 6 + edgePadding * 2
            opacity: root.primary ? 0.88 : 0.66
            preferredRendererType: Shape.CurveRenderer
            layer.enabled: true
            layer.smooth: true
            layer.textureSize: Qt.size(
                Math.ceil(width * Math.max(1, Screen.devicePixelRatio) * 2),
                Math.ceil(height * Math.max(1, Screen.devicePixelRatio) * 2)
            )
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.navigationCool ? root.theme.electric : root.theme.accent
                startX: navigationHeroSlash.edgePadding
                startY: navigationHeroSlash.edgePadding + 3
                PathLine {
                    x: Math.max(
                        0,
                        navigationHeroSlash.width
                        - navigationHeroSlash.edgePadding * 2
                        - 24
                    ) + navigationHeroSlash.edgePadding
                    y: navigationHeroSlash.edgePadding
                }
                PathLine {
                    x: navigationHeroSlash.width - navigationHeroSlash.edgePadding
                    y: navigationHeroSlash.edgePadding + 1.4
                }
                PathLine {
                    x: Math.max(
                        0,
                        navigationHeroSlash.width
                        - navigationHeroSlash.edgePadding * 2
                        - 24
                    ) + navigationHeroSlash.edgePadding
                    y: navigationHeroSlash.height - navigationHeroSlash.edgePadding
                }
                PathLine {
                    x: navigationHeroSlash.edgePadding
                    y: navigationHeroSlash.edgePadding + 4
                }
                PathLine {
                    x: navigationHeroSlash.edgePadding
                    y: navigationHeroSlash.edgePadding + 3
                }
            }
        }

        Text {
            objectName: "navigationCodeLabel"
            visible: root.navigation && !root.theme.dohna && !root.theme.refraStyle
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
        clip: !root.theme.dohna && !(root.theme.refraStyle && root.navigation)
        transform: Translate {
            y: root.theme.dohna ? root.dohnaImpact * 2 : 0
        }
        color: !root.enabled ? "transparent"
              : root.navigation ? "transparent"
              : root.theme.dohna ? "transparent"
              : root.theme.refraStyle && root.p3Action ? "transparent"
              : root.primary ? root.theme.buttonPrimary
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.12)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.065)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: root.theme.dohna || root.navigation
                      || (root.theme.refraStyle && root.p3Action) ? "transparent"
                    : root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
                    : root.primary && root.theme.dohna ? root.theme.selectionEdge
                    : root.primary ? root.theme.accent
                    : root.theme.lineStrong
        border.width: root.theme.dohna || root.navigation
                      || (root.theme.refraStyle && root.p3Action) ? 0
                      : (root.activeFocus ? 2 : root.primary ? 1.5 : 1)
        opacity: root.dohnaGroupFrame
                 ? (root.dohnaGroupEnabled ? 1 : 0.55)
                 : root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.ui } }
        Behavior on border.color { ColorAnimation { duration: root.theme.ui } }

        Rectangle {
            objectName: "prismButtonLightEdge"
            visible: !root.theme.dohna && !root.theme.refraStyle
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.primary ? 2 : 1
            color: root.primary && root.theme.dohna ? root.theme.selectionEdge
                 : root.primary ? root.theme.accent : root.theme.lineStrong
            opacity: root.enabled ? (root.primary || root.hovered || root.activeFocus ? 0.9 : 0.24) : 0.15
            Behavior on opacity { NumberAnimation { duration: root.theme.ui } }
        }

        Shape {
            id: prismNavigationSidebarMagenta
            objectName: "prismNavigationMagentaOffset"
            visible: root.theme.refraStyle && root.navigation && root.primary && root.enabled
                     && !root.navigationHero
            readonly property real edgePadding: 3
            x: 10 - edgePadding
            y: 8 - edgePadding
            width: Math.max(0, parent.width - 16) + edgePadding * 2
            height: Math.max(0, parent.height - 13) + edgePadding * 2
            preferredRendererType: Shape.CurveRenderer
            layer.enabled: true
            layer.smooth: true
            layer.textureSize: Qt.size(
                Math.ceil(width * Math.max(1, Screen.devicePixelRatio) * 2),
                Math.ceil(height * Math.max(1, Screen.devicePixelRatio) * 2)
            )
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.spectrum
                startX: 8 + prismNavigationSidebarMagenta.edgePadding
                startY: prismNavigationSidebarMagenta.edgePadding
                PathLine {
                    x: prismNavigationSidebarMagenta.width - prismNavigationSidebarMagenta.edgePadding
                    y: prismNavigationSidebarMagenta.edgePadding
                }
                PathLine {
                    x: prismNavigationSidebarMagenta.width - prismNavigationSidebarMagenta.edgePadding - 12
                    y: prismNavigationSidebarMagenta.height - prismNavigationSidebarMagenta.edgePadding
                }
                PathLine {
                    x: prismNavigationSidebarMagenta.edgePadding
                    y: prismNavigationSidebarMagenta.height - prismNavigationSidebarMagenta.edgePadding
                }
                PathLine {
                    x: 8 + prismNavigationSidebarMagenta.edgePadding
                    y: prismNavigationSidebarMagenta.edgePadding
                }
            }
        }
        Shape {
            id: prismNavigationSidebarActive
            objectName: "prismNavigationActivePlate"
            visible: root.theme.refraStyle && root.navigation && root.primary && root.enabled
                     && !root.navigationHero
            readonly property real edgePadding: 3
            x: -edgePadding
            y: 4 - edgePadding
            width: Math.max(0, parent.width - 18) + edgePadding * 2
            height: Math.max(0, parent.height - 10) + edgePadding * 2
            preferredRendererType: Shape.CurveRenderer
            layer.enabled: true
            layer.smooth: true
            layer.textureSize: Qt.size(
                Math.ceil(width * Math.max(1, Screen.devicePixelRatio) * 2),
                Math.ceil(height * Math.max(1, Screen.devicePixelRatio) * 2)
            )
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.accent
                startX: 8 + prismNavigationSidebarActive.edgePadding
                startY: prismNavigationSidebarActive.edgePadding
                PathLine {
                    x: prismNavigationSidebarActive.width - prismNavigationSidebarActive.edgePadding
                    y: prismNavigationSidebarActive.edgePadding
                }
                PathLine {
                    x: prismNavigationSidebarActive.width - prismNavigationSidebarActive.edgePadding - 12
                    y: prismNavigationSidebarActive.height - prismNavigationSidebarActive.edgePadding
                }
                PathLine {
                    x: prismNavigationSidebarActive.edgePadding
                    y: prismNavigationSidebarActive.height - prismNavigationSidebarActive.edgePadding
                }
                PathLine {
                    x: 8 + prismNavigationSidebarActive.edgePadding
                    y: prismNavigationSidebarActive.edgePadding
                }
            }
        }

        Shape {
            id: navigationHeroMagentaShape
            objectName: "prismNavigationHeroMagentaWedge"
            visible: root.theme.refraStyle && root.navigation && root.navigationHero
                     && root.primary && root.enabled
            readonly property real edgePadding: 4
            x: 13 - edgePadding
            y: 10 - edgePadding
            width: parent.width * 0.85 + edgePadding * 2
            height: parent.height - 20 + edgePadding * 2
            rotation: -2.2
            preferredRendererType: Shape.CurveRenderer
            layer.enabled: true
            layer.smooth: true
            layer.textureSize: Qt.size(
                Math.ceil(width * Math.max(1, Screen.devicePixelRatio) * 2),
                Math.ceil(height * Math.max(1, Screen.devicePixelRatio) * 2)
            )
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.spectrum
                startX: 18 + navigationHeroMagentaShape.edgePadding
                startY: navigationHeroMagentaShape.edgePadding
                PathLine {
                    x: navigationHeroMagentaShape.width * 0.96 - navigationHeroMagentaShape.edgePadding * 0.92
                    y: navigationHeroMagentaShape.edgePadding
                }
                PathLine {
                    x: navigationHeroMagentaShape.width * 0.88 - navigationHeroMagentaShape.edgePadding * 0.76
                    y: navigationHeroMagentaShape.height - navigationHeroMagentaShape.edgePadding
                }
                PathLine {
                    x: navigationHeroMagentaShape.edgePadding
                    y: navigationHeroMagentaShape.height - navigationHeroMagentaShape.edgePadding
                }
                PathLine {
                    x: 18 + navigationHeroMagentaShape.edgePadding
                    y: navigationHeroMagentaShape.edgePadding
                }
            }
        }

        Shape {
            id: navigationHeroActiveShape
            objectName: "prismNavigationHeroActiveWedge"
            visible: root.theme.refraStyle && root.navigation && root.navigationHero
                     && root.primary && root.enabled
            readonly property real edgePadding: 4
            x: 3 - edgePadding
            y: 3 - edgePadding
            width: parent.width * 0.85 + edgePadding * 2
            height: parent.height - 16 + edgePadding * 2
            rotation: -2.2
            preferredRendererType: Shape.CurveRenderer
            layer.enabled: true
            layer.smooth: true
            layer.textureSize: Qt.size(
                Math.ceil(width * Math.max(1, Screen.devicePixelRatio) * 2),
                Math.ceil(height * Math.max(1, Screen.devicePixelRatio) * 2)
            )
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.accent
                startX: 18 + navigationHeroActiveShape.edgePadding
                startY: navigationHeroActiveShape.edgePadding
                PathLine {
                    x: navigationHeroActiveShape.width * 0.96 - navigationHeroActiveShape.edgePadding * 0.92
                    y: navigationHeroActiveShape.edgePadding
                }
                PathLine {
                    x: navigationHeroActiveShape.width * 0.88 - navigationHeroActiveShape.edgePadding * 0.76
                    y: navigationHeroActiveShape.height - navigationHeroActiveShape.edgePadding
                }
                PathLine {
                    x: navigationHeroActiveShape.edgePadding
                    y: navigationHeroActiveShape.height - navigationHeroActiveShape.edgePadding
                }
                PathLine {
                    x: 18 + navigationHeroActiveShape.edgePadding
                    y: navigationHeroActiveShape.edgePadding
                }
            }
        }

        Shape {
            objectName: "prismP3ActionWedge"
            visible: root.theme.refraStyle && root.p3Action && root.enabled
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.primary ? "transparent" : root.theme.electric
                strokeWidth: root.primary ? 0 : 1.4
                fillColor: root.primary ? root.theme.buttonPrimary
                          : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.14)
                          : Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.035)
                startX: 18
                startY: 0
                PathLine { x: root.width; y: 0 }
                PathLine { x: root.width - 18; y: root.height }
                PathLine { x: 0; y: root.height }
                PathLine { x: 18; y: 0 }
            }
        }

        Shape {
            id: p3ActionLeadFacet
            objectName: "prismP3ActionLeadFacet"
            visible: root.theme.refraStyle && root.p3Action && root.primary && root.enabled
            x: 0
            y: 0
            width: 32
            height: parent.height
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.accent
                startX: 21
                startY: 0
                PathLine { x: 32; y: 0 }
                PathLine { x: 11; y: p3ActionLeadFacet.height }
                PathLine { x: 0; y: p3ActionLeadFacet.height }
                PathLine { x: 21; y: 0 }
            }
        }

        Text {
            objectName: "prismP3ActionPlayMark"
            visible: root.theme.refraStyle && root.p3Action && root.primary
            x: 22
            y: 0
            width: 28
            height: parent.height
            text: "▶"
            color: root.theme.buttonPrimaryText
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 22
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        Shape {
            objectName: "prismButtonPrimaryFacet"
            visible: !root.theme.dohna && root.primary && root.enabled && !root.navigation
                     && !(root.theme.refraStyle && root.p3Action)
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
