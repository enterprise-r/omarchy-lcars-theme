import QtQuick
import qs.Commons
import qs.Ui

// Structural Dark-R endcap; no click target or simulated telemetry.
BarWidget {
  id: root
  readonly property bool darkR: Color.background.toString() === "#0c040f"
  implicitWidth: darkR ? Style.space(Number(setting("size", 38))) : 0
  implicitHeight: barSize
  Rectangle {
    visible: root.darkR
    anchors.centerIn: parent
    width: Math.max(0, parent.width - 6)
    height: parent.height - 8
    topLeftRadius: root.setting("end", "left") === "left" ? height / 2 : 1
    bottomLeftRadius: topLeftRadius
    topRightRadius: root.setting("end", "left") === "right" ? height / 2 : 1
    bottomRightRadius: topRightRadius
    color: root.setting("color", "#f4b965")
  }
}
