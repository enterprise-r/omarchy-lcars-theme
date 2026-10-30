import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  readonly property bool lcars: Color.background.toString() === "#0e0012"
  readonly property var hostWindow: root.QsWindow.window
  // The layout entry loads this decoration but occupies no bar space.
  implicitWidth: 0
  implicitHeight: barSize
  property real elapsed: 0

  Timer {
    interval: 50
    running: field.visible && root.hostWindow !== null && root.hostWindow.visible
    repeat: true
    onTriggered: root.elapsed += 0.05
  }

  Item {
    id: field
    // Paint into this monitor's existing bar surface, below every control.
    // No extra layer surface, input handler, or replacement bar is needed.
    parent: root.hostWindow ? root.hostWindow.contentItem : root
    anchors.fill: parent
    z: -10
    clip: true
    visible: root.lcars && !root.vertical && root.visible && root.hostWindow !== null

    // Distant points provide depth between the occasional approaching streaks.
    Repeater {
      model: root.lcars ? 9 : 0
      Rectangle {
        required property int index
        x: ((index * 0.6180339 + 0.17) % 1) * field.width
        y: 3 + (index * 13) % Math.max(1, field.height - 6)
        width: 1
        height: 1
        radius: 0.5
        color: "#c8cdd2"
        opacity: 0.14 + (index % 3) * 0.025
      }
    }

    Repeater {
      model: root.lcars ? 16 : 0
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
        readonly property color headColor: index % 4 === 0 ? "#c8cdd2" : "#e4eafa"
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
