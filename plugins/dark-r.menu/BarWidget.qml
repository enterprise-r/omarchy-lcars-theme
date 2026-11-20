import QtQuick
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "omarchy.menu"
  readonly property bool darkR: Color.background.toString() === "#0c040f"
  // LeftModules insets the group by space(8). Cancel that so the pill meets
  // the screen edge. sideGap stays between this pill and the next control.
  readonly property int sideGap: Style.space(3)
  readonly property int edgeInset: Style.space(8)

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    anchors.leftMargin: root.darkR ? -root.edgeInset : 0
    anchors.rightMargin: root.darkR ? root.sideGap : 0
    bar: root.bar
    text: "\ue900"
    fontFamily: "omarchy"
    fontSize: root.darkR ? 18 : Style.font.body
    foreground: root.darkR ? "#0c040f" : (root.bar ? root.bar.barForeground : Color.foreground)
    fixedWidth: root.darkR ? Style.space(32) - root.edgeInset + root.sideGap * 2 : -1
    // The stock label centers on the full button, below this shorter pill.
    // The glyph also leans right in its em box.
    labelVisible: !root.darkR
    Rectangle {
      id: pill
      visible: root.darkR
      z: -1
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      height: parent.height - 2
      // Same curve as the window corners. Style.cornerRadius tracks
      // Hyprland's decoration:rounding.
      radius: Style.cornerRadius
      color: "#77af8a"
    }
    Text {
      visible: root.darkR
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
