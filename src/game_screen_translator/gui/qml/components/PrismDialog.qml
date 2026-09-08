import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root

    required property var theme
    property string surfaceName: "prismDialog"
    property string acceptText: "确认"
    property string rejectText: "取消"
    property string acceptTone: "neutral"
    property bool showAcceptButton: true
    property bool showRejectButton: true
    property bool acceptEnabled: true
    default property alias bodyData: bodyLayout.data

    modal: true
    padding: 0
    topPadding: 0
    bottomPadding: 0
    leftPadding: 0
    rightPadding: 0

    header: Rectangle {
        objectName: root.surfaceName + "Header"
        implicitHeight: 56
        color: root.theme.glassRaised
        border.color: root.theme.lineStrong
        border.width: 1

        Text {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            text: root.title
            color: root.theme.text
            font.family: root.theme.displayFontFor(text)
            font.pixelSize: 17
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    contentItem: Rectangle {
        objectName: root.surfaceName + "Content"
        implicitWidth: Math.max(260, bodyLayout.implicitWidth + 36)
        implicitHeight: Math.max(82, bodyLayout.implicitHeight + 36)
        color: root.theme.inkRaised

        ColumnLayout {
            id: bodyLayout
            anchors.fill: parent
            anchors.margins: 18
            spacing: 14
        }
    }

    footer: Rectangle {
        objectName: root.surfaceName + "Actions"
        implicitHeight: root.showAcceptButton || root.showRejectButton ? 66 : 0
        visible: implicitHeight > 0
        color: root.theme.panel
        border.color: root.theme.lineStrong
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            spacing: 10

            Item { Layout.fillWidth: true }

            PrismButton {
                objectName: root.surfaceName + "RejectButton"
                theme: root.theme
                text: root.rejectText
                visible: root.showRejectButton
                onClicked: root.reject()
            }

            PrismButton {
                objectName: root.surfaceName + "AcceptButton"
                theme: root.theme
                text: root.acceptText
                tone: root.acceptTone
                primary: root.acceptTone !== "danger"
                enabled: root.acceptEnabled
                visible: root.showAcceptButton
                onClicked: root.accept()
            }
        }
    }

    background: Rectangle {
        objectName: root.surfaceName + "Background"
        color: root.theme.inkRaised
        border.color: root.acceptTone === "danger"
                      ? root.theme.danger
                      : root.theme.lineStrong
        border.width: 1
    }
}
