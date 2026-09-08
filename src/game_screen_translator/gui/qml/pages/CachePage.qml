import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root

    required property var theme
    required property var workbench
    property string mode: "automatic"
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    signal visualAction(string action)

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PrismPanel {
            objectName: "cachePrimaryPanel"
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

                RowLayout {
                    objectName: "cacheSummaryMetrics"
                    visible: root.workbench.hasProfile
                    Layout.fillWidth: true
                    spacing: 10
                    Repeater {
                        model: [
                            {"label": "模型缓存", "value": root.workbench.automaticEntries, "tone": root.theme.accent},
                            {"label": "缓存命中", "value": root.workbench.automaticHits, "tone": root.theme.violet},
                            {"label": "人工修订", "value": root.workbench.manualCorrections, "tone": root.theme.spectrum},
                            {"label": "修订命中", "value": root.workbench.manualHits, "tone": root.theme.amber}
                        ]
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 98
                            color: "transparent"
                            border.color: root.theme.line
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 3
                                Text {
                                    objectName: "cacheMetricValue"
                                    text: String(modelData.value)
                                    color: modelData.tone
                                    font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 29
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: modelData.label
                                    color: root.theme.textDim
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }

                UnavailableState {
                    objectName: "cacheLastRunUnavailable"
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.hasProfile
                    eyebrow: "CACHE · UNAVAILABLE"
                    title: "尚未选择 Profile"
                    detail: "没有真实缓存统计来源；请先在 HOME 创建或选择一个 Profile。"
                }

                Flickable {
                    objectName: "cacheLastRunHits"
                    visible: root.workbench.hasProfile
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: width
                    contentHeight: cacheLastRunHitsColumn.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    ColumnLayout {
                        id: cacheLastRunHitsColumn
                        width: parent.width
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                    spacing: 8
                    SectionHeader {
                        theme: root.theme
                        title: "上次运行缓存命中"
                        meta: "TOP 5 · RUN ONLY"
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
                                        text: modelData.sourceText
                                        color: root.theme.text
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 13
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    Text {
                                        text: String(modelData.hits) + " 次"
                                        color: root.theme.accent
                                        font.family: root.theme.monoFontFor(text)
                                        font.pixelSize: 12
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        text: "下方累计统计来自 Profile SQLite；上方仅代表最近一次运行。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    }
                }

                PrismButton {
                    objectName: "cacheRippleAction"
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
            objectName: "cacheSecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 408
            Layout.minimumWidth: 370
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 7
                    PrismButton {
                        theme: root.theme
                        text: "自动缓存"
                        primary: root.mode === "automatic"
                        Layout.fillWidth: true
                        onClicked: {
                            root.mode = "automatic"
                            root.visualAction("ripple")
                        }
                    }
                    PrismButton {
                        theme: root.theme
                        text: "人工修订"
                        primary: root.mode === "corrections"
                        Layout.fillWidth: true
                        onClicked: {
                            root.mode = "corrections"
                            root.visualAction("ripple")
                        }
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.mode === "automatic" ? 0 : 1

                    ColumnLayout {
                        spacing: 12
                        SectionHeader {
                            theme: root.theme
                            title: "自动缓存"
                            meta: "READ ONLY"
                            Layout.fillWidth: true
                        }
                        UnavailableState {
                            theme: root.theme
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            eyebrow: "ENTRY LIST · UNAVAILABLE"
                            title: "控制器只提供统计数据"
                            detail: "自动缓存仍由现有 SQLite 路径管理；本工作台暂不浏览或改写记录。"
                        }
                        Text {
                            text: root.workbench.profileDirectory
                            color: root.theme.textDim
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 9
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                    }

                    PairEditor {
                        objectName: "correctionsEditor"
                        theme: root.theme
                        initialEntries: root.workbench.correctionEntries
                        initialDirty: root.workbench.correctionsDirty
                        revisionKey: root.workbench.currentProfileId + ":" + root.workbench.profileRevision
                        sourceTitle: "识别原文"
                        targetTitle: "人工译文"
                        saveText: "保存人工修订"
                        enabled: root.workbench.hasProfile
                        onDraftChanged: entries => root.workbench.setCorrectionsDraft(entries)
                        onSaveRequested: entries => root.workbench.saveCorrections(entries)
                    }
                }
            }
        }
    }
}
