using Cxx = import "/include/c++.capnp";
$Cxx.namespace("cereal");

@0xb526ba661d550a59;

# custom.capnp: a home for empty structs reserved for custom forks
# These structs are guaranteed to remain reserved and empty in mainline
# cereal, so use these if you want custom events in your fork.

# DO rename the structs
# DON'T change the identifier (e.g. @0x81c2f05a394cf4af)

struct ControlsStateExt @0x81c2f05a394cf4af {
  # dp - ALKA: two states, deliberately. alkaActive is "steering right now" and gates the
  # UI path drawing; alkaArmed is "the driver switched ALKA on" and is what soundd chimes
  # for. Chiming on active meant every stop light below dp_lat_alka_min_speed, and every
  # shift to reverse, played the enable/disable pair.
  alkaActive @0 :Bool;
  alkaArmed @1 :Bool;
}

struct CarStateExt @0xaedffd8f31e7b55d {
  # dp - ALKA: lkasOn state from carstate (mirrors panda's lkas_on)
  lkasOn @0 :Bool;
}

struct ModelExt @0xf35cc4560bbf6ec2 {
  leftEdgeDetected @0 :Bool;
  rightEdgeDetected @1 :Bool;
}

struct DashyState @0xda96579883444c35 {
  # Pre-serialized JSON bytes for dashy UI
  # Aggregates all topics needed by dashy into single message
  json @0 :Data;
}

struct LiveGPS @0x80ae746ee2596b11 {
  # Position
  latitude @0 :Float64;                # degrees
  longitude @1 :Float64;               # degrees
  altitude @2 :Float64;                # meters (WGS84)

  # Motion
  speed @3 :Float32;                   # m/s (horizontal speed)
  bearingDeg @4 :Float32;              # degrees (heading)

  # Accuracy
  horizontalAccuracy @5 :Float32;      # meters
  verticalAccuracy @6 :Float32;        # meters

  # Status
  gpsOK @7 :Bool;                      # livePose valid + GPS fresh
  status @8 :Status;

  enum Status {
    uninitialized @0;    # no GPS data yet
    uncalibrated @1;     # has GPS but fusion not ready (raw passthrough)
    valid @2;            # fusion active with calibrated bearing
  }

  # Metadata
  unixTimestampMillis @9 :Int64;
  lastGpsTimestamp @10 :UInt64;        # logMonoTime of last GPS

  # livePose health (for debugging fusion issues)
  livePoseOk @11 :Bool;                # livePose valid and providing orientation/velocity
}

struct CustomReserved5 @0xa5cd762cd951a455 {
}

struct CustomReserved6 @0xf98d843bfd7004a3 {
}

struct CustomReserved7 @0xb86e6369214c01c8 {
}

struct CustomReserved8 @0xf416ec09499d9d19 {
}

struct CustomReserved9 @0xa1680744031fdb2d {
}

struct CustomReserved10 @0xcb9fd56c7057593a {
}

struct CustomReserved11 @0xc2243c65e0340384 {
}

struct CustomReserved12 @0x9ccdc8676701b412 {
}

struct CustomReserved13 @0xcd96dafb67a082d0 {
}

struct CustomReserved14 @0xb057204d7deadf3f {
}

struct CustomReserved15 @0xbd443b539493bc68 {
}

struct CustomReserved16 @0xfc6241ed8877b611 {
}

struct CustomReserved17 @0xa30662f84033036c {
}

struct CustomReserved18 @0xc86a3d38d13eb3ef {
}

struct CustomReserved19 @0xa4f1eb3323f5f582 {
}
