# © 2022 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import json
import logging

import requests
from requests.exceptions import ConnectionError as ConnError, HTTPError, Timeout

from odoo.addons.component.core import AbstractComponent
from odoo.addons.connector.exception import NetworkRetryableError
from odoo.addons.queue_job.exception import FailedJobError

_logger = logging.getLogger(__name__)


def retryable_error(func):
    """
    Sometimes Jobs may fail because of a network error when calling
    api. The job have very good chance to go through later
    So we want to retry it automatically.
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ConnError, Timeout, HTTPError) as err:
            raise NetworkRetryableError(
                "A network error caused the failure of the job: " "%s" % str(err)
            )
        except Exception as e:
            raise e

    return wrapper


class DocuwareApi(object):
    def __init__(self, location, token=False):
        self.location = location
        self.token = token
        self.headers = {
            "User-Agent": "OdooConnector/1.0",
            "Accept": "application/json",
        }
        self.session = requests.session()

    def login(self):
        """
        Login into docuware
        """
        token_login_url = "{}/Account/TokenLogOn".format(self.location)
        data = {
            "Token": self.token,
            "HostID": "This_Is_A_Test",
            "LicenseType": "PlatformService",
        }
        response = self._make_call(token_login_url, "POST", params=data)
        if response.status_code != 200:
            raise FailedJobError(
                "%s error: %s" % (response.status_code, response.content)
            )
        return self

    def generate_access_token(self, username, password):
        login_url = "{}/Account/Logon".format(self.location)
        params = {"UserName": username, "Password": password}
        response = self._make_call(login_url, "POST", params)
        if response.status_code != 200:
            raise FailedJobError(
                "%s error: %s" % (response.status_code, response.content)
            )
        get_token_url = "{}/Organization/LoginToken".format(self.location)
        data = {
            "TargetProducts": ["PlatformService"],
            "Usage": "Multi",
            "Lifetime": "365.00:00:00",
        }
        token_response = self._make_call(get_token_url, "POST", json=data)
        if token_response.status_code != 200:
            raise FailedJobError(
                "%s error: %s" % (response.status_code, response.content)
            )
        return token_response.content

    def _make_call(
        self,
        url,
        method="GET",
        params=None,
        data=None,
        json=None,
        content_type="application/json",
    ):
        headers = self.headers
        headers["Content-Type"] = content_type
        return self.session.request(
            method,
            url,
            params=params,
            data=data,
            json=json,
            headers=self.headers,
        )

    def get(self, endpoint, id=False):
        url = "{}/{}".format(self.location, endpoint)
        if id:
            url = url + "/{}".format(id)
        response = self._make_call(url)
        if response.status_code != 200:
            raise FailedJobError(
                "%s error: %s" % (response.status_code, response.content)
            )
        return json.loads(response.content)

    def get_binary_data(self, endpoint, id=False):
        url = "{}/{}".format(self.location, endpoint)
        if id:
            url = url + "/{}".format(id)
        response = self._make_call(url)
        if response.status_code != 200:
            raise FailedJobError(
                "%s error: %s" % (response.status_code, response.content)
            )
        return response.content


class DocuwareCRUDAdapter(AbstractComponent):
    """External Records Adapter for Docuware"""

    _name = "docuware.crud.adapter"
    _inherit = ["base.backend.adapter", "base.docuware.connector"]
    _usage = "backend.adapter"
    # pylint: disable=method-required-super

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.ConnectorEnvironment`
        """
        super().__init__(environment)
        self.client = DocuwareApi(
            self.backend_record.url, self.backend_record.access_token
        )
        self.client.login()

    def search(self, filters=None):
        """Search records according to some criterias
        and returns a list of ids"""
        raise NotImplementedError

    def read(self, id_, attributes=None):
        """Returns the information of a record"""
        raise NotImplementedError

    def search_read(self, filters=None):
        """Search records according to some criterias
        and returns their information"""
        raise NotImplementedError

    def create(self, data):
        """Create a record on the external system"""
        raise NotImplementedError

    def write(self, id_, data):
        """Update records on the external system"""
        raise NotImplementedError

    def delete(self, id_, attributes=None):
        """Delete a record on the external system"""
        raise NotImplementedError


class GenericAdapter(AbstractComponent):
    _name = "docuware.adapter"
    _inherit = "docuware.crud.adapter"
    # pylint: disable=method-required-super

    _model_name = None
    _docuware_path = None
    # PS WS key for exporting
    _export_node_name = ""
    # PS WS key response
    # When you create a record in PS
    # you get back a result that is wrapped like this:
    # {'docuware': _export_node_name_res: {...}}
    # For instance: for `manufacturers`
    # _export_node_name="manufacturers"
    # _export_node_name_res = "manufacturer"
    _export_node_name_res = ""

    @retryable_error
    def search(self):
        """Search records according to some criterias
        and returns a list of ids
        :rtype: list
        """
        _logger.debug(
            "method search, model %s",
            self._docuware_path,
        )
        return self.client.get(self._docuware_path)

    @retryable_error
    def read(self, id_, attributes=None):
        """Returns the information of a record
        :rtype: dict
        """
        _logger.debug(
            "method read, model %s id %s, attributes %s",
            self._docuware_path,
            str(id_),
            str(attributes),
        )
        res = self.client.get(self._docuware_path, id_)
        return res

    def create(self, attributes=None):
        """Create a record on the external system"""
        _logger.debug(
            "method create, model %s, attributes %s",
            self._docuware_path,
            str(attributes),
        )
        res = self.client.add(self._docuware_path, {self._export_node_name: attributes})
        if self._export_node_name_res:
            return res["docuware"][self._export_node_name_res]["id"]
        return res

    def write(self, id_, attributes=None):
        """Update records on the external system"""
        attributes["id"] = id_
        _logger.debug(
            "method write, model %s, attributes %s",
            self._docuware_path,
            str(attributes),
        )
        res = self.client.edit(
            self._docuware_path, {self._export_node_name: attributes}
        )
        if self._export_node_name_res:
            return res["docuware"][self._export_node_name_res]["id"]
        return res

    def delete(self, resource, ids, attributes=None):
        _logger.debug("method delete, model %s, ids %s", resource, str(ids))
        # Delete a record(s) on the external system
        return self.client.delete(resource, ids)
