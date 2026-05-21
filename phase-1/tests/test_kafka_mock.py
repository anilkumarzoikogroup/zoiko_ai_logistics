"""Tests for Kafka producer, consumer, and mock broker."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from kafka.mock_kafka import MockKafkaBroker
from kafka.producer import ZoikoProducer, KafkaMessage, REGISTERED_TOPICS
from kafka.consumer import ZoikoConsumer


TENANT_ID = "tenant-abc-123"


@pytest.fixture
def broker():
    return MockKafkaBroker()

@pytest.fixture
def producer(broker):
    return ZoikoProducer(broker)

@pytest.fixture
def consumer(broker):
    return ZoikoConsumer(broker, group_id="test-group")


class TestMockKafkaBroker:

    def test_send_and_count(self, broker):
        broker.send("zoiko.source.record.received", key=b"k1", value=b"v1")
        assert broker.message_count("zoiko.source.record.received") == 1

    def test_poll_returns_unread_messages(self, broker):
        broker.send("zoiko.case.opened", key=b"k", value=b"v")
        result = broker.poll(group_id="grp-a")
        assert "zoiko.case.opened" in result
        assert len(result["zoiko.case.opened"]) == 1

    def test_poll_advances_offset(self, broker):
        broker.send("zoiko.case.opened", key=b"k", value=b"v")
        broker.poll(group_id="grp-a")
        result2 = broker.poll(group_id="grp-a")
        assert "zoiko.case.opened" not in result2

    def test_different_groups_independent_offsets(self, broker):
        broker.send("zoiko.finding.generated", key=b"k", value=b"v")
        r1 = broker.poll(group_id="grp-1")
        r2 = broker.poll(group_id="grp-2")
        assert "zoiko.finding.generated" in r1
        assert "zoiko.finding.generated" in r2

    def test_reset_clears_all(self, broker):
        broker.send("zoiko.acr.generated", key=b"k", value=b"v")
        broker.reset()
        assert broker.message_count("zoiko.acr.generated") == 0


class TestKafkaMessage:

    def test_valid_message_serializes(self):
        msg = KafkaMessage(
            topic     = "zoiko.source.record.received",
            key       = "case-001",
            payload   = {"invoice_number": "DHL-001", "total": 220.0},
            tenant_id = TENANT_ID,
        )
        body = json.loads(msg.to_bytes())
        assert body["tenant_id"] == TENANT_ID
        assert body["payload"]["total"] == 220.0

    def test_unregistered_topic_raises(self):
        with pytest.raises(ValueError, match="Unknown topic"):
            KafkaMessage(topic="nonexistent.topic", key="k", payload={}, tenant_id=TENANT_ID)

    def test_all_17_topics_are_registered(self):
        assert len(REGISTERED_TOPICS) == 17

    def test_headers_include_tenant_and_idempotency(self):
        msg     = KafkaMessage(topic="zoiko.case.closed", key="k", payload={}, tenant_id=TENANT_ID)
        headers = dict(msg.headers())
        assert headers["tenant_id"].decode() == TENANT_ID
        assert "idempotency_key" in headers


class TestZoikoProducer:

    def test_publish_stores_in_broker(self, producer, broker):
        msg = KafkaMessage(topic="zoiko.case.opened", key="case-001", payload={"state": "NEW"}, tenant_id=TENANT_ID)
        producer.publish(msg)
        assert broker.message_count("zoiko.case.opened") == 1

    def test_publish_batch(self, producer, broker):
        msgs = [
            KafkaMessage(topic="zoiko.source.record.received", key=f"inv-{i}", payload={}, tenant_id=TENANT_ID)
            for i in range(3)
        ]
        producer.publish_batch(msgs)
        assert broker.message_count("zoiko.source.record.received") == 3


class TestZoikoConsumer:

    def test_subscribe_and_poll(self, producer, consumer, broker):
        received = []
        consumer.subscribe("zoiko.case.opened", lambda tid, payload: received.append((tid, payload)))

        msg = KafkaMessage(topic="zoiko.case.opened", key="k", payload={"state": "NEW"}, tenant_id=TENANT_ID)
        producer.publish(msg)
        count = consumer.poll()
        assert count == 1
        assert received[0][0] == TENANT_ID
        assert received[0][1]["state"] == "NEW"

    def test_unsubscribed_topic_ignored(self, producer, consumer, broker):
        received = []
        consumer.subscribe("zoiko.case.closed", lambda t, p: received.append(p))

        msg = KafkaMessage(topic="zoiko.source.record.received", key="k", payload={}, tenant_id=TENANT_ID)
        producer.publish(msg)
        consumer.poll()
        assert len(received) == 0
