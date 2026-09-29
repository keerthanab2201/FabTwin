#pragma once
#include "simulator/Machine.h"
#include <chrono>
#include <memory>
#include <string>

class NetworkClient {
    struct Impl;
    std::unique_ptr<Impl> impl_;
    std::chrono::steady_clock::time_point started_ = std::chrono::steady_clock::now();
    int outage_ms_;
    bool first_publish_ = true;
public:
    NetworkClient(std::string brokers, int outage_ms);
    ~NetworkClient();
    bool publish(const Telemetry& event);
};
