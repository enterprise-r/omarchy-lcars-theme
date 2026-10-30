import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// Zero-width decoration under the right-hand modules. Geometry is applied
// after layout: mapToItem is not a binding, and the row's anchors move it
// once its width has already settled.
BarWidget {
  id: root
  readonly property bool lcars: Color.background.toString() === "#0e0012"
  // A transparent bar samples the wallpaper and, on a bright field, switches
  // its ink to the near-black contrast color. This plate is opaque and would
  // otherwise be that same black under the dark ink. Match the ink: bright
  // silver when it is dark, the theme background when it is light. Keep the
  // sample in a color property; a var copy does not expose hslLightness.
  readonly property color ink: bar ? bar.barForeground : "#00000000"
  readonly property bool darkInk: bar && bar.transparent === true && ink.a > 0.5 && ink.hslLightness < 0.45
  readonly property color plateColor: darkInk ? "#c8cdd2" : Color.background
  readonly property var hostWindow: root.QsWindow.window
  // Loader, then the module slot, then the row for this section.
  readonly property Item hostRow: {
    var loader = root.parent
    var slot = loader ? loader.parent : null
    return slot ? slot.parent : null
  }
  // The bar item that spans this monitor.
  readonly property Item barSurface: {
    var window = root.hostWindow
    var limit = window && window.contentItem ? window.contentItem.width : 0
    var item = root.hostRow
    while (item && limit > 0 && item.width < limit - 1 && item.parent && item.parent !== window.contentItem)
      item = item.parent
    return item
  }

  implicitWidth: 0
  implicitHeight: barSize

  function place() {
    var row = root.hostRow
    var surface = root.barSurface
    if (!row || !surface || !root.lcars || root.vertical) {
      plateRect.width = 0
      return
    }
    var left = Infinity
    var right = -Infinity
    for (var i = 0; i < row.children.length; i++) {
      var child = row.children[i]
      if (!child || child.width < 1 || child.height < 1) continue
      // The tray sits to the left of the capsule. An empty tray collapses
      // and drops out of this measurement on its own.
      if (child.moduleName === "omarchy.tray") continue
      var origin = child.mapToItem(surface, 0, 0)
      if (origin.x < left) left = origin.x
      var end = origin.x + child.width
      if (end > right) right = end
    }
    if (left === Infinity || right <= left) {
      plateRect.width = 0
      return
    }
    // Menu, workspace, and clock capsules are barSize - 2, flush with the
    // top of the bar. This row is vertically centered, so a taller slot
    // shifts every module upward and a plate that follows them ends short
    // of those capsules.
    var h = root.barSize - 2
    if (h < 1) {
      plateRect.width = 0
      return
    }
    plateRect.parent = surface
    plateRect.x = left
    plateRect.y = 0
    // RightModules keeps a space(8) margin. The plate continues through it
    // to the screen edge; the modules themselves stay where they are.
    plateRect.width = Math.max(0, surface.width - left)
    plateRect.height = h
  }

  onBarSurfaceChanged: Qt.callLater(root.place)
  Component.onCompleted: Qt.callLater(root.place)
  // place() reparents the plate onto the bar. Drop that copy on the way out
  // so a reload cannot leave the old plate behind.
  Component.onDestruction: if (plateRect && plateRect.parent !== root) plateRect.destroy()

  Connections {
    target: root.hostRow
    function onChildrenRectChanged() { Qt.callLater(root.place) }
    function onWidthChanged() { Qt.callLater(root.place) }
    function onHeightChanged() { Qt.callLater(root.place) }
  }

  // Widgets such as the tray report their width a moment after the row exists.
  Timer {
    interval: 200
    repeat: true
    running: root.lcars && root.hostRow !== null
    triggeredOnStart: true
    property int ticks: 0
    onTriggered: {
      root.place()
      ticks++
      if (ticks >= 10) interval = 1000
      if (ticks >= 16) running = false
    }
  }

  Rectangle {
    id: plateRect
    z: -1
    visible: root.lcars && !root.vertical && width > 0
    radius: 12
    color: root.plateColor
  }
}
