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
    // P3 navigation moves continuously between the compact rail and Home hero.
    property real navigationPresentationProgress: navigationHero ? 1 : 0
    readonly property real navigationHeroProgress: navigationPresentationProgress
    function navigationTextCoolColor() {
        const progress = Math.max(0, Math.min(1, root.navigationHeroProgress))
        const base = root.theme.text
        const cool = root.theme.electric
        return Qt.rgba(base.r * (1 - progress) + cool.r * progress,
                       base.g * (1 - progress) + cool.g * progress,
                       base.b * (1 - progress) + cool.b * progress,
                       base.a * (1 - progress) + cool.a * progress)
    }
    property real navigationHeroFontSize: 0
    property bool navigationSlashVisible: false
    property bool p3Action: false
    property string tone: "neutral"

    implicitWidth: Math.max(112, contentItem.implicitWidth + 30)
    implicitHeight: root.navigation ? ( (60 * root.navigationHeroProgress + 66 * (1 - root.navigationHeroProgress))
                                         ) : 42
    verticalPadding: padding
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    // Rotate the menu control itself so its label and hit target follow the bar.
    rotation: true && root.navigation ? root.navigationTilt : 0
    scale: (root.down ? 0.994 : root.hovered && root.enabled ? 1.004 : 1)

    Behavior on scale {
        NumberAnimation { duration: root.theme.fast; easing.type: Easing.OutCubic }
    }

    TextMetrics {
        id: navigationTextMetrics
        font: buttonLabel.font
        text: buttonLabel.text
    }

    contentItem: Item {
        implicitWidth: root.navigation && !false
                       ? ( (520 * root.navigationHeroProgress + 160 * (1 - root.navigationHeroProgress))
                          )
                       : buttonLabel.implicitWidth
        implicitHeight: root.navigation && !false
                        ? ( (58 * root.navigationHeroProgress + 64 * (1 - root.navigationHeroProgress))
                           )
                        : buttonLabel.implicitHeight

        TextMetrics {
            id: navigationHeroTitleMetrics
            font: navigationTitleLabel.font
            text: navigationTitleLabel.text
        }

        Text {
            id: buttonLabel
            objectName: root.theme.active ? ("prismButtonLabel") : ""
            anchors.fill: parent
            visible: !root.navigation || false
            text: root.text
            color: !root.enabled ? root.theme.textDim
                  : root.tone === "danger" ? root.theme.danger
                  : root.primary ? ( root.theme.buttonPrimaryText)
                  : root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: true && root.p3Action
                            ? (root.primary ? 20 : 17)
                            : 13
            font.weight: true && root.p3Action ? Font.Bold
                         : Font.DemiBold
            font.letterSpacing: 0.2
            fontSizeMode: Text.FixedSize
            leftPadding: true && root.p3Action && root.primary ? 35 : 0
            rightPadding: leftPadding
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
        }

        Text {
            objectName: root.theme.active ? ("navigationNumberLabel") : ""
            visible: root.navigation && !false
            x: 10 * root.navigationHeroProgress + 7 * (1 - root.navigationHeroProgress)
            y: Math.max(0, (parent.height - height) / 2) * root.navigationHeroProgress
               + 8 * (1 - root.navigationHeroProgress)
            width: 34 * root.navigationHeroProgress + 24 * (1 - root.navigationHeroProgress)
            height: 28 * root.navigationHeroProgress + 18 * (1 - root.navigationHeroProgress)
            text: root.navigationNumber
            color: true && root.primary ? root.theme.ink
                  : root.primary ? root.theme.accent : root.theme.textDim
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 16 * root.navigationHeroProgress + 12 * (1 - root.navigationHeroProgress)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            id: navigationTitleLabel
            objectName: root.theme.active ? ("navigationTitleLabel") : ""
            visible: root.navigation && !false
            x: 54 * root.navigationHeroProgress + 37 * (1 - root.navigationHeroProgress)
               
            y: (1 - root.navigationHeroProgress)
               
            width: Math.min(parent.width - x - 8,
                              navigationHeroTitleMetrics.tightBoundingRect.width + 6)
                     * root.navigationHeroProgress
                     + Math.max(0, parent.width - x - 10) * (1 - root.navigationHeroProgress)
                   
            height: parent.height * root.navigationHeroProgress + 36 * (1 - root.navigationHeroProgress)
                    
            text: root.text
            color: true && root.primary ? root.theme.ink
                  : !root.enabled ? root.theme.textDim
                  : true && root.navigationCool ? root.navigationTextCoolColor()
                  : root.theme.text
            font.family: true && !root.theme.containsCjk(text)
                         ? "Arial Black" : root.theme.displayFontFor(text)
            font.pixelSize: (root.navigationHeroFontSize > 0
                               ? root.navigationHeroFontSize
                               : Math.max(64, Math.min(96, (root.width - 126) / 5.5)))
                              * root.navigationHeroProgress
                              + Math.max(16, Math.min(28, (root.width - 52)
                                                      / Math.max(5, String(text).length * 0.67)))
                                * (1 - root.navigationHeroProgress)
                            
            font.weight: Font.Black 
            font.italic: true
            font.letterSpacing: (-2.8 * root.navigationHeroProgress
                                   -1.4 * (1 - root.navigationHeroProgress)) 
            fontSizeMode: true && root.navigation
                          && root.navigationHeroProgress < 0.001
                          ? Text.HorizontalFit : Text.FixedSize
            minimumPixelSize: true && root.navigation
                              && root.navigationHeroProgress < 0.001 ? 16 : 1
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideNone }

        Text {
            id: navigationSubtitleLabel
            objectName: root.theme.active ? ("navigationSubtitleLabel") : ""
            visible: root.navigation
            opacity: {
                const progress = Math.max(0, Math.min(1, root.navigationHeroProgress))
                const railFadeEnd = 0.12
                const heroFadeStart = 0.88
                if (progress <= railFadeEnd)
                    return 1 - progress / railFadeEnd
                if (progress >= heroFadeStart)
                    return (progress - heroFadeStart) / (1 - heroFadeStart)
                return 0
            }
            x: {
                const heroX = Math.min(parent.width - implicitWidth - 5,
                                       navigationTitleLabel.x
                                       + navigationHeroTitleMetrics.tightBoundingRect.width + 12)
                return 37 * (1 - root.navigationHeroProgress) + heroX * root.navigationHeroProgress
            }
            y: 35 * (1 - root.navigationHeroProgress)
            width: {
                const railWidth = Math.max(0, Math.min(parent.width - 37 - 5, implicitWidth))
                const heroWidth = Math.max(0, Math.min(parent.width - x - 5, implicitWidth))
                return railWidth * (1 - root.navigationHeroProgress)
                       + heroWidth * root.navigationHeroProgress
            }
            height: 25 * (1 - root.navigationHeroProgress)
                    + parent.height * root.navigationHeroProgress
            text: root.navigationSubtitle
            color: root.primary ? root.theme.ink
                  : root.navigationCool ? root.navigationTextCoolColor() : root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 24 * root.navigationHeroProgress
                            + 14 * (1 - root.navigationHeroProgress)
            font.weight: Font.Bold
            verticalAlignment: Text.AlignVCenter
            elide: root.navigationHeroProgress > 0.5 ? Text.ElideNone : Text.ElideRight
        }

        Shape {
            id: navigationHeroSlash
            objectName: root.theme.active ? ("navigationHeroSlash") : ""
            visible: true && root.navigation
                     && root.navigationSlashVisible
                     && (root.navigationHero || root.navigationHeroProgress > 0)
            readonly property real edgePadding: 2
            readonly property real visualX: navigationSubtitleLabel.x + navigationSubtitleLabel.width + 10
            readonly property real visualY: parent.height * 0.80
            x: visualX - edgePadding
            y: visualY - edgePadding
            width: Math.max(0, parent.width - visualX - 5) + edgePadding * 2
            height: 6 + edgePadding * 2
            opacity: (root.primary ? 0.88 : 0.66)
                     * (root.navigationHero ? 1 : root.navigationHeroProgress)
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


    }

    background: Rectangle {
        id: buttonSurface
        clip: !false && !(true && root.navigation)
        transform: Translate {
            y: 0
        }
        color: !root.enabled ? "transparent"
              : root.navigation ? "transparent"
              : true && root.p3Action ? "transparent"
              : root.primary ? root.theme.buttonPrimary
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.12)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.065)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: false || root.navigation
                      || (true && root.p3Action) ? "transparent"
                    : root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
                    : root.primary ? root.theme.accent
                    : root.theme.lineStrong
        border.width: false || root.navigation
                      || (true && root.p3Action) ? 0
                      : (root.activeFocus ? 2 : root.primary ? 1.5 : 1)
        opacity: root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.ui } }
        Behavior on border.color { ColorAnimation { duration: root.theme.ui } }



        Shape {
            id: prismNavigationSidebarMagenta
            objectName: root.theme.active ? ("prismNavigationMagentaOffset") : ""
            visible: true && root.navigation && root.primary && root.enabled
                     && root.navigationHeroProgress < 1
            opacity: 1 - root.navigationHeroProgress
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
            objectName: root.theme.active ? ("prismNavigationActivePlate") : ""
            visible: true && root.navigation && root.primary && root.enabled
                     && root.navigationHeroProgress < 1
            opacity: 1 - root.navigationHeroProgress
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
            objectName: root.theme.active ? ("prismNavigationHeroMagentaWedge") : ""
            visible: true && root.navigation
                     && root.navigationHeroProgress > 0
                     && root.primary && root.enabled
            opacity: root.navigationHeroProgress
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
            objectName: root.theme.active ? ("prismNavigationHeroActiveWedge") : ""
            visible: true && root.navigation
                     && root.navigationHeroProgress > 0
                     && root.primary && root.enabled
            opacity: root.navigationHeroProgress
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
            objectName: root.theme.active ? ("prismP3ActionWedge") : ""
            visible: true && root.p3Action && root.enabled
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
            objectName: root.theme.active ? ("prismP3ActionLeadFacet") : ""
            visible: true && root.p3Action && root.primary && root.enabled
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
            objectName: root.theme.active ? ("prismP3ActionPlayMark") : ""
            visible: true && root.p3Action && root.primary
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
            objectName: root.theme.active ? ("prismButtonPrimaryFacet") : ""
            visible: !false && root.primary && root.enabled && !root.navigation
                     && !(true && root.p3Action)
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















    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }

}
