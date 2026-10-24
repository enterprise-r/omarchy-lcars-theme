import QtQuick
import QtQuick.Layouts
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.workspaces"
  readonly property bool lcars: Color.background.toString() === "#08090c"

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }

    return null
  }

  function workspaceIds() {
    var ids = [1, 2, 3, 4, 5]
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 0 && id <= 10 && ids.indexOf(id) === -1) ids.push(id)
    }

    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function focusWorkspace(id) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)

  implicitWidth: grid.implicitWidth + trailingGap
  implicitHeight: grid.implicitHeight

  GridLayout {
    id: grid
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap
    columns: root.vertical ? 1 : root.workspaceIds().length
    columnSpacing: root.vertical ? 0 : Style.space(root.lcars ? 3 : 1)
    rowSpacing: root.vertical ? Style.space(2) : 0

    Repeater {
      model: root.workspaceIds()

      WidgetButton {
        id: segment
        required property int modelData

        readonly property var workspace: root.workspaceById(modelData)
        readonly property bool occupied: workspace !== null && workspace.toplevels.values.length > 0
        readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData

        bar: root.bar
        text: root.lcars ? String(modelData).padStart(2, "0") : (focused ? "\uDB85\uDCFB" : (modelData === 10 ? "0" : String(modelData)))
        foreground: root.lcars ? "#08090c" : (root.bar ? root.bar.barForeground : Color.foreground)
        tooltipText: "Workspace " + modelData + (occupied ? " · " + workspace.toplevels.values.length + " windows" : " · empty")
        opacity: root.lcars ? 1 : (occupied || focused ? 1 : 0.5)
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.vertical ? root.barSize : Style.space(root.lcars ? 32 : 20)
        fixedHeight: root.barSize
        onPressed: function() { root.focusWorkspace(modelData) }
        Rectangle {
          visible: root.lcars
          z: -1
          anchors.horizontalCenter: parent.horizontalCenter
          anchors.top: parent.top
          width: parent.width
          height: parent.height - 2
          topLeftRadius: segment.modelData === 1 ? 12 : 2
          bottomLeftRadius: topLeftRadius
          topRightRadius: segment.modelData === root.workspaceIds()[root.workspaceIds().length - 1] ? 12 : 2
          bottomRightRadius: topRightRadius
          color: segment.focused ? "#f2ba64" : (segment.occupied ? "#a5ace1" : "#756986")
          border.width: (segment.tooltipHovered && !segment.focused) ? 1 : 0
          border.color: "#f2ba64"
          Behavior on color { ColorAnimation { duration: 120 } }
        }
      }
    }
  }
}
