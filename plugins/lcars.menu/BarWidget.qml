import QtQuick
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "omarchy.menu"
  readonly property bool lcars: Color.background.toString() === "#08090c"
  // LeftModules already insets the group by space(8). Pull the pill left so
  // the screen-edge gap matches the gap before the next control.
  readonly property int sideGap: Style.space(3)
  readonly property int leftPull: Style.space(8) - sideGap

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    anchors.leftMargin: root.lcars ? -root.leftPull : 0
    anchors.rightMargin: root.lcars ? root.sideGap : 0
    bar: root.bar
    text: "\ue900"
    fontFamily: "omarchy"
    fontSize: root.lcars ? 18 : Style.font.body
    foreground: root.lcars ? "#08090c" : (root.bar ? root.bar.barForeground : Color.foreground)
    fixedWidth: root.lcars ? Style.space(32) - root.leftPull + root.sideGap : -1
    // The stock label centers on the full button, below this shorter pill.
    // The glyph also leans right in its em box.
    labelVisible: !root.lcars
    Rectangle {
      id: pill
      visible: root.lcars
      z: -1
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      height: parent.height - 2
      radius: 12
      color: button.tooltipHovered ? "#98c5a3" : "#efb18b"
    }
    Text {
      visible: root.lcars
      anchors.centerIn: pill
      anchors.horizontalCenterOffset: -0.5
      text: "\ue900"
      color: button.foreground
      font.family: "omarchy"
      font.pixelSize: button.fontSize
      renderType: Text.NativeRendering
    }
    horizontalMargin: 7.5
    onPressed: function(button) {
      if (!root.bar) return
      if (button === Qt.RightButton) root.bar.run("xdg-terminal-exec")
      else root.bar.run("omarchy-shell shell toggle omarchy.menu '{\"menu\":\"root\"}'")
    }
  }
}
