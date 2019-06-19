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
import json
import logging
import os

from Cryptodome.PublicKey import RSA
from django.test import TestCase, client
from mock import patch

from hgw_common.cipher import Cipher
from hgw_common.utils.mocks import (MockKafkaConsumer, MockMessage,
                                    get_free_port, start_mock_server)
from hgw_frontend.models import (ConsentConfirmation, Destination, FlowRequest,
                                 RESTClient)
from . import CORRECT_CONFIRM_ID, SOURCES_DATA, PROFILES_DATA
from .utils import MockBackendRequestHandler, MockConsentManagerRequestHandler

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

CONSENT_MANAGER_PORT = get_free_port()
CONSENT_MANAGER_URI = 'http://localhost:{}'.format(CONSENT_MANAGER_PORT)

HGW_BACKEND_PORT = get_free_port()
HGW_BACKEND_URI = 'http://localhost:{}'.format(HGW_BACKEND_PORT)

DEST_PUBLIC_KEY = '-----BEGIN PUBLIC KEY-----\n' \
                  'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAp4TF/ETwYKG+eAYZz3wo\n' \
                  '8IYqrPIlQyz1/xljqDD162ZAYJLCYeCfs9yczcazC8keWzGd5/tn4TF6II0oINKh\n' \
                  'kCYLqTIVkVGC7/tgH5UEe/XG1trRZfMqwl1hEvZV+/zanV0cl7IjTR9ajb1TwwQY\n' \
                  'MOjcaaBZj+xfD884pwogWkcSGTEODGfoVACHjEXHs+oVriHqs4iggiiMYbO7TBjg\n' \
                  'Be9p7ZDHSVBbXtQ3XuGKnxs9MTLIh5L9jxSRb9CgAtv8ubhzs2vpnHrRVkRoddrk\n' \
                  '8YHKRryYcVDHVLAGc4srceXU7zrwAMbjS7msh/LK88ZDUWfIZKZvbV0L+/topvzd\n' \
                  'XQIDAQAB\n' \
                  '-----END PUBLIC KEY-----'

DEST_1_NAME = 'Destination 1'
DEST_1_ID = 'vnTuqCY3muHipTSan6Xdctj2Y0vUOVkj'
DEST_2_NAME = 'Destination 2'
DEST_2_ID = '6RtHuetJ44HKndsDHI5K9JUJxtg0vLJ3'
DISPATCHER_NAME = 'Health Gateway Dispatcher'
POWERLESS_NAME = 'Powerless Client'


class TestHGWFrontendAPI(TestCase):
    fixtures = ['test_data.json']

    @classmethod
    def setUpClass(cls):
        super(TestHGWFrontendAPI, cls).setUpClass()
        logger = logging.getLogger('hgw_frontend')
        logger.setLevel(logging.ERROR)
        start_mock_server('certs', MockConsentManagerRequestHandler, CONSENT_MANAGER_PORT)
        start_mock_server('certs', MockBackendRequestHandler, HGW_BACKEND_PORT)

    def setUp(self):
        self.client = client.Client()
        payload = '[{"clinical_domain": "Laboratory"}]'
        self.profile = {
            'code': 'PROF_001',
            'version': 'v0',
            'payload': payload
        }
        self.flow_request = {
            'flow_id': 'f_44444',
            'profile': self.profile,
            'start_validity': '2017-10-23T10:00:00+02:00',
            'expire_validity': '2018-10-23T10:00:00+02:00'
        }

        self.encrypter = Cipher(public_key=RSA.importKey(DEST_PUBLIC_KEY))

        with open(os.path.abspath(os.path.join(BASE_DIR, '../hgw_frontend/fixtures/test_data.json'))) as fixtures_file:
            self.fixtures = json.load(fixtures_file)

        self.profiles = {obj['pk']: obj['fields'] for obj in self.fixtures
                         if obj['model'] == 'hgw_common.profile'}
        self.sources = {obj['pk']: {
            'source_id': obj['fields']['source_id'],
            'name': obj['fields']['name'],
            'profile':  self.profiles[obj['fields']['profile']]
        } for obj in self.fixtures if obj['model'] == 'hgw_frontend.source'}
        self.destinations = {obj['pk']: obj['fields'] for obj in self.fixtures
                             if obj['model'] == 'hgw_frontend.destination'}
        self.flow_requests = {obj['pk']: obj['fields'] for obj in self.fixtures
                              if obj['model'] == 'hgw_frontend.flowrequest'}
        self.channels = {obj['pk']: {
            'channel_id': obj['fields']['channel_id'],
            'source': self.sources[obj['fields']['source']],
            'profile': self.profiles[self.flow_requests[obj['fields']['flow_request']]['profile']],
            'destination_id':
            self.destinations[self.flow_requests[obj['fields']['flow_request']]['destination']]['destination_id'],
                'status': obj['fields']['status']
        } for obj in self.fixtures if obj['model'] == 'hgw_frontend.channel'}

        self.active_flow_request_channels = {obj['pk']: {
            'channel_id': obj['fields']['channel_id'],
            'source': self.sources[obj['fields']['source']],
            'profile': self.profiles[self.flow_requests[obj['fields']['flow_request']]['profile']],
            'destination_id':
            self.destinations[self.flow_requests[obj['fields']['flow_request']]['destination']]['destination_id'],
                'status': obj['fields']['status']
        } for obj in self.fixtures if obj['model'] == 'hgw_frontend.channel' and obj['fields']['flow_request'] == 2}

    def set_mock_kafka_consumer(self, mock_kc_klass):
        mock_kc_klass.FIRST = 3
        mock_kc_klass.END = 33
        message = self.encrypter.encrypt(1000000 * 'a')
        mock_kc_klass.MESSAGES = {i: MockMessage(key="33333".encode('utf-8'), offset=i,
                                                 topic=DEST_1_ID.encode('utf-8'),
                                                 value=message) for i in range(mock_kc_klass.FIRST, mock_kc_klass.END)}

    @staticmethod
    def _get_client_data(client_name=DEST_1_NAME):
        app = RESTClient.objects.get(name=client_name)
        return app.client_id, app.client_secret

    def _get_oauth_header(self, client_name=DEST_1_NAME):
        c_id, c_secret = self._get_client_data(client_name)
        params = {
            'grant_type': 'client_credentials',
            'client_id': c_id,
            'client_secret': c_secret
        }
        res = self.client.post('/oauth2/token/', data=params)
        access_token = res.json()['access_token']
        return {"Authorization": "Bearer {}".format(access_token)}

    def test_init_fixtures(self):
        self.assertEqual(RESTClient.objects.all().count(), 4)
        self.assertEqual(Destination.objects.all().count(), 2)
        self.assertEqual(FlowRequest.objects.all().count(), 3)

    def test_create_oauth2_token(self):
        """
        Tests correct oauth2 token creation
        """
        c_id, c_secret = self._get_client_data()
        params = {
            'grant_type': 'client_credentials',
            'client_id': c_id,
            'client_secret': c_secret
        }
        res = self.client.post('/oauth2/token/', data=params)
        self.assertEqual(res.status_code, 200)
        self.assertIn('access_token', res.json())

    def test_create_oauth2_token_unauthorized(self):
        """
        Tests oauth2 token creation fails when unknown client data are sent
        """
        params = {
            'grant_type': 'client_credentials',
            'client_id': 'unkn_client_id',
            'client_secret': 'unkn_client_secret'
        }
        res = self.client.post('/oauth2/token/', data=params)
        self.assertEqual(res.status_code, 401)
        self.assertDictEqual(res.json(), {'error': 'invalid_client'})

    def test_create_oauth2_token_wrong_grant_type(self):
        """
        Tests oauth2 token creation fails when the grant type is wrong
        """
        c_id, c_secret = self._get_client_data()
        params = {
            'grant_type': 'wrong',
            'client_id': c_id,
            'client_secret': c_secret
        }
        res = self.client.post('/oauth2/token/', data=params)
        self.assertEqual(res.status_code, 400)
        self.assertDictEqual(res.json(), {'error': 'unsupported_grant_type'})

        # Gets the confirmation code installed with the test data
        c = ConsentConfirmation.objects.get(confirmation_id=CORRECT_CONFIRM_ID)
        self.client.get('/v1/flow_requests/confirm/?consent_confirm_id={}'.format(CORRECT_CONFIRM_ID))

    def test_get_message(self):
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=DEST_1_NAME)
            res = self.client.get('/v1/messages/3/', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()['message_id'], 3)
            res = self.client.get('/v1/messages/15/', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()['message_id'], 15)
            res = self.client.get('/v1/messages/32/', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()['message_id'], 32)

    def test_get_messages(self):
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=DEST_1_NAME)
            res = self.client.get('/v1/messages/', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res['X-Total-Count'], '30')
            self.assertEqual(res['X-Skipped'], '0')
            self.assertEqual(len(res.json()), 5)

            res = self.client.get('/v1/messages/?start=6&limit=3', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.json()), 3)
            self.assertEqual(res['X-Total-Count'], '30')
            self.assertEqual(res['X-Skipped'], '3')
            self.assertEqual(res.json()[0]['message_id'], 6)
            self.assertEqual(res.json()[1]['message_id'], 7)
            self.assertEqual(res.json()[2]['message_id'], 8)

    def test_get_messages_max_limit(self):
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=DEST_1_NAME)
            res = self.client.get('/v1/messages/?start=3&limit=11', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.json()), 10)
            self.assertEqual(res['X-Total-Count'], '30')
            self.assertEqual(res['X-Skipped'], '0')
            for i in range(3, 13):
                self.assertEqual(res.json()[i - 3]['message_id'], i)

    def test_get_message_not_found(self):
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=DEST_1_NAME)
            res = self.client.get('/v1/messages/33/', **headers)
            self.assertEqual(res.status_code, 404)
            self.assertDictEqual(res.json(), {'first_id': 3, 'last_id': 32})

            res = self.client.get('/v1/messages/0/', **headers)
            self.assertEqual(res.status_code, 404)
            self.assertDictEqual(res.json(), {'first_id': 3, 'last_id': 32})

    def test_get_messages_not_found(self):
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=DEST_1_NAME)
            res = self.client.get('/v1/messages/?start=30&limit=5', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.json()), 3)
            self.assertEqual(res['X-Skipped'], '27')
            self.assertEqual(res['X-Total-Count'], '30')

            res = self.client.get('/v1/messages/?start=0&limit=5', **headers)
            self.assertEqual(res.status_code, 404)
            self.assertDictEqual(res.json(), {'first_id': 3, 'last_id': 32})

    def test_get_messages_info(self):
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=DEST_1_NAME)
            res = self.client.get('/v1/messages/info/', **headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json(), {
                'start_id': 3,
                'last_id': 32,
                'count': 30
            })

    def test_rest_forbidden(self):
        """
        Tests that accessing via REST is forbidden for a client configured using kafka
        :return:
        """
        with patch('hgw_frontend.views.messages.KafkaConsumer', MockKafkaConsumer):
            self.set_mock_kafka_consumer(MockKafkaConsumer)
            headers = self._get_oauth_header(client_name=POWERLESS_NAME)
            res = self.client.get('/v1/messages/3/', **headers)
            self.assertEqual(res.status_code, 403)
            res = self.client.get('/v1/messages/', **headers)
            self.assertEqual(res.status_code, 403)
            res = self.client.get('/v1/messages/info/', **headers)
            self.assertEqual(res.status_code, 403)

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_sources(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/sources/', **headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), SOURCES_DATA)

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_sources_unauthorized(self):
        """
        Tests get sources endpoint
        """
        res = self.client.get('/v1/sources/')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {'errors': ['not_authenticated']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_sources_forbidden(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header(client_name=POWERLESS_NAME)
        res = self.client.get('/v1/sources/', **headers)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'errors': ['forbidden']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    @patch('hgw_frontend.views.sources.HGW_BACKEND_CLIENT_ID', 'wrong_client_id')
    def test_get_sources_fail_backend_access_token(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/sources/', **headers)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json(), {'errors': ['invalid_backend_client']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', 'http://localhost')
    def test_get_sources_fail_backend_connection_error(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/sources/', **headers)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json(), {'errors': ['backend_connection_error']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_profiles(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/profiles/', **headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), PROFILES_DATA)

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_profiles_unauthorized(self):
        """
        Tests get sources endpoint
        """
        res = self.client.get('/v1/profiles/')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {'errors': ['not_authenticated']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_profiles_forbidden(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header(client_name=POWERLESS_NAME)
        res = self.client.get('/v1/profiles/', **headers)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'errors': ['forbidden']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    @patch('hgw_frontend.views.sources.HGW_BACKEND_CLIENT_ID', 'wrong_client_id')
    def test_get_profiles_fail_backend_access_token(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/profiles/', **headers)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json(), {'errors': ['invalid_backend_client']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', 'http://localhost')
    def test_get_profiles_fail_backend_connection_error(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/profiles/', **headers)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json(), {'errors': ['backend_connection_error']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_source(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header(client_name=DEST_1_NAME)
        res = self.client.get('/v1/sources/{}/'.format(SOURCES_DATA[0]['source_id']), **headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), SOURCES_DATA[0])

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_source_unauthorized(self):
        """
        Tests get sources endpoint
        """
        res = self.client.get('/v1/sources/{}/'.format(SOURCES_DATA[0]['source_id']))
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {'errors': ['not_authenticated']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    def test_get_source_forbidden(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header(client_name=POWERLESS_NAME)
        res = self.client.get('/v1/sources/{}/'.format(SOURCES_DATA[0]['source_id']), **headers)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'errors': ['forbidden']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', HGW_BACKEND_URI)
    @patch('hgw_frontend.views.sources.HGW_BACKEND_CLIENT_ID', 'wrong_client_id')
    def test_get_source_fail_backend_access_token(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/sources/{}/'.format(SOURCES_DATA[0]['source_id']), **headers)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json(), {'errors': ['invalid_backend_client']})

    @patch('hgw_frontend.views.sources.HGW_BACKEND_URI', 'http://localhost')
    def test_get_source_fail_backend_connection_error(self):
        """
        Tests get sources endpoint
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/sources/{}/'.format(SOURCES_DATA[0]['source_id']), **headers)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json(), {'errors': ['backend_connection_error']})

    def test_get_channels(self):
        """
        Tests getting channels
        """
        headers = self._get_oauth_header()
        res = self.client.get('/v1/channels/', **headers)
        self.assertEqual(res.status_code, 200)
        expected = [ch_fi for ch_pk, ch_fi in self.channels.items()
                    if ch_fi['destination_id'] == DEST_1_ID]
        self.assertEqual(res.json(), expected)
        self.assertEqual(res['X-Total-Count'], str(len(expected)))

    def test_get_channels_filter_by_status(self):
        """
        Tests getting channels related to a specific flow_request
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/channels/?status=AC', **headers)
        self.assertEqual(res.status_code, 200)
        expected = [ch_fi for ch_pk, ch_fi in self.channels.items()
                    if ch_fi['destination_id'] == DEST_2_ID and ch_fi['status'] == 'AC']
        self.assertEqual(res.json(), expected)
        self.assertEqual(res['X-Total-Count'], str(len(expected)))

    def test_get_channels_filter_by_status_wrong_status(self):
        """
        Tests getting channels related to a specific flow_request
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/channels/?status=WRONG_STATUS', **headers)
        self.assertEqual(res.status_code, 400)

    def test_get_channels_by_superuser(self):
        """
        Tests getting all channels from a superuser
        """
        headers = self._get_oauth_header(client_name=DISPATCHER_NAME)
        res = self.client.get('/v1/channels/', **headers)
        self.assertEqual(res.status_code, 200)
        expected = [ch_fi for ch_pk, ch_fi in self.channels.items()]
        self.assertEqual(res.json(), expected)
        self.assertEqual(res['X-Total-Count'], str(len(expected)))

    def test_get_channels_unauthorized(self):
        """
        Tests get channels unauthorized
        """
        res = self.client.get('/v1/channels/')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {'errors': ['not_authenticated']})

    def test_get_channels_forbidden(self):
        """
        Tests get channels forbidden
        """
        headers = self._get_oauth_header(client_name=POWERLESS_NAME)
        res = self.client.get('/v1/channels/', **headers)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'errors': ['forbidden']})

    def test_get_channel(self):
        """
        Tests getting channels
        """
        target_channel = self.channels[1]
        headers = self._get_oauth_header()
        res = self.client.get('/v1/channels/nh4P0hYo2SEIlE3alO6w3geTDzLTOl7b/', **headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), target_channel)

    def test_get_channel_unauthorized(self):
        """
        Tests get channel unauthorized
        """
        res = self.client.get('/v1/channels/nh4P0hYo2SEIlE3alO6w3geTDzLTOl7b/')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {'errors': ['not_authenticated']})

    def test_get_channel_forbidden(self):
        """
        Tests get channels forbidden
        """
        headers = self._get_oauth_header(client_name=POWERLESS_NAME)
        res = self.client.get('/v1/channels/nh4P0hYo2SEIlE3alO6w3geTDzLTOl7b/', **headers)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'errors': ['forbidden']})

    def test_get_channel_by_superuser(self):
        """
        Tests get channels forbidden
        """
        target_channel = self.channels[1]
        headers = self._get_oauth_header(client_name=DISPATCHER_NAME)
        res = self.client.get('/v1/channels/nh4P0hYo2SEIlE3alO6w3geTDzLTOl7b/', **headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), target_channel)

    def test_get_channel_not_found(self):
        """
        Tests get channels not found. It tests not found for superclient, for nonexistent channel and for a channel
        that belongs to another destination
        """
        headers = self._get_oauth_header(client_name=DISPATCHER_NAME)
        res = self.client.get('/v1/channels/nonexistent_channel/', **headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'errors': ['not_found']})

        headers = self._get_oauth_header(client_name=DEST_1_NAME)
        res = self.client.get('/v1/channels/nonexistent_channel/', **headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'errors': ['not_found']})

        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/channels/nh4P0hYo2SEIlE3alO6w3geTDzLTOl7b/', **headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'errors': ['not_found']})

    def test_get_channels_by_flow_request(self):
        """
        Tests getting channels related to a specific flow_request
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/flow_requests/p_22222/channels/', **headers)
        self.assertEqual(res.status_code, 200)
        expected = [ch_fi for ch_pk, ch_fi in self.active_flow_request_channels.items()
                    if ch_fi['destination_id'] == DEST_2_ID]
        self.assertEqual(res.json(), expected)
        self.assertEqual(res['X-Total-Count'], str(len(expected)))

    def test_get_channels_by_flow_request_filter_by_status(self):
        """
        Tests getting channels related to a specific flow_request
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/flow_requests/p_22222/channels/?status=AC', **headers)
        self.assertEqual(res.status_code, 200)
        expected = [ch_fi for ch_pk, ch_fi in self.active_flow_request_channels.items()
                    if ch_fi['destination_id'] == DEST_2_ID and ch_fi['status'] == 'AC']
        self.assertEqual(res.json(), expected)
        self.assertEqual(res['X-Total-Count'], str(len(expected)))

    def test_get_channels_by_flow_request_filter_by_status_wrong_status(self):
        """
        Tests getting channels related to a specific flow_request
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/flow_requests/p_22222/channels/?status=WRONG_STATUS', **headers)
        self.assertEqual(res.status_code, 400)

    def test_get_channels_by_flow_request_flow_request_not_found(self):
        """
        Tests getting channels related to a specific flow_request which is not found
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/flow_requests/nonexistentfr/channels/', **headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'errors': ['not_found']})

    def test_get_channels_by_flow_request_channels_not_found(self):
        """
        Tests getting channels related to a specific flow_request when the flow_request has no channels
        """
        headers = self._get_oauth_header(client_name=DEST_2_NAME)
        res = self.client.get('/v1/flow_requests/p_33333/channels/', **headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'errors': ['not_found']})

    def test_get_channels_by_flow_request_not_owner(self):
        """
        Tests getting channels related to a specific flow_request when the flow_request does not
        belong to the same Destination
        """
        headers = self._get_oauth_header(client_name=DEST_1_NAME)
        res = self.client.get('/v1/flow_requests/p_22222/channels/', **headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'errors': ['not_found']})

    def test_get_channels_by_flow_request_by_superuser(self):
        """
        Tests getting channels related to a specific flow_request
        """
        headers = self._get_oauth_header(client_name=DISPATCHER_NAME)
        res = self.client.get('/v1/flow_requests/p_22222/channels/', **headers)
        self.assertEqual(res.status_code, 200)
        expected = [ch_fi for ch_pk, ch_fi in self.active_flow_request_channels.items()
                    if ch_fi['destination_id'] == DEST_2_ID]
        self.assertEqual(res.json(), expected)
        self.assertEqual(res['X-Total-Count'], str(len(expected)))

    def test_get_channels_by_flow_request_unauthorized(self):
        """
        Tests get channels unauthorized
        """
        res = self.client.get('/v1/flow_requests/33333/channels/')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {'errors': ['not_authenticated']})

    def test_get_channels_by_flow_request_forbidden(self):
        """
        Tests get channels forbidden
        """
        headers = self._get_oauth_header(client_name=POWERLESS_NAME)
        res = self.client.get('/v1/flow_requests/33333/channels/', **headers)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'errors': ['forbidden']})
