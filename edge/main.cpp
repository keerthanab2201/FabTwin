#include "agent/EdgeAgent.h"
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) {
    try {
        Options o;
        for (int i = 1; i < argc; ++i) {
            std::string key = argv[i];
            if (key == "--help") {
                std::cout << "--machines 24 --ticks 0 (continuous) --interval-ms 1000 --capacity 65536 --outage-ms 0 --seed 42 --brokers kafka:9092\n";
                return 0;
            }
            if (++i >= argc) throw std::invalid_argument("missing argument");
            std::string value = argv[i];
            if (key == "--brokers") o.brokers = value;
            else if (key == "--machines") o.machines = std::stoi(value);
            else if (key == "--ticks") o.ticks = std::stoi(value);
            else if (key == "--interval-ms") o.interval_ms = std::stoi(value);
            else if (key == "--outage-ms") o.outage_ms = std::stoi(value);
            else if (key == "--capacity") { int n = std::stoi(value); if (n <= 0) throw std::invalid_argument("invalid capacity"); o.capacity = n; }
            else if (key == "--seed") o.seed = std::stoul(value);
            else throw std::invalid_argument("unknown option: " + key);
        }
        if (o.machines < 1 || o.ticks < 0 || o.interval_ms < 0 || o.outage_ms < 0) throw std::invalid_argument("invalid options");
        EdgeAgent(o).run();
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
