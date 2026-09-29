#pragma once
#include <cstdint>
#include <random>
#include <string>

struct Telemetry {
    std::string event_id, machine_id, run_id, state;
    std::uint64_t sequence;
    std::int64_t timestamp_ms;
    double temperature, pressure, vibration, power, flow_rate, cycle_time;
    int error_code;
    double edge_vibration_mean = 0;
    bool edge_anomaly = false;
    std::string json() const;
};

class Machine {
    int index_;
    std::uint64_t tick_ = 0;
    std::string run_;
    std::mt19937 rng_;
    std::normal_distribution<double> noise_{0, 1};
public:
    Machine(int index, unsigned seed, std::string run): index_(index), run_(std::move(run)), rng_(seed + index) {}
    Telemetry sample();
};
