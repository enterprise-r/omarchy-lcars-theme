-- LCARS geometry stays with this theme; switching themes restores defaults.
-- Window opacity and blur are left to Omarchy's Glassy toggle.
-- Colors follow Dark-R: cyan marks the active window (the space in view),
-- the slate --ui-border the others, as in colors.toml.
local active_border_color = "rgba(96c5cfff)"
local inactive_border_color = "rgba(3f2c53ff)"

hl.config({
  general = {
    gaps_in = 4,
    gaps_out = 8,
    border_size = 1,
    col = {
      active_border = active_border_color,
      inactive_border = inactive_border_color,
    },
  },
  decoration = {
    rounding = 10,
    shadow = { enabled = false },
  },
  group = {
    col = {
      border_active = active_border_color,
      border_inactive = inactive_border_color,
    },
  },
})
