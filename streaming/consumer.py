import argparse
import json
import logging
import os
import sys
from digital_twin.state_manager import StateManager


def process(store, payload):
    try:
        store.ingest(json.loads(payload))
    except (ValueError, TypeError) as exc:
        store.reject(payload, str(exc))
        logging.warning("Invalid event persisted to rejected table: %s", exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdin", action="store_true", help="Consume simulator JSONL without Kafka")
    parser.add_argument("--db", default=os.getenv("FABTWIN_DB", "data/fabtwin.db"))
    parser.add_argument("--brokers", default=os.getenv("KAFKA_BROKERS", "localhost:9092"))
    args = parser.parse_args()
    store = StateManager(args.db)
    if args.stdin:
        for line in sys.stdin:
            if line.strip():
                process(store, line)
        return
    from confluent_kafka import Consumer
    consumer = Consumer({"bootstrap.servers": args.brokers, "group.id": "fabtwin-twins-v1", "auto.offset.reset": "earliest", "enable.auto.commit": False})
    consumer.subscribe(["fabtwin.telemetry"])
    try:
        while True:
            message = consumer.poll(1)
            if message is None:
                continue
            if message.error():
                logging.error("Kafka: %s", message.error())
                continue
            process(store, message.value().decode("utf-8", errors="replace"))
            # Commit only after SQLite commit; replay is harmless via event uniqueness.
            consumer.commit(message=message, asynchronous=False)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
