import json
import os
import pytest
import unittest
from db_plugins.db.generic import new_DBConnection
from db_plugins.db.mongo import MongoDatabaseCreator
from mongo_scribe.step import MongoScribe
from apf.producers.kafka import KafkaProducer

DB_CONFIG = {
    "MONGO": {
        "HOST": "localhost",
        "USERNAME": "mongo",
        "PASSWORD": "mongo",
        "PORT": 27017,
        "DATABASE": "test",
    }
}

CONSUMER_CONFIG = {
    "CLASS": "apf.consumers.KafkaConsumer",
    "TOPICS": ["test_topic"],
    "PARAMS": {
        "bootstrap.servers": "localhost:9092",
        "group.id": "command_consumer_2",
        "enable.partition.eof": True,
        "auto.offset.reset": "beginning",
    },
    "NUM_MESSAGES": 2,
    "TIMEOUT": 10
}

PRODUCER_CONFIG = {
    "TOPIC": "test_topic",
    "PARAMS": {"bootstrap.servers": "localhost:9092"},
    "SCHEMA": {
        "namespace": "db_operation",
        "type": "record",
        "name": "Command",
        "fields": [
            {"name": "payload", "type": "string"},
        ],
    },
}


@pytest.mark.usefixtures("mongo_service")
@pytest.mark.usefixtures("kafka_service")
class MongoIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = new_DBConnection(MongoDatabaseCreator)
        step_config = {
            "DB_CONFIG": DB_CONFIG,
            "CONSUMER_CONFIG": CONSUMER_CONFIG,
            "STEP_METADATA": {
                "STEP_ID": "scribe",
                "STEP_NAME": "scribe",
                "STEP_VERSION": "test",
                "STEP_COMMENTS": "test ver.",
            },
        }
        cls.db.connect(DB_CONFIG["MONGO"])
        cls.db.create_db()
        cls.step = MongoScribe(config=step_config)
        cls.producer = KafkaProducer(config=PRODUCER_CONFIG)

    def tearDown(self):
        object_collection = self.db.database["object"]
        object_collection.delete_many({})
        object_detection = self.db.database["detection"]
        object_detection.delete_many({})

    def test_insert_into_database(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "insert",
                "data": {"_id": "inserted_id1", "field": "some_value"},
            }
        )
        self.producer.produce({"payload": command})
        command = json.dumps(
            {
                "collection": "object",
                "type": "insert",
                "data": {"_id": "inserted_id2", "field": "some_value"},
            }
        )
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        result = collection.find_one({"_id": "inserted_id1"})
        assert result is not None
        assert result["field"] == "some_value"

    def test_insert_into_multiple_collections(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "insert",
                "data": {"_id": "inserted_id10", "field": "some_value"},
            }
        )
        self.producer.produce({"payload": command})
        command = json.dumps(
            {
                "collection": "detection",
                "type": "insert",
                "data": {"_id": "inserted_id2", "field": "some_value2"},
            }
        )
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        detection_coll = self.step.db_client.connection.database["detection"]
        result = collection.find_one({"_id": "inserted_id10"})
        assert result is not None
        assert result["field"] == "some_value"
        result_detection = detection_coll.find_one({"_id": "inserted_id2"})
        assert result_detection is not None
        assert result_detection["field"] == "some_value2"

    def test_upsert_into_database(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "update",
                "criteria": {"_id": "upserted_id"},
                "data": {"field": "some_value"},
                "options": {"upsert": True},
            }
        )
        self.producer.produce({"payload": command})
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        result = collection.find_one({"_id": "upserted_id"})
        assert result is not None
        assert result["field"] == "some_value"

    def test_upsert_only_into_database(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "update",
                "criteria": {"_id": "upserted_only_id"},
                "data": {"field": "some_value"},
                "options": {"upsert": True, "set_on_insert": True},
            }
        )
        self.producer.produce({"payload": command})
        command = json.dumps(
            {
                "collection": "object",
                "type": "update",
                "criteria": {"_id": "upserted_only_id"},
                "data": {"field": "other_value"},
                "options": {"upsert": True, "set_on_insert": True},
            }
        )
        self.producer.produce({"payload": command})
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        result = collection.find_one({"_id": "upserted_only_id"})
        assert result is not None
        assert result["field"] == "some_value"

    def test_insert_probabilities_into_database(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "update_probabilities",
                "criteria": {"_id": "insert_probabilities_id"},
                "data": {
                    "class1": 0.1,
                    "class2": 0.9,
                    "classifier_name": "classifier",
                    "classifier_version": "1",
                },
                "options": {"upsert": True, "set_on_insert": True},
            }
        )
        self.producer.produce({"payload": command})
        command = json.dumps(
            {
                "collection": "object",
                "type": "update_probabilities",
                "criteria": {"_id": "insert_probabilities_id"},
                "data": {
                    "class1": 0.5,
                    "class2": 0.3,
                    "classifier_name": "classifier",
                    "classifier_version": "1",
                },
                "options": {"upsert": True, "set_on_insert": True},
            }
        )
        self.producer.produce({"payload": command})
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        result = collection.find_one({"_id": "insert_probabilities_id"})
        assert result is not None
        assert {
            "classifier_name": "classifier",
            "classifier_version": "1",
            "probability": 0.1,
            "class_name": "class1",
            "ranking": 2,
        } in result["probabilities"]

        assert {
            "classifier_name": "classifier",
            "classifier_version": "1",
            "probability": 0.9,
            "class_name": "class2",
            "ranking": 1,
        } in result["probabilities"]

    def test_update_probabilities_into_database(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "update_probabilities",
                "criteria": {"_id": "update_probabilities_id"},
                "data": {
                    "class1": 0.1,
                    "class2": 0.9,
                    "classifier_name": "classifier",
                    "classifier_version": "1",
                },
                "options": {"upsert": True},
            }
        )
        self.producer.produce({"payload": command})
        command = json.dumps(
            {
                "collection": "object",
                "type": "update_probabilities",
                "criteria": {"_id": "update_probabilities_id"},
                "data": {
                    "class1": 0.5,
                    "class2": 0.3,
                    "classifier_name": "classifier",
                    "classifier_version": "1",
                },
                "options": {"upsert": True},
            }
        )
        self.producer.produce({"payload": command})
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        result = collection.find_one({"_id": "update_probabilities_id"})
        assert result is not None
        assert {
            "classifier_name": "classifier",
            "classifier_version": "1",
            "probability": 0.5,
            "class_name": "class1",
            "ranking": 1,
        } in result["probabilities"]

        assert {
            "classifier_name": "classifier",
            "classifier_version": "1",
            "probability": 0.3,
            "class_name": "class2",
            "ranking": 2,
        } in result["probabilities"]

    def test_update_features_into_database(self):
        command = json.dumps(
            {
                "collection": "object",
                "type": "update_features",
                "criteria": {"_id": "update_features_id"},
                "data": {
                    "features_version": "v1",
                    "features_group": "elasticc",
                    "features": [
                        {"name": "feat1", "value": 123, "fid": 'g'},
                        {"name": "feat2", "value": 456, "fid": 'Y'},
                    ],
                },
                "options": {"upsert": True},
            }
        )
        self.producer.produce({"payload": command})
        command = json.dumps(
            {
                "collection": "object",
                "type": "update_features",
                "criteria": {"_id": "update_features_id"},
                "data": {
                    "features_version": "v1",
                    "features_group": "elasticc",
                    "features": [
                        {"name": "feat1", "value": 741, "fid": 'g'},
                        {"name": "feat2", "value": 369, "fid": 'Y'},
                    ],
                },
                "options": {"upsert": True},
            }
        )
        self.producer.produce({"payload": command})
        self.producer.produce({"payload": command})

        command = json.dumps({
            "collection": "object",
            "type": "update_features",
            "criteria": {"_id": "update_features_id"},
            "data": {
                "features_version": "v1",
                "features_group": "elasticc",
                "features": [
                    {"name": "feat1", "value": 741, "fid": 'g'},
                    {"name": "feat2", "value": 369, "fid": 'Y'},
                ],
            },
            "options": {"upsert": True},
        })
        self.producer.produce({"payload": command})

        self.step.start()
        collection = self.step.db_client.connection.database["object"]
        result = collection.find_one({"_id": "update_features_id"})
        assert result is not None
        assert "elasticc" in result["features"]
        assert {
                   "name": "feat1",
                   "value": 741,
                   "fid": "g",
               } in result["features"]["elasticc"]["features"]

    def test_print_into_console(self):
        os.environ["MOCK_DB_COLLECTION"] = "True"
        commands = [
            json.dumps(
                {
                    "collection": "object",
                    "type": "insert",
                    "data": {"_id": "some printed value"},
                }
            ),
            json.dumps(
                {
                    "collection": "object",
                    "type": "update",
                    "criteria": {"_id": "some printed value"},
                    "data": {"field2": "hehe"},
                }
            ),
        ]
        self.producer.produce({"payload": commands[0]})
        self.producer.produce({"payload": commands[1]})
        self.step.start()

        os.environ["MOCK_DB_COLLECTION"] = ""
        collection = self.step.db_client.connection.database["object"]
        result = collection.find({"_id": "some printed value"})
        assert len(list(result)) == 0
