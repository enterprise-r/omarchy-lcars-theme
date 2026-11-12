import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  readonly property bool lcars: Color.background.toString() === "#0c040f"
  readonly property var hostWindow: root.QsWindow.window
  // The layout entry loads this decoration but occupies no bar space.
  implicitWidth: 0
  implicitHeight: barSize
  property real elapsed: 0
  // Off until a right-click. The choice used to be an install flag.
  readonly property bool shown: setting("shown", false) === true
  readonly property string starsId: moduleName !== "" ? moduleName : "lcars.stars"
  // Plugin widgets see a facade, not the bar. Hiding parks the surface
  // off-screen and leaves the window visible, so this is the stop signal.
  readonly property bool barParked: {
    var shell = root.bar ? root.bar.shell : null
    var state = shell ? shell.bar : null
    return !!(state && state.barHidden === true)
  }
  readonly property bool animating: root.lcars && root.shown && !root.vertical
      && root.visible && !root.barParked
      && root.barStrip !== null && root.hostWindow !== null && root.hostWindow.visible

  // The bar window now spans the whole screen and stays clear past the
  // strip. Parenting into the window paints the trails across the desktop.
  property Item barStrip: null

  function findStrip() {
    var window = root.hostWindow
    if (!window || !window.contentItem) return null
    var item = root
    var guard = 0
    while (item && item.parent && item.parent !== window.contentItem && guard++ < 16)
      item = item.parent
    if (!item || item.parent !== window.contentItem) return null
    // Reject the screen-sized surface. The strip is only about as thick
    // as the bar, plus a notch floor on some panels.
    var cross = root.vertical ? item.width : item.height
    var thickness = Math.max(1, root.barSize)
    if (cross < 1 || cross > thickness * 4) return null
    return item
  }

  function trackStrip() {
    var next = root.findStrip()
    if (root.barStrip !== next) root.barStrip = next
  }

  function toggleStars() {
    var entry = { id: root.starsId }
    for (var key in root.settings) if (key !== "id") entry[key] = root.settings[key]
    entry.shown = !root.shown
    root.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.starsId, entry)
  }

  onParentChanged: root.trackStrip()
  onHostWindowChanged: root.trackStrip()
  Component.onCompleted: Qt.callLater(root.trackStrip)

  Timer {
    interval: 200
    repeat: true
    running: root.lcars && root.barStrip === null
    triggeredOnStart: true
    property int ticks: 0
    onTriggered: {
      root.trackStrip()
      ticks++
      if (ticks >= 20) running = false
    }
  }

  Timer {
    interval: 50
    running: root.animating
    repeat: true
    onTriggered: root.elapsed += 0.05
  }

  // The field and the click catcher are reparented onto the bar strip.
  // Drop them on the way out so a reload cannot leave a trail field behind.
  Component.onDestruction: {
    if (toggleArea && toggleArea.parent !== root) toggleArea.destroy()
    if (field && field.parent !== root) field.destroy()
  }

  // Behind the controls. Widgets that use the right button keep it; a
  // right-click on the rest of the bar shows or hides the trails.
  MouseArea {
    id: toggleArea
    parent: root.barStrip ? root.barStrip : root
    anchors.fill: parent
    z: -9
    enabled: root.lcars && !root.vertical && root.barStrip !== null
    acceptedButtons: Qt.RightButton
    onClicked: root.toggleStars()
  }

  Item {
    id: field
    // Paint into this monitor's bar strip, below every control.
    parent: root.barStrip ? root.barStrip : root
    anchors.fill: parent
    z: -10
    clip: true
    visible: root.animating

    // Distant points provide depth between the occasional approaching streaks.
    Repeater {
      model: root.animating ? 9 : 0
      Rectangle {
        required property int index
        x: ((index * 0.6180339 + 0.17) % 1) * field.width
        y: 3 + (index * 13) % Math.max(1, field.height - 6)
        width: 1
        height: 1
        radius: 0.5
        color: "#cfdae6"
        opacity: 0.14 + (index % 3) * 0.025
      }
    }

    Repeater {
      model: root.animating ? 16 : 0
      Item {
        id: star
        required property int index
        // Exponential projection: slow distant points gain speed and length.
        readonly property real phase: (index * 0.6180339 + root.elapsed / (55 + (index % 5) * 5)) % 1
        readonly property real depth: (Math.exp(phase * 2.2) - 1) / (Math.exp(2.2) - 1)
        readonly property real direction: index % 2 === 0 ? -1 : 1
        readonly property real rayX: direction * (field.width / 2 + 80)
        readonly property real rayY: ((index * 7) % 23 - 11) * (field.height / 32)
        readonly property real trailLength: 1 + Math.pow(depth, 1.4) * (index % 5 === 0 ? 100 : 68)
        readonly property real thickness: 0.8 + depth * 0.55
        readonly property color headColor: index % 4 === 0 ? "#cedceb" : "#e4eafa"
        readonly property color tailColor: index % 7 === 0 ? "#ba7c79" : "#929dbf"
        // The true vanishing point sits at the centered STARDATE clock.
        x: field.width / 2 + rayX * depth
        y: field.height / 2 + rayY * depth
        rotation: Math.atan2(rayY, rayX) * 180 / Math.PI
        transformOrigin: Item.TopLeft
        width: 0
        height: 0
        opacity: (0.12 + Math.sqrt(depth) * 0.42) * Math.min(1, phase * 14) * Math.min(1, (1 - phase) * 22)

        Rectangle {
          x: -star.trailLength
          y: -star.thickness / 2
          width: star.trailLength
          height: star.thickness
          radius: height / 2
          gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 0.42; color: star.tailColor }
            GradientStop { position: 1; color: star.headColor }
          }
        }
      }
    }
  }
}
