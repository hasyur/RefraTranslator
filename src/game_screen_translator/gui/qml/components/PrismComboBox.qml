pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

ComboBox {
    id: root

    required property var theme
    property var itemEnabled: []
    property string accessibleName: ""
    property string settingDescription: ""
    property string settingKey: ""

    Accessible.name: root.accessibleName.length > 0 ? root.accessibleName : root.displayText

    function isItemEnabled(index) {
        return !root.itemEnabled
                || root.itemEnabled.length <= index
                || Boolean(root.itemEnabled[index])
    }

    implicitHeight: 42
    leftPadding: 12
    rightPadding: 34
    font.family: root.theme.uiFontFor(root.displayText)
    font.pixelSize: 13
    hoverEnabled: true

    contentItem: Text {
        leftPadding: 0
        rightPadding: root.indicator.width + root.spacing
        text: root.displayText
        color: root.enabled ? root.theme.text : root.theme.textDim
        font: root.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Text {
        x: root.width - width - 12
        y: (root.height - height) / 2
        text: "⌄"
        color: root.theme.accentText
        font.pixelSize: 16
    }

    background: Rectangle {
        objectName: "prismComboBoxBackground"
        clip: !root.theme.dohna
        color: root.theme.inputSurface
        border.color: root.activeFocus ? root.theme.accent : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : 1

        Rectangle {
            objectName: "prismComboBoxDohnaShadow"
            visible: root.theme.dohna
            x: 4
            y: 4
            width: parent.width
            height: parent.height
            color: root.theme.stageShadow
            z: -1
        }

        Shape {
            objectName: "prismComboBoxDohnaCorner"
            visible: root.theme.dohna && (root.hovered || root.activeFocus || root.popup.visible)
            anchors.right: parent.right
            anchors.top: parent.top
            width: 38
            height: 18
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.theme.ink
                strokeWidth: root.activeFocus ? 2 : 1
                fillColor: root.popup.visible ? root.theme.violet : root.theme.spectrum
                startX: 3
                startY: 0
                PathLine { x: 34; y: 0 }
                PathLine { x: 38; y: 16 }
                PathLine { x: 8; y: 18 }
                PathLine { x: 3; y: 0 }
            }
        }
    }

    delegate: ItemDelegate {
        id: comboDelegate
        required property var modelData
        required property int index
        width: root.width
        enabled: root.isItemEnabled(comboDelegate.index)
        highlighted: root.highlightedIndex === comboDelegate.index
        contentItem: Text {
            text: String(comboDelegate.modelData)
            color: comboDelegate.enabled ? root.theme.text : root.theme.textDim
            font: root.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Item {
            Rectangle {
                objectName: "prismComboBoxDelegatePrismBackground"
                anchors.fill: parent
                visible: !root.theme.dohna || !comboDelegate.highlighted
                color: !root.theme.dohna && comboDelegate.highlighted
                       ? Qt.rgba(root.theme.accent.r,
                                 root.theme.accent.g,
                                 root.theme.accent.b,
                                 0.14)
                       : root.theme.inputSurface
            }

            Shape {
                id: dohnaDelegateCut
                objectName: "prismComboBoxDohnaDelegateCut"
                visible: root.theme.dohna && comboDelegate.highlighted
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: root.theme.ink
                    strokeWidth: 2
                    fillColor: root.theme.spectrum
                    startX: 0
                    startY: 0
                    PathLine { x: dohnaDelegateCut.width - 10; y: 0 }
                    PathLine { x: dohnaDelegateCut.width; y: dohnaDelegateCut.height }
                    PathLine { x: 0; y: dohnaDelegateCut.height }
                    PathLine { x: 0; y: 0 }
                }
            }
        }
    }

    popup: Popup {
        y: root.height + 2
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + 2, 260)
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }

        background: Rectangle {
            color: root.theme.inputSurface
            border.color: root.theme.lineStrong
            border.width: root.theme.dohna ? 3 : 1
        }
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
