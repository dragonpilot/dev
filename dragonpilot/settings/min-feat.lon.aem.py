from dragonpilot.settings import tr

ITEMS = [
  {
    "section": "Longitudinal",
    "key": "dp_lon_aem",
    "needs_restart": True,
    "type": "toggle_item",
    "title": lambda: tr("Adaptive Experimental Mode (AEM)"),
    "description": lambda: tr("Adaptive mode switcher between ACC and Blended based on driving context."),
    "condition": "openpilotLongitudinalControl",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
    "lon_param": True,
  },
]
