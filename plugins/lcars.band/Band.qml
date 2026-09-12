import QtQuick
import qs.Commons
import qs.Ui

// Structural LCARS endcap; no click target or simulated telemetry.
BarWidget {
  id: root
  readonly property bool lcars: Color.background.toString() === "#08090c"
  implicitWidth: lcars ? Style.space(Number(setting("size", 38))) : 0
  implicitHeight: barSize
  Rectangle {
    visible: root.lcars
    anchors.centerIn: parent
    width: Math.max(0, parent.width - 6)
    height: parent.height - 8
    topLeftRadius: root.setting("end", "left") === "left" ? height / 2 : 1
    bottomLeftRadius: topLeftRadius
    topRightRadius: root.setting("end", "left") === "right" ? height / 2 : 1
    bottomRightRadius: topRightRadius
    color: root.setting("color", "#efb18b")
  }
}
