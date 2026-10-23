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
    font.pixelSize: 15
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

    indicator: Item {
        x: root.width - width - 12
        y: (root.height - height) / 2
        implicitWidth: comboArrowText.implicitWidth 
        implicitHeight: comboArrowText.implicitHeight 
        Text {
            id: comboArrowText
            visible: true
            anchors.fill: parent
            text: "⌄"
            color: root.theme.ink
            font.pixelSize: 18
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }


    }

    background: Rectangle {
        objectName: root.theme.active ? ("prismComboBoxBackground") : ""
        clip: !true
        color: "transparent" 
        border.color: "transparent"
                      
        border.width: 0 
        Shape {
            id: dohnaComboBody
            objectName: root.theme.active ? ("prismComboBoxDohnaBody") : ""
            visible: true
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: root.theme.active ? ("prismComboBoxDohnaBodyPath") : ""
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
            leftPadding: 10 
            rightPadding: 22 
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Item {


            Shape {
                id: dohnaDelegateCut
                objectName: root.theme.active ? ("prismComboBoxDohnaDelegateCut") : ""
                visible: true
                // Flat highlights stay inside the popup's slanted paper edge.
                x: 4
                y: 2
                width: Math.max(0, parent.width - 18)
                height: Math.max(0, parent.height - 4)
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    objectName: root.theme.active ? ("prismComboBoxDohnaDelegatePath") : ""
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


            Shape {
                id: dohnaPopupBody
                objectName: root.theme.active ? ("prismComboBoxDohnaPopupBody") : ""
                visible: true
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    objectName: root.theme.active ? ("prismComboBoxDohnaPopupPath") : ""
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
        enabled: description.length > 0 && !root.popup.visible
    }
}
