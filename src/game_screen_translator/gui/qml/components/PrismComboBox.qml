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
        color: root.theme.dohna ? root.theme.ink : root.theme.accentText
        font.pixelSize: 16
    }

    background: Rectangle {
        objectName: "prismComboBoxBackground"
        clip: !root.theme.dohna
        color: root.theme.dohna ? "transparent" : root.theme.inputSurface
        border.color: root.theme.dohna
                      ? "transparent"
                      : root.activeFocus ? root.theme.accent : root.theme.lineStrong
        border.width: root.theme.dohna ? 0 : root.activeFocus ? 2 : 1

        Shape {
            id: dohnaComboBody
            objectName: "prismComboBoxDohnaBody"
            visible: root.theme.dohna
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: "prismComboBoxDohnaBodyPath"
                strokeColor: "transparent"
                strokeWidth: 0
                fillColor: root.popup.visible ? root.theme.accent
                           : root.hovered || root.activeFocus ? root.theme.violet
                           : root.theme.white
                startX: 0
                startY: 0
                PathLine { x: dohnaComboBody.width - 14; y: 0 }
                PathLine { x: dohnaComboBody.width; y: dohnaComboBody.height }
                PathLine { x: 0; y: dohnaComboBody.height }
                PathLine { x: 0; y: 0 }
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
            leftPadding: root.theme.dohna ? 10 : 0
            rightPadding: root.theme.dohna ? 22 : 0
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Item {
            Rectangle {
                objectName: "prismComboBoxDelegatePrismBackground"
                anchors.fill: parent
                visible: !root.theme.dohna
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
                visible: root.theme.dohna
                // Flat highlights stay inside the popup's slanted paper edge.
                x: 4
                y: 2
                width: Math.max(0, parent.width - 18)
                height: Math.max(0, parent.height - 4)
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    objectName: "prismComboBoxDohnaDelegatePath"
                    strokeColor: "transparent"
                    strokeWidth: 0
                    fillColor: comboDelegate.index === root.currentIndex
                               ? root.theme.accent
                               : comboDelegate.highlighted
                                 ? root.theme.violet
                                 : "transparent"
                    startX: 0
                    startY: 0
                    PathLine {
                        x: dohnaDelegateCut.width
                               - (comboDelegate.highlighted || comboDelegate.index === root.currentIndex ? 10 : 0)
                        y: 0
                    }
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

        background: Item {
            Rectangle {
                objectName: "prismComboBoxPopupPrismBackground"
                visible: !root.theme.dohna
                anchors.fill: parent
                color: root.theme.inputSurface
                border.color: root.theme.lineStrong
                border.width: 1
            }

            Shape {
                id: dohnaPopupBody
                objectName: "prismComboBoxDohnaPopupBody"
                visible: root.theme.dohna
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    objectName: "prismComboBoxDohnaPopupPath"
                    strokeColor: "transparent"
                    strokeWidth: 0
                    fillColor: root.theme.white
                    startX: 0
                    startY: 0
                    PathLine { x: dohnaPopupBody.width - 14; y: 0 }
                    PathLine { x: dohnaPopupBody.width; y: dohnaPopupBody.height }
                    PathLine { x: 0; y: dohnaPopupBody.height }
                    PathLine { x: 0; y: 0 }
                }
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
