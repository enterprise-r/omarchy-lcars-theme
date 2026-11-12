import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// Zero-width decoration. Geometry is applied after layout: mapToItem is not
// a binding, and the row's anchors move it once its width has already settled.
BarWidget {
  id: root
  readonly property bool lcars: Color.background.toString() === "#0c040f"
  // A transparent bar samples the wallpaper and, on a bright field, switches
  // its ink to the near-black contrast color. This plate is opaque and would
  // otherwise be that same black under the dark ink. Match the ink: bright
  // silver when it is dark, the theme background when it is light. Keep the
  // sample in a color property; a var copy does not expose hslLightness.
  readonly property color ink: bar ? bar.barForeground : "#00000000"
  readonly property bool darkInk: bar && bar.transparent === true && ink.a > 0.5 && ink.hslLightness < 0.45
  readonly property color plateColor: darkInk ? "#d5dce3" : Color.background
  // Clear bars leave the wallpaper showing. Opaque and glassy bars paint a
  // full strip; that strip uses this same plate color.
  readonly property bool fullBar: bar && bar.transparent === false
  readonly property var hostWindow: root.QsWindow.window
  // The section row, once the widget host chain has settled.
  property Item hostRow: null
  // The bar window spans the screen. This is the strip that actually holds
  // the controls, a direct child of the window.
  property Item barStrip: null

  function findStrip() {
    var window = root.hostWindow
    if (!window || !window.contentItem) return null
    var item = root
    var guard = 0
    while (item && item.parent && item.parent !== window.contentItem && guard++ < 16)
      item = item.parent
    if (!item || item.parent !== window.contentItem) return null
    var cross = root.vertical ? item.width : item.height
    var thickness = Math.max(1, root.barSize)
    if (cross < 1 || cross > thickness * 4) return null
    return item
  }

  function isSlot(child) {
    return !!(child && child.width >= 1
      && child.moduleName !== undefined && child.moduleName !== null
      && String(child.moduleName) !== "")
  }

  // Delegates are siblings of the repeater, or its children, depending on
  // the Qt Quick version. Count either shape.
  function slotCount(item) {
    if (!item || !item.children) return 0
    var slots = 0
    for (var i = 0; i < item.children.length; i++) {
      var child = item.children[i]
      if (root.isSlot(child)) slots++
      else if (child && child.children) {
        for (var j = 0; j < child.children.length; j++)
          if (root.isSlot(child.children[j])) slots++
      }
    }
    return slots
  }

  function slotsOf(row) {
    var found = []
    if (!row || !row.children) return found
    for (var i = 0; i < row.children.length; i++) {
      var child = row.children[i]
      if (root.isSlot(child)) found.push(child)
      else if (child && child.children) {
        for (var j = 0; j < child.children.length; j++)
          if (root.isSlot(child.children[j])) found.push(child.children[j])
      }
    }
    return found
  }

  // BarWidget, loader, widget host, holder, widget area, slot, then the row.
  // The host was inserted in front of the slot, so a fixed three-step walk
  // no longer reaches the section.
  function findRow() {
    var item = root.parent
    var guard = 0
    while (item && guard++ < 16) {
      if (root.slotCount(item) >= 1) return item
      if (root.barStrip && item.parent === root.barStrip) break
      item = item.parent
    }
    return null
  }

  // The content item inside the strip, above the stock background and behind
  // the widgets. Parenting onto the strip itself would put the plate under
  // that background, so a drawn bar would keep the stock color.
  function findSurface(row) {
    var strip = root.barStrip
    if (!strip) return null
    var item = row || root
    var guard = 0
    while (item && item.parent && item !== strip && guard++ < 16) {
      if (item.width >= strip.width - 1 && item.height >= strip.height - 1)
        return item
      item = item.parent
    }
    return null
  }

  function track() {
    var strip = root.findStrip()
    if (root.barStrip !== strip) root.barStrip = strip
    var row = root.findRow()
    if (root.hostRow !== row) root.hostRow = row
    root.place()
  }

  implicitWidth: 0
  implicitHeight: barSize

  function place() {
    var row = root.hostRow
    var surface = root.findSurface(row)
    if (!surface || !root.lcars || root.vertical) {
      plateRect.width = 0
      return
    }
    var h = root.fullBar ? surface.height : root.barSize - 2
    if (h < 1) {
      plateRect.width = 0
      return
    }
    if (root.fullBar) {
      plateRect.parent = surface
      plateRect.x = 0
      plateRect.y = 0
      plateRect.width = surface.width
      plateRect.height = h
      plateRect.radius = 0
      return
    }
    if (!row) {
      plateRect.width = 0
      return
    }
    var left = Infinity
    var slots = root.slotsOf(row)
    for (var i = 0; i < slots.length; i++) {
      var child = slots[i]
      if (!child || child.height < 1) continue
      // The tray sits to the left of the capsule. An empty tray collapses
      // and drops out of this measurement on its own.
      if (child.moduleName === "omarchy.tray") continue
      var origin = child.mapToItem(surface, 0, 0)
      if (origin.x < left) left = origin.x
    }
    if (left === Infinity) {
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
    plateRect.radius = 12
  }

  onParentChanged: root.track()
  onHostWindowChanged: root.track()
  onBarChanged: Qt.callLater(root.track)
  onFullBarChanged: Qt.callLater(root.place)
  Component.onCompleted: Qt.callLater(root.track)
  // place() reparents the plate onto the bar. Drop that copy on the way out
  // so a reload cannot leave the old plate behind.
  Component.onDestruction: if (plateRect && plateRect.parent !== root) plateRect.destroy()

  Connections {
    target: root.hostRow
    function onChildrenRectChanged() { Qt.callLater(root.place) }
    function onWidthChanged() { Qt.callLater(root.place) }
    function onHeightChanged() { Qt.callLater(root.place) }
  }

  Connections {
    target: root.bar
    function onTransparentChanged() { Qt.callLater(root.place) }
  }

  // Widgets such as the tray report their width a moment after the row exists.
  Timer {
    interval: 200
    repeat: true
    running: root.lcars
    triggeredOnStart: true
    property int ticks: 0
    onTriggered: {
      root.track()
      ticks++
      if (ticks >= 10) interval = 1000
      if (ticks >= 16 && root.barStrip !== null && root.hostRow !== null) running = false
      if (ticks >= 30) running = false
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
