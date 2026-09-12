-- LCARS geometry stays with this theme; switching themes restores defaults.
hl.config({
  general = {
    gaps_in = 4,
    gaps_out = 8,
    border_size = 1,
    col = {
      active_border = "rgba(b4a0dfff)",
      inactive_border = "rgba(393344ff)",
    },
  },
  decoration = {
    rounding = 10,
    active_opacity = 0.97,
    inactive_opacity = 0.94,
    shadow = { enabled = false },
    blur = { enabled = false },
  },
  group = {
    col = {
      border_active = "rgba(b4a0dfff)",
      border_inactive = "rgba(393344ff)",
    },
  },
})
