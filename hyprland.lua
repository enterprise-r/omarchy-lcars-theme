-- LCARS geometry stays with this theme; switching themes restores defaults.
-- The stock window rule paints active windows at 98.5%. Match this theme instead.
o.window({ tag = "default-opacity" }, { opacity = "1 0.94" })

hl.config({
  general = {
    gaps_in = 4,
    gaps_out = 8,
    border_size = 1,
    col = {
      active_border = "rgba(a5ace1ff)",
      inactive_border = "rgba(393344ff)",
    },
  },
  decoration = {
    rounding = 10,
    active_opacity = 1.0,
    inactive_opacity = 0.94,
    shadow = { enabled = false },
    blur = { enabled = false },
  },
  group = {
    col = {
      border_active = "rgba(a5ace1ff)",
      border_inactive = "rgba(393344ff)",
    },
  },
})
