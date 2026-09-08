import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var theme
    property var initialEntries: []
    property string revisionKey: ""
    property string sourceTitle: "原文"
    property string targetTitle: "译文"
    property string saveText: "保存"
    property bool initialDirty: false
    property bool dirty: false
    property string errorText: ""
    readonly property int entryCount: rows.count
    signal draftChanged(var entries)
    signal saveRequested(var entries)

    implicitHeight: 360

    function reload() {
        rows.clear()
        const source = root.initialEntries || []
        for (let index = 0; index < source.length; ++index) {
            rows.append({
                "source": String(source[index].source || ""),
                "target": String(source[index].target || ""),
                "selected": false
            })
        }
        root.dirty = root.initialDirty
        root.errorText = ""
    }

    function snapshot() {
        const result = []
        for (let index = 0; index < rows.count; ++index) {
            const row = rows.get(index)
            result.push({"source": String(row.source), "target": String(row.target)})
        }
        return result
    }

    function markDirty() {
        root.dirty = true
        root.errorText = ""
        root.draftChanged(root.snapshot())
    }

    function collect() {
        const result = []
        for (let index = 0; index < rows.count; ++index) {
            const row = rows.get(index)
            const source = String(row.source).trim()
            const target = String(row.target).trim()
            if ((source.length > 0) !== (target.length > 0)) {
                root.errorText = "原文和译文必须同时填写。"
                return null
            }
            if (source.length > 0)
                result.push({"source": source, "target": target})
        }
        root.errorText = ""
        return result
    }

    onRevisionKeyChanged: reload()
    onInitialDirtyChanged: {
        if (root.initialDirty)
            root.dirty = true
    }
    Component.onCompleted: reload()

    ListModel { id: rows }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Text {
                text: root.sourceTitle
                color: root.theme.textDim
                font.family: root.theme.monoFontFor(text)
                font.pixelSize: 10
                font.letterSpacing: 0.8
                Layout.fillWidth: true
            }
            Text {
                text: root.targetTitle
                color: root.theme.textDim
                font.family: root.theme.monoFontFor(text)
                font.pixelSize: 10
                font.letterSpacing: 0.8
                Layout.fillWidth: true
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"
            border.color: root.theme.line

            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: 1
                clip: true
                spacing: 1
                model: rows
                boundsBehavior: Flickable.StopAtBounds

                delegate: Rectangle {
                    id: rowItem
                    required property int index
                    required property string source
                    required property string target
                    required property bool selected

                    width: list.width
                    height: 54
                    color: selected
                           ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.08)
                           : index % 2 ? Qt.rgba(root.theme.text.r, root.theme.text.g, root.theme.text.b, 0.018) : "transparent"
                    border.color: selected ? root.theme.accent : "transparent"
                    focus: false
                    activeFocusOnTab: true

                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            rows.setProperty(index, "selected", !selected)
                            event.accepted = true
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            rowItem.forceActiveFocus()
                            rows.setProperty(rowItem.index, "selected", !rowItem.selected)
                        }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 8

                        Text {
                            text: String(rowItem.index + 1).padStart(2, "0")
                            color: rowItem.selected ? root.theme.accent : root.theme.textDim
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            Layout.preferredWidth: 24
                        }
                        PrismTextField {
                            objectName: "pairSourceField-" + String(rowItem.index)
                            theme: root.theme
                            z: 1
                            text: rowItem.source
                            accessibleName: root.sourceTitle + " " + String(rowItem.index + 1)
                            Layout.fillWidth: true
                            onTextEdited: {
                                rows.setProperty(rowItem.index, "source", text)
                                root.markDirty()
                            }
                        }
                        PrismTextField {
                            objectName: "pairTargetField-" + String(rowItem.index)
                            theme: root.theme
                            z: 1
                            text: rowItem.target
                            accessibleName: root.targetTitle + " " + String(rowItem.index + 1)
                            Layout.fillWidth: true
                            onTextEdited: {
                                rows.setProperty(rowItem.index, "target", text)
                                root.markDirty()
                            }
                        }
                    }
                }

                ScrollIndicator.vertical: ScrollIndicator { }
            }

            UnavailableState {
                anchors.fill: parent
                anchors.margins: 1
                theme: root.theme
                visible: rows.count === 0
                eyebrow: "EMPTY"
                title: "尚无条目"
                detail: "添加一行后填写原文和译文。"
            }
        }

        Text {
            visible: root.errorText.length > 0 || root.dirty
            text: root.errorText.length > 0 ? root.errorText : "有尚未保存的更改。"
            color: root.errorText.length > 0 ? root.theme.danger : root.theme.amber
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            PrismButton {
                objectName: "addPairRowButton"
                theme: root.theme
                text: "添加一行"
                onClicked: {
                    rows.append({"source": "", "target": "", "selected": false})
                    root.markDirty()
                }
            }
            PrismButton {
                theme: root.theme
                text: "删除选中行"
                onClicked: {
                    let removed = 0
                    for (let index = rows.count - 1; index >= 0; --index) {
                        if (rows.get(index).selected) {
                            rows.remove(index)
                            ++removed
                        }
                    }
                    if (removed === 0)
                        root.errorText = "请先选择需要删除的行。"
                    else {
                        root.markDirty()
                    }
                }
            }
            Item { Layout.fillWidth: true }
            PrismButton {
                theme: root.theme
                primary: true
                text: root.saveText
                onClicked: {
                    const value = root.collect()
                    if (value !== null)
                        root.saveRequested(value)
                }
            }
        }
    }
}
