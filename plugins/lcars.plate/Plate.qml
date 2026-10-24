import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// Zero-width decoration under the right-hand modules. Geometry is applied
// after layout: mapToItem is not a binding, and the row's anchors move it
// once its width has already settled.
BarWidget {
  id: root
  readonly property bool lcars: Color.background.toString() === "#08090c"
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
    var top = 0
    var slotHeight = 0
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
      top = origin.y
      slotHeight = child.height
    }
    if (left === Infinity || right <= left || slotHeight < 1) {
      plateRect.width = 0
      return
    }
    var h = Math.max(0, slotHeight - 2)
    plateRect.parent = surface
    plateRect.x = left
    plateRect.y = top
    plateRect.width = right - left
    plateRect.height = h
  }

  onBarSurfaceChanged: Qt.callLater(root.place)
  Component.onCompleted: Qt.callLater(root.place)

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
    color: "#181820"
  }
}
