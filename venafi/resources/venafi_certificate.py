#!/usr/bin/env python3
#
# Copyright 2019 Venafi, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import six
from heat.common.i18n import _
from heat.engine import attributes
from heat.engine import constraints
from heat.engine import properties
from heat.engine import resource
from heat.engine import support
import time
from oslo_log import log as logging

from vcert import Connection, CertificateRequest

NOVA_MICROVERSIONS = (MICROVERSION_KEY_TYPE,
                      MICROVERSION_USER) = ('2.2', '2.10')

LOG = logging.getLogger(__name__)


class VenafiCertificate(resource.Resource):
    """A resource for creating Venafi certificates.
    """

    support_status = support.SupportStatus(version='2014.1')

    PROPERTIES = (
        NAME,
        CN,
        KEY_PASSWORD,
        KEY_TYPE,
        KEY_LENGTH,
        KEY_CURVE,
        SANs,
        ZONE,
        SAVE_PRIVATE_KEY,
        VENAFI_URL,
        TPP_USER,
        TPP_PASSWORD,
        API_KEY,
        TRUST_BUNDLE,
        FAKE
    ) = (
        'name',
        'common_name',
        'key_password',
        'key_type',
        'key_length',
        'key_curve',
        'sans',
        'zone',
        'save_private_key',
        'venafi_url',
        'tpp_user',
        'tpp_password',
        'api_key',
        'trust_bundle',
        'fake'
    )

    ATTRIBUTES = (
        CERTIFICATE_ATTR,
        PRIVATE_KEY_ATTR,
        CHAIN_ATTR,
    ) = (
        'certificate',
        'private_key',
        'chain',
    )

    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('The name of certificate'),
            required=True,
            constraints=[
                constraints.Length(min=1, max=255)
            ]
        ),
        CN: properties.Schema(
            properties.Schema.STRING,
            _('The common name of certificate'),
            required=True,
            constraints=[
                constraints.Length(min=1, max=255)
            ]
        ),
        KEY_PASSWORD: properties.Schema(
            properties.Schema.STRING,
            _("Cryptography key password"),
            default=None,
        ),
        KEY_TYPE: properties.Schema(
            properties.Schema.STRING,
            _("Cryptography key type"),
            default="RSA",
            constraints=[constraints.AllowedValues(("RSA", "ECDSA"))],
        ),
        KEY_LENGTH: properties.Schema(
            properties.Schema.INTEGER,
            _("Key length (only for RSA key_type)"),
            default=2048,
            constraints=[constraints.AllowedValues((1024, 2048, 4096, 8192))],
        ),
        KEY_CURVE: properties.Schema(
            properties.Schema.STRING,
            _("Key curve (only for ecdsa key_type)"),
            default="p521",
            constraints=[constraints.AllowedValues(("p521", "p256", "p224", "p384"))],
        ),
        SANs: properties.Schema(
            properties.Schema.LIST,
            _("List of Subject Alternative Names"),
            default=tuple(),
        ),

        ZONE: properties.Schema(
            properties.Schema.STRING,
            _("Venafi Trust Platform or Cloud zone name"),
            required=True,
            constraints=[constraints.Length(min=1, max=255)]
        ),
        SAVE_PRIVATE_KEY: properties.Schema(
            properties.Schema.BOOLEAN,
            _('True if the system should remember a generated private key; '
              'False otherwise.'),
            default=False
        ),
        VENAFI_URL: properties.Schema(
            properties.Schema.STRING,
            _("Trust Platform or Venafi Cloud url (required for TPP connection and optional for Cloud)"),
        ),
        TPP_USER: properties.Schema(
            properties.Schema.STRING,
            _("Trust Platform user (required for TPP connection)"),
        ),
        TPP_PASSWORD: properties.Schema(
            properties.Schema.STRING,
            _("Trust Platform password (required for TPP connection)"),
        ),
        API_KEY: properties.Schema(
            properties.Schema.STRING,
            _("Venafi Cloud api key (required for Cloud connection)"),
        ),
        TRUST_BUNDLE: properties.Schema(
            properties.Schema.STRING,
            _("Path to server certificate trust bundle")
        ),
        FAKE: properties.Schema(
            properties.Schema.BOOLEAN,
            _("Use fake testong connection if true"),
            default=False
        )
    }

    attributes_schema = {
        CERTIFICATE_ATTR: attributes.Schema(
            _('Venafi certificate.'),
            type=attributes.Schema.STRING
        ),
        PRIVATE_KEY_ATTR: attributes.Schema(
            _('Venafi certificate.'),
            type=attributes.Schema.STRING
        ),
        CHAIN_ATTR: attributes.Schema(
            _('Venafi certificate.'),
            type=attributes.Schema.STRING
        ),
    }

    default_client_name = 'nova'

    entity = 'venafi_certificate'

    def __init__(self, name, json_snippet, stack):
        super(VenafiCertificate, self).__init__(name, json_snippet, stack)
        self._cache = None
        self.conn = self.get_connection()

    @property
    def certificate(self):
        """Return Venafi certificate for the resource."""
        return self.data().get('certificate', '')

    @property
    def chain(self):
        """Return Venafi certificate chain for the resource."""
        return self.data().get('chain', '')

    @property
    def private_key(self):
        """Return Venafi certificate private key for the resource."""
        if self.properties[self.SAVE_PRIVATE_KEY]:
            return self.data().get('private_key', '')
        else:
            return ''

    def get_connection(self):
        url = self.properties[self.VENAFI_URL]
        user = self.properties[self.TPP_USER]
        password = self.properties[self.TPP_PASSWORD]
        token = self.properties[self.API_KEY]
        trust_bundle = self.properties[self.TRUST_BUNDLE]
        fake = self.properties[self.FAKE]
        LOG.info("fake is %s", fake)
        if trust_bundle:
            return Connection(url, token, user, password, http_request_kwargs={"verify": trust_bundle}, fake=fake)
        return Connection(url, token, user, password, fake=fake)

    def enroll(self):
        LOG.info("Running enroll")
        common_name = self.properties[self.CN]
        LOG.info("common name is %s", common_name)
        sans = self.properties[self.SANs]
        LOG.info("sans is %s", sans)
        privatekey_passphrase = self.properties[self.KEY_PASSWORD]
        LOG.info("privatekey_passphrase is %s", privatekey_passphrase)
        privatekey_type = self.properties[self.KEY_TYPE]
        LOG.info("privatekey_type is %s", privatekey_type)
        curve = self.properties[self.KEY_CURVE]
        LOG.info("curve is %s", curve)
        key_size = self.properties[self.KEY_LENGTH]
        LOG.info("key_size is %s", key_size)
        zone = self.properties[self.ZONE]
        LOG.info("zone is %s", zone)
        LOG.info("Creating request with CN %s", common_name)
        request = CertificateRequest(
            common_name=common_name,
        )

        if privatekey_type:
            key_type = {"RSA": "rsa", "ECDSA": "ec", "EC": "ec"}.get(privatekey_type)
            if not key_type:
                raise Exception("Failed to determine key type: %s. "
                                "Must be RSA or ECDSA" % privatekey_type)
            request.key_type = key_type
            request.key_curve = curve
            request.key_length = key_size

        san_dns = sans  # todo
        ip_addresses = []
        email_addresses = []
        request.ip_addresses = ip_addresses
        request.san_dns = san_dns
        request.email_addresses = email_addresses

        self.conn.request_cert(request, zone)
        LOG.info("CSR is: %s", request.csr)
        while True:
            LOG.info("Trying to retrieve certificate")
            cert = self.conn.retrieve_cert(request)  # vcert.Certificate
            if cert:
                break
            else:
                time.sleep(5)
        #         TODO: just workaround because fake cert doesn't have chain
        LOG.info("Got certificate: %s", cert.cert)
        LOG.info("Got chain: %s", cert.chain)
        LOG.info("Got pkey: %s", request.private_key_pem)
        return {self.CHAIN_ATTR: cert.chain, self.CERTIFICATE_ATTR: cert.cert, self.PRIVATE_KEY_ATTR: request.private_key_pem}

    def handle_create(self):
        LOG.info("Creating Venafi certificate")
        self._cache = self.enroll()
        LOG.info("Saving to data certificate: %s", self._cache[self.CERTIFICATE_ATTR])
        self.data_set('certificate', self._cache[self.CERTIFICATE_ATTR], redact=False)
        LOG.info("Saving to data chain: %s", self._cache[self.CHAIN_ATTR])
        self.data_set('chain', self._cache[self.CHAIN_ATTR], redact=False)
        LOG.info("Saving to data private_key: %s", self._cache[self.PRIVATE_KEY_ATTR])
        self.data_set('private_key', self._cache[self.PRIVATE_KEY_ATTR], redact=False)

    def _resolve_attribute(self, name):
        attr_fn = {self.CERTIFICATE_ATTR: self.certificate,
                   self.CHAIN_ATTR: self.chain,
                   self.PRIVATE_KEY_ATTR: self.private_key}
        return six.text_type(attr_fn[name])

    def get_reference_id(self):
        return self.resource_id

def resource_mapping():
    return {'OS::Nova::VenafiCertificate': VenafiCertificate}
