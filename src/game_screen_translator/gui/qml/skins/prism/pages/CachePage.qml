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
    property bool correctionsExpanded: false
    signal visualAction(string action)

    Flickable {
        id: pageScroll
        objectName: root.theme.active ? "cachePageScroll" : ""
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: pageColumn.implicitHeight + 4
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: PrismScrollBar { id: pageScrollBar; theme: root.theme }

        ColumnLayout {
            id: pageColumn
            width: pageScroll.width - pageScrollBar.contentInset
            spacing: root.height <= 560 ? 8 : 10

            Text {
                objectName: root.theme.active ? "cacheCumulativeLabel" : ""
                text: "PROFILE  /  累计统计"
                color: root.theme.textDim
                font.family: root.theme.monoFontFor(text)
                font.pixelSize: 11
                font.letterSpacing: 1.1
                Layout.fillWidth: true
            }

            RowLayout {
                objectName: root.theme.active ? "cacheSummaryStrip" : ""
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                spacing: 8
                visible: root.workbench.hasProfile

                Repeater {
                    model: [
                        {"label": "模型缓存", "value": root.workbench.automaticEntries, "tone": root.theme.accentText},
                        {"label": "缓存命中", "value": root.workbench.automaticHits, "tone": root.theme.violet},
                        {"label": "人工修订", "value": root.workbench.manualCorrections,
                         "tone": root.theme.refraLight ? "#B00079" : root.theme.spectrum},
                        {"label": "修订命中", "value": root.workbench.manualHits, "tone": root.theme.amber}
                    ]

                    Item {
                        objectName: root.theme.active ? ("cacheMetric-" + index) : ""
                        required property int index
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.preferredWidth: 1
                        implicitHeight: 48

                        Rectangle {
                            width: 2
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.left: parent.left
                            color: modelData.tone
                            opacity: 0.9
                        }
                        ColumnLayout {
                            anchors.left: parent.left
                            anchors.leftMargin: 10
                            anchors.right: parent.right
                            anchors.rightMargin: 5
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 1
                            Text {
                                objectName: root.theme.active ? ("cacheMetricValue-" + index) : ""
                                text: String(modelData.value)
                                color: modelData.tone
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 22
                                font.weight: Font.DemiBold
                                fontSizeMode: Text.Fit
                                minimumPixelSize: 12
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                            }
                            Text {
                                text: modelData.label
                                color: root.theme.textSoft
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 12
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                        Rectangle {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: 1
                            color: root.theme.line
                            opacity: 0.8
                        }
                    }
                }

                PrismButton {
                    objectName: root.theme.active ? "cacheRefreshStatsButton" : ""
                    theme: root.theme
                    text: "刷新统计"
                    enabled: root.workbench.hasProfile
                    Layout.minimumWidth: 104
                    Layout.preferredWidth: 116
                    Layout.maximumWidth: 126
                    onClicked: {
                        root.workbench.refreshStats()
                        root.visualAction("ripple")
                    }
                }
            }

            Rectangle {
                objectName: root.theme.active ? "cacheNoProfileState" : ""
                visible: !root.workbench.hasProfile
                Layout.fillWidth: true
                implicitHeight: Math.max(74, noProfileContent.implicitHeight + 24)
                color: root.theme.glass
                border.color: root.theme.line
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10
                    Rectangle {
                        Layout.fillHeight: true
                        Layout.preferredWidth: 3
                        color: root.theme.accent
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        id: noProfileContent
                        spacing: 3
                        Text {
                            objectName: root.theme.active ? "cacheNoProfileEyebrow" : ""
                            text: "CACHE · UNAVAILABLE"
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 11
                            font.letterSpacing: 1
                        }
                        Text {
                            objectName: root.theme.active ? "cacheNoProfileTitle" : ""
                            text: "尚未选择 Profile"
                            color: root.theme.text
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 17
                            font.weight: Font.DemiBold
                        }
                        Text {
                            id: noProfileDetail
                            text: "没有真实缓存统计来源；请先在 HOME 创建或选择一个 Profile。"
                            color: root.theme.textSoft
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Text {
                    text: "上次运行命中"
                    color: root.theme.text
                    font.family: root.theme.displayFontFor(text)
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    Layout.minimumWidth: 0
                }
                PrismFoldRule {
                    theme: root.theme
                    Layout.fillWidth: true
                }
                Text {
                    text: "TOP 5"
                    color: root.theme.accentText
                    font.family: root.theme.monoFontFor(text)
                    font.pixelSize: 11
                    font.letterSpacing: 1
                }
            }

            Text {
                objectName: root.theme.active ? "cacheRunScopeNote" : ""
                text: "仅代表最近一次运行，不含 Profile 累计统计。"
                color: root.theme.textDim
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            ColumnLayout {
                objectName: root.theme.active ? "cacheLastRunList" : ""
                visible: root.workbench.hasProfile
                         && root.workbench.lastRunAvailable
                         && root.workbench.lastRunCacheHits.length > 0
                Layout.fillWidth: true
                spacing: 6

                Repeater {
                    model: root.workbench.lastRunCacheHits
                    Rectangle {
                        required property int index
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: Math.max(48, hitSource.implicitHeight + 16)
                        color: index % 2 === 0 ? root.theme.glass : "transparent"
                        border.color: root.theme.line
                        border.width: 1

                        Rectangle {
                            width: 3
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            color: root.theme.accent
                            opacity: 0.68
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            anchors.topMargin: 7
                            anchors.bottomMargin: 7
                            spacing: 12

                            Text {
                                text: String(index + 1).padStart(2, "0")
                                color: root.theme.textDim
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 12
                                Layout.preferredWidth: 25
                                verticalAlignment: Text.AlignVCenter
                            }
                            Text {
                                id: hitSource
                                objectName: root.theme.active ? ("cacheHitSource-" + index) : ""
                                text: String(modelData.sourceText)
                                color: root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 14
                                wrapMode: Text.Wrap
                                elide: Text.ElideNone
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                            }
                            Text {
                                objectName: root.theme.active ? ("cacheHitCount-" + index) : ""
                                text: String(modelData.hits) + " 次"
                                color: root.theme.accentText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 14
                                fontSizeMode: Text.Fit
                                minimumPixelSize: 12
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                                Layout.preferredWidth: Math.min(parent.width * 0.4, Math.max(72, implicitWidth))
                                Layout.minimumWidth: Math.min(64, parent.width * 0.4)
                                Layout.maximumWidth: parent.width * 0.4
                            }
                        }
                    }
                }
            }

            Rectangle {
                objectName: root.theme.active ? "cacheLastRunEmpty" : ""
                visible: root.workbench.hasProfile
                         && (!root.workbench.lastRunAvailable
                             || root.workbench.lastRunCacheHits.length === 0)
                Layout.fillWidth: true
                implicitHeight: Math.max(64, cacheEmptyContent.implicitHeight + 24)
                color: root.theme.glass
                border.color: root.theme.line

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10
                    Rectangle {
                        Layout.fillHeight: true
                        Layout.preferredWidth: 3
                        color: root.theme.accent
                        opacity: 0.75
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        id: cacheEmptyContent
                        spacing: 2
                        Text {
                            text: root.workbench.lastRunAvailable
                                  ? "LAST RUN CACHE · EMPTY"
                                  : "LAST RUN CACHE · UNAVAILABLE"
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 11
                            font.letterSpacing: 1
                        }
                        Text {
                            text: root.workbench.lastRunAvailable
                                  ? "上次运行无自动缓存命中"
                                  : "尚无上次运行结果"
                            color: root.theme.text
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        Text {
                            id: cacheEmptyDetail
                            text: root.workbench.lastRunAvailable
                                  ? "当前上次运行快照没有记录自动缓存命中。"
                                  : root.workbench.lastRunStatus
                            color: root.theme.textSoft
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            PrismPanel {
                objectName: root.theme.active ? "cacheCorrectionsPanel" : ""
                theme: root.theme
                padding: 12
                rightPadding: 12
                motionRole: "primary"
                transitionSerial: root.transitionSerial
                motionEnabled: root.pageMotionEnabled && root.visible
                Layout.fillWidth: true
                Layout.preferredHeight: root.correctionsExpanded ? 340 : 92
                Layout.minimumHeight: root.correctionsExpanded ? 340 : 92
                Layout.maximumHeight: root.correctionsExpanded ? 340 : 92

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 7

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: "人工修订"
                            color: root.theme.text
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 17
                            font.weight: Font.DemiBold
                        }
                        Text {
                            objectName: root.theme.active ? "cacheSavedCorrectionCount" : ""
                            text: String(root.workbench.manualCorrections) + " 条已保存"
                            color: root.theme.textDim
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 11
                        }
                        Item { Layout.fillWidth: true }
                        PrismButton {
                            objectName: root.theme.active ? "cacheCorrectionsExpandButton" : ""
                            theme: root.theme
                            text: root.correctionsExpanded ? "收起" : "展开 / 添加"
                            enabled: root.workbench.hasProfile
                            Layout.minimumWidth: 112
                            onClicked: root.correctionsExpanded = !root.correctionsExpanded
                        }
                    }

                    Text {
                        objectName: root.theme.active ? "cacheCorrectionsCollapsedNote" : ""
                        visible: !root.correctionsExpanded
                        text: root.workbench.correctionsDirty
                              ? "有尚未保存的更改。"
                              : root.workbench.manualCorrections === 0
                                ? "当前没有已保存修订；添加原文和译文后保存。"
                                : "展开以查看和编辑已保存修订。"
                        color: root.workbench.correctionsDirty ? root.theme.amber : root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    PairEditor {
                        id: correctionEditor
                        objectName: root.theme.active ? "correctionsEditor" : ""
                        theme: root.theme
                        visible: root.correctionsExpanded
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.correctionsExpanded ? 236 : 0
                        Layout.minimumHeight: root.correctionsExpanded ? 236 : 0
                        Layout.maximumHeight: root.correctionsExpanded ? 236 : 0
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
}
