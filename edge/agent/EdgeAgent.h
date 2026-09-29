#pragma once
#include "NetworkClient.h"
#include "TelemetryQueue.h"
#include <atomic>
#include <vector>

struct Options {
    int machines = 24, ticks = 0, interval_ms = 1000, outage_ms = 0;
    unsigned seed = 42;
    size_t capacity = 65536;
    std::string brokers;
};
class EdgeAgent {
    Options options_;
    TelemetryQueue<Telemetry> raw_, processed_;
    NetworkClient network_;
    std::vector<Machine> machines_;
    std::atomic<unsigned long long> generated_{0}, published_{0}, retries_{0}, rejected_{0};
public:
    explicit EdgeAgent(Options options);
    void run();
};
