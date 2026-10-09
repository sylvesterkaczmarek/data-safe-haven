"""Regression tests for stale ACME account recovery during SRE certificate issuance."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from acme import messages

from data_safe_haven.exceptions import DataSafeHavenSSLError
from data_safe_haven.infrastructure.components.dynamic.ssl_certificate import (
    SSLCertificateProvider,
)

MISSING_ACCOUNT = "urn:ietf:params:acme:error:accountDoesNotExist"


@pytest.fixture
def props():
    return {
        "domain_name": "test.example.org",
        "admin_email_address": "admin@example.org",
        "networking_resource_group_name": "rg-test",
        "subscription_name": "subscription-test",
    }


@pytest.fixture
def setup_acme(mocker):
    first = Mock()
    second = Mock()
    for client in (first, second):
        client.generate_private_key.return_value = b"fake-private-key"
        client.request_verification_tokens.return_value = {
            "_acme-challenge.test.example.org": ["challenge-token"]
        }
        client.check_dns_propagation.return_value = True
        client.request_certificate.return_value = b"fake-certificate"
    constructor = mocker.patch(
        "data_safe_haven.infrastructure.components.dynamic.ssl_certificate.ACMEClient",
        side_effect=[first, second],
    )
    azure = Mock()
    azure.ensure_dns_txt_record.return_value = SimpleNamespace(ttl=1)
    azure_ctor = mocker.patch(
        "data_safe_haven.infrastructure.components.dynamic.ssl_certificate.AzureSdk",
        return_value=azure,
    )
    sleep = mocker.patch(
        "data_safe_haven.infrastructure.components.dynamic.ssl_certificate.time.sleep"
    )
    return first, second, constructor, azure, azure_ctor, sleep


def test_normal_certificate_order_does_not_retry(props, setup_acme):
    first, _, ctor, azure, _, sleep = setup_acme
    private, cert, sdk = (
        SSLCertificateProvider._request_certificate_with_account_recovery(props)
    )
    assert (private, cert, sdk) == (b"fake-private-key", b"fake-certificate", azure)
    ctor.assert_called_once()
    assert ctor.call_args.kwargs["new_account"] is True
    first.generate_private_key.assert_called_once_with(key_type="rsa2048")
    first.request_certificate.assert_called_once()
    azure.ensure_dns_txt_record.assert_called_once()
    sleep.assert_called_once_with(1)


def test_stale_account_while_creating_order_retries_once(props, setup_acme):
    first, second, ctor, _, _, _ = setup_acme
    first.request_verification_tokens.side_effect = messages.Error(
        typ=MISSING_ACCOUNT, detail="account not found"
    )
    _, cert, _ = SSLCertificateProvider._request_certificate_with_account_recovery(
        props
    )
    assert cert == b"fake-certificate"
    assert ctor.call_count == 2
    assert all(call.kwargs["new_account"] is True for call in ctor.call_args_list)
    first.request_certificate.assert_not_called()
    second.request_certificate.assert_called_once()


def test_stale_account_after_dns_challenge_retries_complete_order(props, setup_acme):
    first, second, ctor, azure, _, sleep = setup_acme
    first.request_certificate.side_effect = messages.Error(
        typ=MISSING_ACCOUNT, detail="account was removed"
    )
    SSLCertificateProvider._request_certificate_with_account_recovery(props)
    assert ctor.call_count == 2
    assert azure.ensure_dns_txt_record.call_count == 2
    assert sleep.call_count == 2
    second.request_certificate.assert_called_once()


def test_repeated_missing_account_fails_after_single_retry(props, setup_acme):
    first, second, ctor, _, _, _ = setup_acme
    for client in (first, second):
        client.request_verification_tokens.side_effect = messages.Error(
            typ=MISSING_ACCOUNT, detail="no account"
        )
    with pytest.raises(DataSafeHavenSSLError, match="after one retry"):
        SSLCertificateProvider._request_certificate_with_account_recovery(props)
    assert ctor.call_count == 2


def test_unrelated_acme_errors_are_not_retried(props, setup_acme):
    first, _, ctor, _, _, _ = setup_acme
    first.request_verification_tokens.side_effect = messages.Error(
        typ="urn:ietf:params:acme:error:rateLimited", detail="rate limited"
    )
    with pytest.raises(messages.Error, match="rateLimited"):
        SSLCertificateProvider._request_certificate_with_account_recovery(props)
    assert ctor.call_count == 1


def test_failed_dns_propagation_is_not_retried(props, setup_acme):
    first, _, ctor, _, _, sleep = setup_acme
    first.check_dns_propagation.return_value = False
    with pytest.raises(DataSafeHavenSSLError, match="DNS propagation failed"):
        SSLCertificateProvider._request_certificate_with_account_recovery(props)
    assert ctor.call_count == 1
    sleep.assert_not_called()


def test_missing_dns_verification_tokens_are_not_retried(props, setup_acme):
    first, _, ctor, _, azure_ctor, _ = setup_acme
    first.request_verification_tokens.return_value = {}
    with pytest.raises(
        DataSafeHavenSSLError, match="did not return any DNS verification tokens"
    ):
        SSLCertificateProvider._request_certificate_with_account_recovery(props)
    assert ctor.call_count == 1
    azure_ctor.assert_not_called()
