import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root

    required property var theme
    required property var workbench
    required property var appShell
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    signal visualAction(string action)

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PrismPanel {
            objectName: root.theme.active ? ("cachePrimaryPanel") : ""
            theme: root.theme
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 350

            ColumnLayout {
                anchors.fill: parent
                spacing: 15

                SectionHeader {
                    theme: root.theme
                    title: "缓存阵列"
                    meta: root.workbench.hasProfile ? root.workbench.currentProfileName : "NO PROFILE"
                    Layout.fillWidth: true
                }

                GridLayout {
                    objectName: root.theme.active ? ("cacheSummaryMetrics") : ""
                    visible: root.workbench.hasProfile
                    Layout.fillWidth: true
                    columns: width >= 510 ? 4 : 2
                    columnSpacing: 10
                    rowSpacing: 10
                    Repeater {
                        model: [
                            {"label": "模型缓存", "value": root.workbench.automaticEntries, "tone": root.theme.accent},
                            {"label": "缓存命中", "value": root.workbench.automaticHits, "tone": root.theme.violet},
                            {"label": "人工修订", "value": root.workbench.manualCorrections, "tone": root.theme.spectrum},
                            {"label": "修订命中", "value": root.workbench.manualHits, "tone": root.theme.amber}
                        ]
                        Rectangle {
                            objectName: root.theme.active ? ("cacheMetricCard") : ""
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: 1
                            implicitHeight: 90
                            color: "transparent"
                            border.color: root.theme.line
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 3
                                Text {
                                    objectName: root.theme.active ? ("cacheMetricValue") : ""
                                    text: String(modelData.value)
                                    color: modelData.tone
                                    font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 29
                                    font.weight: Font.DemiBold
                                    fontSizeMode: Text.Fit
                                    minimumPixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                }
                                Text {
                                    text: modelData.label
                                    color: root.theme.textDim
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 13
                                }
                            }
                        }
                    }
                }

                UnavailableState {
                    objectName: root.theme.active ? ("cacheLastRunUnavailable") : ""
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.hasProfile
                    eyebrow: "CACHE · UNAVAILABLE"
                    title: "尚未选择 Profile"
                    detail: "没有真实缓存统计来源；请先在 HOME 创建或选择一个 Profile。"
                }

                Flickable {
                    objectName: root.theme.active ? ("cacheLastRunHits") : ""
                    visible: root.workbench.hasProfile
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: width
                    contentHeight: cacheLastRunHitsColumn.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: PrismScrollBar { id: cacheBar; theme: root.theme }
                    ColumnLayout {
                        id: cacheLastRunHitsColumn
                        width: parent.width - cacheBar.contentInset
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                    spacing: 8
                    SectionHeader {
                        theme: root.theme
                        title: "上次运行缓存命中"
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "TOP 5 · RUN ONLY"
                        color: root.theme.accentText
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 12
                        font.letterSpacing: 1
                        Layout.fillWidth: true
                    }
                    UnavailableState {
                        visible: root.workbench.lastRunAvailable
                                 && root.workbench.lastRunCacheHits.length === 0
                        theme: root.theme
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        eyebrow: "LAST RUN CACHE · EMPTY"
                        title: "上次运行无自动缓存命中"
                        detail: "当前上次运行快照没有记录自动缓存命中。"
                    }
                    UnavailableState {
                        visible: !root.workbench.lastRunAvailable
                        theme: root.theme
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        eyebrow: "LAST RUN CACHE · UNAVAILABLE"
                        title: "尚无上次运行结果"
                        detail: root.workbench.lastRunStatus
                    }
                    ColumnLayout {
                        visible: root.workbench.lastRunAvailable
                                 && root.workbench.lastRunCacheHits.length > 0
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Repeater {
                            model: root.workbench.lastRunCacheHits
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 48
                                color: "transparent"
                                border.color: root.theme.line
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    Text {
                                        objectName: root.theme.active ? ("cacheHitSource") : ""
                                        // OCR entries may contain newlines; each result remains one row.
                                        text: String(modelData.sourceText).replace(/\s+/g, " ").trim()
                                        color: root.theme.text
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 15
                                        elide: Text.ElideRight
                                        maximumLineCount: 1
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                    }
                                    Text {
                                        objectName: root.theme.active ? ("cacheHitCount") : ""
                                        text: String(modelData.hits) + " 次"
                                        color: root.theme.accentText
                                        font.family: root.theme.monoFontFor(text)
                                        font.pixelSize: 14
                                        fontSizeMode: Text.Fit
                                        minimumPixelSize: 12
                                        elide: Text.ElideRight
                                        Layout.maximumWidth: parent.width * 0.4
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        objectName: root.theme.active ? ("cacheSummarySourceHint") : ""
                        text: "上方为 Profile SQLite 累计统计；上次运行命中列表仅代表最近一次运行。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    }
                }

                PrismButton {
                    objectName: root.theme.active ? ("cacheRippleAction") : ""
                    theme: root.theme
                    text: "刷新真实统计"
                    enabled: root.workbench.hasProfile
                    Layout.alignment: Qt.AlignRight
                    onClicked: {
                        root.workbench.refreshStats()
                        root.visualAction("ripple")
                    }
                }
            }
        }

        PrismPanel {
            objectName: root.theme.active ? ("cacheSecondaryPanel") : ""
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.preferredWidth: 408
            Layout.maximumWidth: 408
            Layout.minimumWidth: 370
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 12

                SectionHeader {
                    theme: root.theme
                    title: "人工修订"
                    Layout.fillWidth: true
                }

                PairEditor {
                    objectName: root.theme.active ? ("correctionsEditor") : ""
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    initialEntries: root.workbench.correctionEntries
                    initialDirty: root.workbench.correctionsDirty
                    revisionKey: root.workbench.currentProfileId + ":" + root.workbench.profileRevision
                    sourceTitle: "识别原文"
                    targetTitle: "人工译文"
                    saveText: "保存人工修订"
                    settingDescription: "编辑当前游戏的识别原文与人工译文对应关系。"
                    settingKey: "cache-corrections"
                    enabled: root.workbench.hasProfile
                    onDraftChanged: entries => root.workbench.setCorrectionsDraft(entries)
                    onSaveRequested: entries => root.workbench.saveCorrections(entries)
                }
            }
        }
    }
}
