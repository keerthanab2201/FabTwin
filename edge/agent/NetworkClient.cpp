#include "NetworkClient.h"
#include <iostream>
#include <stdexcept>
#ifdef WITH_KAFKA
#include <librdkafka/rdkafka.h>
#endif

struct NetworkClient::Impl {
#ifdef WITH_KAFKA
    rd_kafka_t* producer = nullptr;
    bool delivered = false, failed = false;
    static void delivered_cb(rd_kafka_t*, const rd_kafka_message_t* msg, void* opaque) {
        auto* self = static_cast<Impl*>(opaque);
        self->failed = msg->err != RD_KAFKA_RESP_ERR_NO_ERROR;
        self->delivered = true;
    }
#endif
};
NetworkClient::NetworkClient(std::string brokers, int outage_ms): impl_(new Impl), outage_ms_(outage_ms) {
    if (brokers.empty()) return;
#ifdef WITH_KAFKA
    auto* conf = rd_kafka_conf_new();
    char error[512];
    auto set = [&](const char* key, const char* value) {
        if (rd_kafka_conf_set(conf, key, value, error, sizeof(error)) != RD_KAFKA_CONF_OK)
            throw std::runtime_error(error);
    };
    set("bootstrap.servers", brokers.c_str()); set("enable.idempotence", "true");
    set("message.timeout.ms", "10000"); set("acks", "all");
    rd_kafka_conf_set_opaque(conf, impl_.get());
    rd_kafka_conf_set_dr_msg_cb(conf, Impl::delivered_cb);
    impl_->producer = rd_kafka_new(RD_KAFKA_PRODUCER, conf, error, sizeof(error));
    if (!impl_->producer) throw std::runtime_error(error);
#else
    throw std::runtime_error("Kafka requires a WITH_KAFKA build; omit --brokers for JSONL output");
#endif
}
NetworkClient::~NetworkClient() {
#ifdef WITH_KAFKA
    if (impl_->producer) rd_kafka_destroy(impl_->producer);
#endif
}
bool NetworkClient::publish(const Telemetry& event) {
    if (first_publish_) {
        started_ = std::chrono::steady_clock::now();
        first_publish_ = false;
    }
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started_).count();
    if (elapsed < outage_ms_) return false;
    auto payload = event.json();
#ifdef WITH_KAFKA
    if (impl_->producer) {
        impl_->delivered = false;
        auto err = rd_kafka_producev(impl_->producer, RD_KAFKA_V_TOPIC("fabtwin.telemetry"),
            RD_KAFKA_V_MSGFLAGS(RD_KAFKA_MSG_F_COPY), RD_KAFKA_V_VALUE(const_cast<char*>(payload.data()), payload.size()),
            RD_KAFKA_V_KEY(const_cast<char*>(event.machine_id.data()), event.machine_id.size()), RD_KAFKA_V_END);
        if (err) return false;
        // Keep the FIFO head until the broker acknowledges it; conservative ordered delivery.
        while (!impl_->delivered) rd_kafka_poll(impl_->producer, 100);
        return !impl_->failed;
    }
#endif
    std::cout << payload << '\n' << std::flush;
    if (!std::cout) throw std::runtime_error("telemetry output failed");
    return true;
}
