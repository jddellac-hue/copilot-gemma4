"""Unit tests for the kubernetes tools.

These tests do NOT call kubectl. They verify the safety logic:
- namespace resolution (locked vs allowed-list vs default)
- resource kind validation
- name validation
- argv construction (context locked, no injection possible)
"""

from __future__ import annotations

import pytest

from harness.tools.kubernetes import (
    KubernetesConfig,
    _build_argv,
    _resolve_namespace,
    _validate_name,
    _validate_resource_kind,
    build_kubernetes_tools,
)


# ----- namespace resolution -------------------------------------------------


def test_locked_namespace_overrides_request():
    cfg = KubernetesConfig(
        enabled=True,
        context="prod",
        locked_namespace="billing",
        allowed_namespaces=["billing", "frontend"],
    )
    ns, err = _resolve_namespace(cfg, "frontend")
    assert ns is None
    assert "locked" in err


def test_locked_namespace_accepts_matching_request():
    cfg = KubernetesConfig(
        enabled=True, context="prod", locked_namespace="billing"
    )
    ns, err = _resolve_namespace(cfg, "billing")
    assert ns == "billing"
    assert err is None


def test_locked_namespace_used_when_no_request():
    cfg = KubernetesConfig(
        enabled=True, context="prod", locked_namespace="billing"
    )
    ns, err = _resolve_namespace(cfg, None)
    assert ns == "billing"
    assert err is None


def test_request_must_be_in_allowed_list():
    cfg = KubernetesConfig(
        enabled=True,
        context="staging",
        allowed_namespaces=["a", "b"],
    )
    ns, err = _resolve_namespace(cfg, "evil")
    assert ns is None
    assert "not in allowed list" in err


def test_request_in_allowed_list_succeeds():
    cfg = KubernetesConfig(
        enabled=True,
        context="staging",
        allowed_namespaces=["a", "b"],
    )
    ns, err = _resolve_namespace(cfg, "a")
    assert ns == "a"
    assert err is None


def test_default_namespace_when_no_request_and_no_lock():
    cfg = KubernetesConfig(
        enabled=True,
        context="staging",
        allowed_namespaces=["a", "b"],
        default_namespace="dflt",
    )
    ns, err = _resolve_namespace(cfg, None)
    assert ns == "dflt"
    assert err is None


# ----- resource kind validation --------------------------------------------


def test_allowed_kinds():
    for kind in ("pods", "po", "deploy", "svc", "configmaps", "nodes"):
        assert _validate_resource_kind(kind) is None


def test_disallowed_kind():
    err = _validate_resource_kind("clusterroles")
    assert err is not None
    assert "not in allow-list" in err


def test_kind_case_insensitive():
    assert _validate_resource_kind("PODS") is None


# ----- name validation ------------------------------------------------------


def test_valid_k8s_names():
    for name in ("foo", "foo-bar", "foo-123", "my-app.v1", "a"):
        assert _validate_name(name) is None


def test_invalid_k8s_names():
    for bad in ("Foo", "foo_bar", "foo bar", "-foo", "foo;rm", "foo$bar"):
        assert _validate_name(bad) is not None


def test_empty_name_rejected():
    assert _validate_name("") is not None


# ----- argv construction ----------------------------------------------------


def test_argv_includes_locked_context():
    cfg = KubernetesConfig(enabled=True, context="staging-cluster")
    argv = _build_argv(cfg, "get", "pods", namespace="default")
    assert "--context=staging-cluster" in argv
    assert "--namespace=default" in argv
    assert argv[0] == "kubectl"
    assert argv[1] == "get"


def test_argv_no_namespace_flag_when_none():
    cfg = KubernetesConfig(enabled=True, context="x")
    argv = _build_argv(cfg, "get", "nodes")
    assert not any(a.startswith("--namespace=") for a in argv)


def test_argv_includes_request_timeout():
    cfg = KubernetesConfig(enabled=True, context="x", timeout_s=42)
    argv = _build_argv(cfg, "get", "pods")
    assert "--request-timeout=42s" in argv


# ----- end-to-end build  ----------------------------------------------------


def test_build_returns_empty_when_disabled():
    tools = build_kubernetes_tools(KubernetesConfig(enabled=False))
    assert tools == []


def test_build_returns_empty_when_no_context():
    tools = build_kubernetes_tools(
        KubernetesConfig(enabled=True, context="")
    )
    assert tools == []


def test_build_returns_three_tools_when_enabled():
    tools = build_kubernetes_tools(
        KubernetesConfig(
            enabled=True,
            context="staging",
            allowed_namespaces=["default"],
        )
    )
    names = sorted(t.name for t in tools)
    assert names == ["kubectl_describe", "kubectl_get", "kubectl_logs"]


def test_kubectl_get_refuses_disallowed_kind():
    tools = build_kubernetes_tools(
        KubernetesConfig(
            enabled=True,
            context="staging",
            allowed_namespaces=["default"],
        )
    )
    get = next(t for t in tools if t.name == "kubectl_get")
    result = get.invoke({"kind": "clusterroles"})
    assert not result.ok
    assert "not in allow-list" in result.content


def test_kubectl_logs_refuses_bad_pod_name():
    tools = build_kubernetes_tools(
        KubernetesConfig(
            enabled=True,
            context="staging",
            allowed_namespaces=["default"],
        )
    )
    logs = next(t for t in tools if t.name == "kubectl_logs")
    result = logs.invoke({"pod": "foo;rm -rf /"})
    assert not result.ok
    assert "invalid k8s name" in result.content


def test_kubectl_logs_refuses_bad_since_value():
    tools = build_kubernetes_tools(
        KubernetesConfig(
            enabled=True,
            context="staging",
            allowed_namespaces=["default"],
        )
    )
    logs = next(t for t in tools if t.name == "kubectl_logs")
    result = logs.invoke({"pod": "valid-pod", "since": "5m; whoami"})
    assert not result.ok
    assert "invalid since" in result.content
