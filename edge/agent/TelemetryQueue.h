#pragma once
#include <condition_variable>
#include <deque>
#include <mutex>
#include <stdexcept>

// Blocking bounded FIFO: exhaustion applies backpressure, never silently drops.
template<class T> class TelemetryQueue {
    std::mutex mutex_;
    std::condition_variable readable_, writable_;
    std::deque<T> queue_;
    const size_t capacity_;
    bool closed_ = false;
public:
    explicit TelemetryQueue(size_t capacity): capacity_(capacity) {
        if (!capacity) throw std::invalid_argument("queue capacity must be positive");
    }
    bool push(T value) {
        std::unique_lock<std::mutex> lock(mutex_);
        writable_.wait(lock, [&]{ return closed_ || queue_.size() < capacity_; });
        if (closed_) return false;
        queue_.push_back(std::move(value));
        readable_.notify_one();
        return true;
    }
    bool pop(T& value) {
        std::unique_lock<std::mutex> lock(mutex_);
        readable_.wait(lock, [&]{ return closed_ || !queue_.empty(); });
        if (queue_.empty()) return false;
        value = std::move(queue_.front()); queue_.pop_front();
        writable_.notify_one();
        return true;
    }
    void close() {
        std::lock_guard<std::mutex> lock(mutex_); closed_ = true;
        readable_.notify_all(); writable_.notify_all();
    }
};
