import QtQuick
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "omarchy.menu"
  readonly property bool lcars: Color.background.toString() === "#08090c"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.lcars ? "LCARS" : "\ue900"
    fontFamily: root.lcars ? "Nimbus Sans Narrow" : "omarchy"
    fontSize: root.lcars ? 16 : Style.font.body
    foreground: root.lcars ? "#08090c" : (root.bar ? root.bar.barForeground : Color.foreground)
    fixedWidth: root.lcars ? 82 : -1
    tooltipText: "Omarchy menu · right-click for terminal"
    Rectangle {
      visible: root.lcars
      z: -1
      anchors.centerIn: parent
      width: parent.width - 6
      height: parent.height - 8
      radius: height / 2
      color: button.tooltipHovered ? "#ffd1ad" : "#efb18b"
      Rectangle {
        x: 9
        width: 3
        height: parent.height
        color: "#08090c"
      }
    }
    horizontalMargin: 7.5
    onPressed: function(button) {
      if (!root.bar) return
      if (button === Qt.RightButton) root.bar.run("xdg-terminal-exec")
      else root.bar.run("omarchy-shell shell toggle omarchy.menu '{\"menu\":\"root\"}'")
    }
  }
}
