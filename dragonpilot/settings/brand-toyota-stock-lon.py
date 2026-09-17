from dragonpilot.settings import tr

ITEMS = [
  {
    "section": "Toyota / Lexus",
    "key": "dp_toyota_stock_lon",
    "needs_restart": True,
    "type": "toggle_item",
    "title": lambda: tr("Use Stock Longitudinal Control"),
    "description": lambda: tr("Let the car's built-in ACC handle gas and brake instead of openpilot. Lateral control (steering) still runs through openpilot."),
    "brands": ["toyota"],
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
    "car_param": True,
  },
]
