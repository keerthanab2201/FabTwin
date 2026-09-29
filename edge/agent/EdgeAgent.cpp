#include "EdgeAgent.h"
#include <cmath>
#include <deque>
#include <iostream>
#include <map>
#include <numeric>
#include <thread>
#include <exception>

EdgeAgent::EdgeAgent(Options options): options_(options), raw_(options.capacity), processed_(options.capacity), network_(options.brokers, options.outage_ms) {
    std::random_device rd;
    auto run = std::to_string(std::chrono::system_clock::now().time_since_epoch().count()) + "-" + std::to_string(rd());
    for (int i = 0; i < options.machines; ++i) machines_.emplace_back(i, options.seed, run);
}
void EdgeAgent::run() {
    auto started = std::chrono::steady_clock::now();
    std::exception_ptr failure;
    std::mutex failure_mutex;
    auto guard = [&](auto work) {
        try { work(); } catch (...) {
            { std::lock_guard<std::mutex> lock(failure_mutex); if (!failure) failure = std::current_exception(); }
            raw_.close(); processed_.close();
        }
    };
    std::thread collect([&]{ guard([&]{
        for (int tick = 0; options_.ticks == 0 || tick < options_.ticks; ++tick) {
            for (auto& machine: machines_) {
                if (!raw_.push(machine.sample())) return;
                ++generated_;
            }
            if (options_.interval_ms) std::this_thread::sleep_for(std::chrono::milliseconds(options_.interval_ms));
        }
        raw_.close();
    }); });
    std::thread preprocess([&]{ guard([&]{
        std::map<std::string, std::deque<double>> windows;
        Telemetry event;
        while (raw_.pop(event)) {
            if (!std::isfinite(event.temperature) || !std::isfinite(event.vibration) || !std::isfinite(event.pressure) ||
                !std::isfinite(event.power) || !std::isfinite(event.flow_rate) || !std::isfinite(event.cycle_time) ||
                event.temperature < -50 || event.temperature > 300 || event.vibration < 0 || event.pressure <= 0) {
                ++rejected_; continue;
            }
            auto& window = windows[event.machine_id];
            window.push_back(event.vibration); if (window.size() > 30) window.pop_front();
            event.edge_vibration_mean = std::accumulate(window.begin(), window.end(), 0.0) / window.size();
            event.edge_anomaly = event.edge_vibration_mean > 0.35 || event.temperature > 82;
            if (!processed_.push(std::move(event))) return;
        }
        processed_.close();
    }); });
    std::thread publish([&]{ guard([&]{
        Telemetry event;
        while (processed_.pop(event)) {
            while (!network_.publish(event)) { ++retries_; std::this_thread::sleep_for(std::chrono::milliseconds(10)); }
            ++published_;
        }
    }); });
    collect.join(); preprocess.join(); publish.join();
    if (failure) std::rethrow_exception(failure);
    auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    std::cerr << "{\"generated\":" << generated_ << ",\"published\":" << published_
              << ",\"rejected\":" << rejected_ << ",\"retry_attempts\":" << retries_
              << ",\"elapsed_seconds\":" << elapsed << "}\n";
}
