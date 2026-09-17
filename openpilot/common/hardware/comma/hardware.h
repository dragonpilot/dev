#pragma once

#include <cassert>
#include <fstream>
#include <map>
#include <string>
#include <algorithm>  // for std::clamp

#include "common/util.h"
#include "common/swaglog.h"
#include "common/hardware/base.h"

class HardwareComma : public HardwareNone {
public:
  static std::string get_name() {
    static const std::string name = []() {
      std::string model = util::read_file("/sys/firmware/devicetree/base/model");
      return util::strip(model.substr(std::string("comma ").size()));
    }();
    return name;
  }

  static cereal::InitData::DeviceType get_device_type() {
    static const std::map<std::string, cereal::InitData::DeviceType> device_map = {
      // dp - upstream dropped tici from this map in 0.11.2 but kept it everywhere else:
      // hardware.py:113/392, soundd.py:33, amplifier.py:144 and log.capnp's `tici @4`.
      // comma three is still supported here, and 3X-class clones report "comma tici".
      {"tici", cereal::InitData::DeviceType::TICI},
      {"tizi", cereal::InitData::DeviceType::TIZI},
      {"mici", cereal::InitData::DeviceType::MICI}
    };
    static const cereal::InitData::DeviceType type = []() {
      auto it = device_map.find(get_name());
      if (it == device_map.end()) {
        // dp - assert is live in every build (NDEBUG is never set), so an unrecognised
        // model killed pandad outright. A third-party device can report anything.
        LOGE("unknown device model '%s', reporting unknown", get_name().c_str());
        return cereal::InitData::DeviceType::UNKNOWN;
      }
      return it->second;
    }();
    return type;
  }

  static std::string get_serial() {
    static std::string serial("");
    if (serial.empty()) {
      std::ifstream stream("/proc/cmdline");
      std::string cmdline;
      std::getline(stream, cmdline);

      auto start = cmdline.find("serialno=");
      if (start == std::string::npos) {
        serial = "cccccc";
      } else {
        auto end = cmdline.find(" ", start + 9);
        serial = cmdline.substr(start + 9, end - start - 9);
      }
    }
    return serial;
  }

  static void set_ir_power(int percent) {
    auto device = get_device_type();
    // dp - 0.11.1 skipped TICI here too. Upstream dropped that arm in 0.11.2 only
    // because removing tici from device_map made it unreachable, not because comma
    // three gained IR LEDs at these paths. We put tici back, so the arm comes back
    // with it; hardware.py:113 still skips both.
    if (device == cereal::InitData::DeviceType::TICI ||
        device == cereal::InitData::DeviceType::TIZI) {
      return;
    }

    int value = util::map_val(std::clamp(percent, 0, 100), 0, 100, 0, 300);
    std::ofstream("/sys/class/leds/led:switch_2/brightness") << 0 << "\n";
    std::ofstream("/sys/class/leds/led:torch_2/brightness") << value << "\n";
    std::ofstream("/sys/class/leds/led:switch_2/brightness") << value << "\n";
  }

  static std::map<std::string, std::string> get_init_logs(bool route_log = false) {
    std::map<std::string, std::string> ret = {
      {"/BUILD", util::read_file("/BUILD")},
      {"lsblk", util::check_output("lsblk -o NAME,SIZE,STATE,VENDOR,MODEL,REV,SERIAL")},
      {"SOM ID", util::read_file("/sys/devices/platform/vendor/vendor:gpio-som-id/som_id")},
    };

    std::string bs = util::check_output("abctl --boot_slot");
    ret["boot slot"] = bs.substr(0, bs.find_first_of("\n"));

    std::string temp = util::read_file("/dev/disk/by-partlabel/ssd");
    temp.erase(temp.find_last_not_of(std::string("\0\r\n", 3))+1);
    ret["boot temp"] = temp;

    // TODO: these are too slow to do on route log inits. need to do it async?
    if (!route_log) {
      for (std::string part : {"xbl", "abl", "aop", "devcfg", "xbl_config"}) {
        for (std::string slot : {"a", "b"}) {
          std::string partition = part + "_" + slot;
          std::string hash = util::check_output("sha256sum /dev/disk/by-partlabel/" + partition);
          ret[partition] = hash.substr(0, hash.find_first_of(" "));
        }
      }
    }

    return ret;
  }
};
