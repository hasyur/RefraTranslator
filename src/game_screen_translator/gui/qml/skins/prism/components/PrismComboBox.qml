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
        implicitWidth: 16
        implicitHeight: 16



        Shape {
            objectName: root.theme.active ? ("prismComboBoxChevron") : ""
            visible: !false
            anchors.centerIn: parent
            width: 9
            height: 6
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.theme.accentText
                strokeWidth: 1.6
                fillColor: "transparent"
                startX: 0
                startY: 0
                PathLine { x: 4.5; y: 4.5 }
                PathLine { x: 9; y: 0 }
            }
        }
    }

    background: Rectangle {
        objectName: root.theme.active ? ("prismComboBoxBackground") : ""
        clip: !false
        color: root.theme.inputSurface
        border.color: root.activeFocus ? root.theme.accent : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : 1



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
            leftPadding: 0
            rightPadding: 0
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Item {
            Rectangle {
                objectName: root.theme.active ? ("prismComboBoxDelegatePrismBackground") : ""
                anchors.fill: parent
                visible: !false
                color: !false && comboDelegate.highlighted
                       ? Qt.rgba(root.theme.accent.r,
                                 root.theme.accent.g,
                                 root.theme.accent.b,
                                 0.14)
                       : root.theme.inputSurface
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
                objectName: root.theme.active ? ("prismComboBoxPopupPrismBackground") : ""
                visible: !false
                anchors.fill: parent
                color: Qt.rgba(root.theme.inputSurface.r,
                               root.theme.inputSurface.g,
                               root.theme.inputSurface.b,
                               1)
                border.color: root.theme.lineStrong
                border.width: 1
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
