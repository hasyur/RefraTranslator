import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    required property var theme
    required property var workbench
    readonly property var diagnostics: workbench.latencyDiagnostics
    implicitHeight: diagnosticsContent.implicitHeight

    Column {
        id: diagnosticsContent
        width: root.width
        spacing: 8

        Text {
            width: diagnosticsContent.width
            text: root.diagnostics.status
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Text {
            width: diagnosticsContent.width
            text: "PROFILE · REAL CONFIG"
            color: root.theme.accentText
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 10
            font.letterSpacing: 0.5
        }
        TextArea {
            objectName: "azureSettingsProfileDiagnostic"
            Accessible.name: "Profile 诊断"
            width: diagnosticsContent.width
            text: root.workbench.infoText
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 11
            wrapMode: TextEdit.Wrap
            height: Math.max(108, contentHeight + 12)
            background: Rectangle {
                color: root.theme.inputSurface
                border.color: root.theme.line
            }
        }
        Text {
            width: diagnosticsContent.width
            text: "最近运行延迟 · " + root.diagnostics.scope
            color: root.theme.accentText
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 10
            font.letterSpacing: 0.2
        }
        Text {
            width: diagnosticsContent.width
            text: "OCR 流程"
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }
        TextArea {
            objectName: "azureSettingsOcrLatency"
            Accessible.name: "OCR 流程延迟"
            width: diagnosticsContent.width
            text: root.diagnostics.ocr
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 11
            wrapMode: TextEdit.Wrap
            height: Math.max(50, contentHeight + 10)
            background: Rectangle { color: root.theme.inputSurface; border.color: root.theme.line }
        }
        Rectangle { width: diagnosticsContent.width; height: 1; color: root.theme.line }
        Text {
            width: diagnosticsContent.width
            text: "翻译流程"
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }
        TextArea {
            objectName: "azureSettingsTranslationLatency"
            Accessible.name: "翻译流程延迟"
            width: diagnosticsContent.width
            text: root.diagnostics.translation
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 11
            wrapMode: TextEdit.Wrap
            height: Math.max(50, contentHeight + 10)
            background: Rectangle { color: root.theme.inputSurface; border.color: root.theme.line }
        }
        Rectangle { width: diagnosticsContent.width; height: 1; color: root.theme.line }
        Text {
            width: diagnosticsContent.width
            text: "延迟汇总"
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }
        TextArea {
            objectName: "azureSettingsLatencySummary"
            Accessible.name: "延迟汇总"
            width: diagnosticsContent.width
            text: root.diagnostics.summary
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 11
            wrapMode: TextEdit.Wrap
            height: Math.max(50, contentHeight + 10)
            background: Rectangle { color: root.theme.inputSurface; border.color: root.theme.line }
        }
    }
}
