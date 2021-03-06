# Copyright (c) 2017-2018 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
# AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
Tests senders
"""

import json

from django.test import TestCase
from mock import patch

from consent_manager import settings
from hgw_common.messaging.sender import KafkaSender, UnknownSender, create_sender
from hgw_common.utils import create_broker_parameters_from_settings


class TestSenders(TestCase):
    """
    Test senders class
    """

    def test_raise_unknown_sender(self):
        """
        Tests that, when the sender is unknown the factory function raises an error
        """
        self.assertRaises(UnknownSender, create_sender, {'broker_type': 'unknown'})

    @patch('hgw_common.messaging.sender.KafkaProducer')
    def test_get_kafka_sender(self, mocked_kafka_producer):
        """
        Tests that, when the settings specifies a kafka sender, the instantiated sender is Kafkasender
        """
        sender = create_sender(create_broker_parameters_from_settings())
        self.assertIsInstance(sender, KafkaSender)


class TestKafkaSender(TestCase):
    """
    Class the tests kafka sender
    """

    def test_fail_kafka_producer_connection(self):
        """
        Tests that, if the kafka broker is not accessible, the send method raises an exception
        """
        sender = create_sender(create_broker_parameters_from_settings())
        self.assertFalse(sender.send(settings.KAFKA_NOTIFICATION_TOPIC, {'message': 'fake_message'}))

    @patch('hgw_common.messaging.sender.KafkaProducer')
    def test_fail_json_encoding_error(self, mocked_kafka_producer):
        """
        Tests that, if the json encoding fails the send method raises an exception
        """
        sender = create_sender(create_broker_parameters_from_settings())
        self.assertFalse(sender.send(settings.KAFKA_NOTIFICATION_TOPIC, {"wrong_object"}))

    @patch('hgw_common.messaging.sender.KafkaProducer')
    def test_correct_send(self, mocked_kafka_producer):
        """
        Tests that, if the json encoding fails the send method raises an exception
        """
        sender = create_sender(create_broker_parameters_from_settings())
        message = {'message': 'text'}
        self.assertTrue(sender.send(settings.KAFKA_NOTIFICATION_TOPIC, message))
        self.assertEqual(mocked_kafka_producer().send.call_args_list[0][0][0], settings.KAFKA_NOTIFICATION_TOPIC)
        self.assertDictEqual(json.loads(mocked_kafka_producer().send.call_args_list[0][1]['value'].decode('utf-8')), message)
