import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    required property var theme
    property int value: 0
    property int minimum: 0
    property int maximum: 100
    property int stepSize: 1
    property string suffix: ""
    property string accessibleName: ""
    property bool highlighted: false
    signal edited(int value)
    implicitHeight: 32
    implicitWidth: 190

    function refreshValueText() {
        valueField.text = String(root.value)
    }

    Connections {
        target: root
        function onValueChanged() {
            if (!valueField.activeFocus)
                root.refreshValueText()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        AzureButton {
            objectName: root.accessibleName + "DecreaseButton"
            theme: root.theme
            text: "−"
            quiet: true
            onAccent: root.highlighted
            implicitWidth: 38
            Layout.preferredHeight: 32
            Accessible.name: root.accessibleName + " 减少"
            onClicked: root.edited(Math.max(root.minimum, root.value - root.stepSize))
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: root.theme.inputSurface
            border.color: root.theme.line
            clip: true
            TextField {
                id: valueField
                anchors.fill: parent
                leftPadding: 5
                rightPadding: 5
                text: String(root.value)
                color: root.theme.text
                selectedTextColor: "#ffffff"
                selectionColor: root.theme.accent
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.family: root.theme.monoFontFor(text)
                font.pixelSize: 16
                objectName: root.accessibleName + "ValueField"
                validator: IntValidator { bottom: -2147483648; top: 2147483647 }
                background: null
                Accessible.name: root.accessibleName
                onEditingFinished: {
                    const candidate = text.trim()
                    if (candidate.length > 0) {
                        const parsed = Number(candidate)
                        if (Number.isInteger(parsed))
                            root.edited(Math.max(root.minimum, Math.min(root.maximum, parsed)))
                    }
                    root.refreshValueText()
                }
                onActiveFocusChanged: if (!activeFocus) root.refreshValueText()
            }
        }
        Text {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 32
            text: root.suffix
            color: root.highlighted ? "#dce8ff" : root.theme.textSoft
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
        }
        AzureButton {
            objectName: root.accessibleName + "IncreaseButton"
            theme: root.theme
            text: "+"
            quiet: true
            onAccent: root.highlighted
            implicitWidth: 38
            Layout.preferredHeight: 32
            Accessible.name: root.accessibleName + " 增加"
            onClicked: root.edited(Math.min(root.maximum, root.value + root.stepSize))
        }
    }
}
