#include "Machine.h"
#include <chrono>
#include <iomanip>
#include <sstream>

Telemetry Machine::sample() {
    // 240 operating ticks per episode. Offset devices to avoid identical phases.
    auto phase = (tick_ + index_ * 17) % 240;
    std::string state = phase < 10 ? "IDLE" : phase < 110 ? "RUNNING" : phase < 190 ? "DEGRADING" : phase < 210 ? "FAULT" : "MAINTENANCE";
    // Later episodes restart directly in RUNNING after maintenance.
    if (tick_ + index_ * 17 >= 240 && phase < 10) state = "RUNNING";
    double degradation = state == "DEGRADING" ? (phase - 110) / 80.0 : state == "FAULT" ? 1.0 : 0.0;
    bool active = state == "RUNNING" || state == "DEGRADING" || state == "FAULT";
    const char* types[] = {"ETCHER", "DEPOSITION", "INSPECTION", "CLEANER"};
    std::string id = std::string(types[index_ % 4]) + "_" + std::to_string(index_ + 1);
    auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    auto sequence = tick_++;
    return {run_ + ":" + id + ":" + std::to_string(sequence), id, run_, state, sequence, timestamp,
        (active ? 70 : 35) + 22 * degradation + noise_(rng_) * 0.7,
        4.2 - 0.6 * degradation + noise_(rng_) * (0.025 + degradation * 0.16),
        (active ? 0.2 : 0.025) + 0.45 * degradation + noise_(rng_) * 0.006,
        (active ? 238 : 25) + 65 * degradation + noise_(rng_) * 2,
        (active ? 12.7 : 1) - 2 * degradation + noise_(rng_) * 0.1,
        30 + degradation * 12 + noise_(rng_) * 0.2, state == "FAULT" ? 101 : 0};
}

std::string Telemetry::json() const {
    std::ostringstream s;
    s << std::setprecision(10) << "{\"event_id\":\"" << event_id << "\",\"machine_id\":\"" << machine_id
      << "\",\"run_id\":\"" << run_id << "\",\"state\":\"" << state << "\",\"sequence\":" << sequence
      << ",\"timestamp_ms\":" << timestamp_ms << ",\"temperature\":" << temperature << ",\"pressure\":" << pressure
      << ",\"vibration\":" << vibration << ",\"power\":" << power << ",\"flow_rate\":" << flow_rate
      << ",\"cycle_time\":" << cycle_time << ",\"error_code\":" << error_code
      << ",\"edge_vibration_mean\":" << edge_vibration_mean << ",\"edge_anomaly\":" << (edge_anomaly ? "true" : "false") << "}";
    return s.str();
}
