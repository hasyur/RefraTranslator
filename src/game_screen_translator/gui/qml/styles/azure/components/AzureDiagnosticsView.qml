import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    required property var theme
    required property var workbench
    property bool compact: false
    readonly property var diagnostics: workbench.latencyDiagnostics
    implicitHeight: diagnosticsContent.implicitHeight

    function compactMetrics(source, markers) {
        const lines = String(source || "").split(/\r?\n/)
        const selected = []
        for (const marker of markers) {
            const line = lines.find(value => value.includes(marker))
            if (line && !selected.includes(line))
                selected.push(line)
        }
        if (selected.length)
            return selected.join("\n")
        return lines.filter(value => value.trim().length > 0).slice(0, 2).join("\n")
    }

    Column {
        id: diagnosticsContent
        width: root.width
        spacing: root.compact ? 3 : 8

        Text {
            width: diagnosticsContent.width
            text: root.diagnostics.status
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: root.compact ? 10 : 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            visible: !root.compact || !root.diagnostics.available
        }
        Text {
            visible: !root.compact
            width: diagnosticsContent.width
            text: "PROFILE · REAL CONFIG"
            color: root.theme.accentText
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 10
            font.letterSpacing: 0.5
        }
        TextArea {
            objectName: "azureSettingsProfileDiagnostic"
            visible: !root.compact
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
                color: root.compact ? "transparent" : root.theme.inputSurface
                border.color: root.compact ? "transparent" : root.theme.line
            }
        }
        Text {
            width: diagnosticsContent.width
            text: root.compact ? "最近完成运行 · " + root.diagnostics.scope
                               : "最近运行延迟 · " + root.diagnostics.scope
            color: root.theme.accentText
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: root.compact ? 9 : 10
            font.letterSpacing: 0.2
        }
        Text {
            width: diagnosticsContent.width
            text: "OCR 流程"
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: root.compact ? 11 : 14
            font.weight: Font.DemiBold
            visible: !root.compact
        }
        TextArea {
            objectName: "azureSettingsOcrLatency"
            Accessible.name: "OCR 流程延迟"
            width: diagnosticsContent.width
            text: root.compact
                  ? root.compactMetrics(root.diagnostics.ocr, ["OCR："])
                  : root.diagnostics.ocr
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: root.compact ? 13 : 12
            font.weight: root.compact ? Font.DemiBold : Font.Normal
            wrapMode: TextEdit.Wrap
            height: root.compact ? Math.max(30, contentHeight + 12)
                                 : Math.max(30, contentHeight + 10)
            background: Rectangle {
                color: root.compact ? "transparent" : root.theme.inputSurface
                border.color: root.compact ? "transparent" : root.theme.line
            }
        }
        Rectangle { width: diagnosticsContent.width; height: 1; color: root.theme.line; visible: !root.compact }
        Text {
            width: diagnosticsContent.width
            text: "翻译流程"
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: root.compact ? 11 : 14
            font.weight: Font.DemiBold
            visible: !root.compact
        }
        TextArea {
            objectName: "azureSettingsTranslationLatency"
            Accessible.name: "翻译流程延迟"
            width: diagnosticsContent.width
            text: root.compact
                  ? root.compactMetrics(root.diagnostics.translation, ["LLM 请求"])
                  : root.diagnostics.translation
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: root.compact ? 13 : 12
            font.weight: root.compact ? Font.DemiBold : Font.Normal
            wrapMode: TextEdit.Wrap
            height: root.compact ? Math.max(30, contentHeight + 12)
                                 : Math.max(30, contentHeight + 10)
            background: Rectangle {
                color: root.compact ? "transparent" : root.theme.inputSurface
                border.color: root.compact ? "transparent" : root.theme.line
            }
        }
        Rectangle { width: diagnosticsContent.width; height: 1; color: root.theme.line; visible: !root.compact }
        Text {
            width: diagnosticsContent.width
            text: "延迟汇总"
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: root.compact ? 11 : 14
            font.weight: Font.DemiBold
            visible: !root.compact
        }
        TextArea {
            objectName: "azureSettingsLatencySummary"
            Accessible.name: "延迟汇总"
            width: diagnosticsContent.width
            text: root.compact
                  ? root.compactMetrics(root.diagnostics.summary, ["最近总延迟"])
                  : root.diagnostics.summary
            readOnly: true
            selectByMouse: true
            color: root.theme.textSoft
            selectionColor: root.theme.accent
            selectedTextColor: "#ffffff"
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: root.compact ? 13 : 12
            font.weight: root.compact ? Font.DemiBold : Font.Normal
            wrapMode: TextEdit.Wrap
            height: root.compact ? Math.max(30, contentHeight + 12)
                                 : Math.max(30, contentHeight + 10)
            background: Rectangle {
                color: root.compact ? "transparent" : root.theme.inputSurface
                border.color: root.compact ? "transparent" : root.theme.line
            }
        }
    }
}
