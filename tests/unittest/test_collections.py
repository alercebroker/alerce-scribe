import unittest
from unittest.mock import patch
from mongo_scribe.db.models import ScribeCollectionMock, ScribeCollectionMongo

class CollectionTest(unittest.TestCase):
    @patch("builtins.print")
    def test_mock_collection(self, mock_print):
        collection = ScribeCollectionMock("object")
        collection.insert_many([])
        mock_print.assert_called_with("Inserting into object:")

        collection.bulk_write([])
        mock_print.assert_called_with("Bulk writing into object:")

    @patch("db_plugins.db.mongo.MongoConnection")
    @patch("pymongo.collection.Collection")
    def test_mongo_collection(self, mock_collection, mock_connection):
        scribe_collection = ScribeCollectionMongo(mock_connection, "object")
        scribe_collection.collection = mock_collection

        scribe_collection.insert_many([{}])
        mock_collection.insert_many.assert_called()

        scribe_collection.bulk_write([{}])
        mock_collection.bulk_write.assert_called()