import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

ComboBox {
    id: control
    required property var theme
    implicitHeight: 40
    leftPadding: 10
    rightPadding: 34
    font.family: theme.uiFontFor(displayText)
    font.pixelSize: 13
    Accessible.role: Accessible.ComboBox

    contentItem: Text {
        leftPadding: control.leftPadding
        rightPadding: control.rightPadding
        text: control.displayText
        color: control.enabled ? control.theme.text : control.theme.textDim
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Shape {
        x: control.width - width - 12
        y: (control.height - height) / 2
        width: 12
        height: 8
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: control.theme.accent
            strokeWidth: 0
            startX: 0
            startY: 0
            PathLine { x: 12; y: 0 }
            PathLine { x: 6; y: 8 }
            PathLine { x: 0; y: 0 }
        }
    }
    background: Rectangle {
        color: control.enabled ? control.theme.inputSurface : control.theme.inputTrack
        border.color: control.visualFocus || control.popup.visible
                    ? control.theme.spectrum : control.theme.lineStrong
        border.width: control.visualFocus || control.popup.visible ? 2 : 1
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: control.width
        height: 36
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: String(modelData)
            color: control.theme.text
            font: control.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            color: parent.highlighted || parent.hovered ? control.theme.inputTrack : control.theme.white
        }
    }
    popup: Popup {
        y: control.height
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight, 250)
        padding: 1
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        background: Rectangle {
            color: control.theme.white
            border.color: control.theme.lineStrong
        }
    }
}
