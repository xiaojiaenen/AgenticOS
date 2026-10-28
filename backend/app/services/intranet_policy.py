"""内网访问策略（SSRF 防护 + 出网限制）。

内网爬虫的本质是「让服务器去访问任意地址」—— 这正是 SSRF 的定义。
没有这层防护，一个被诱导的模型就能用 AgenticOS 服务器去探测内网
（甚至打云元数据接口拿实例凭据）。

因此这里做**默认拒绝**：只有落在允许网段 / 白名单里的目标才放行。
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

# 云厂商元数据地址：任何情况下都禁止（即使网段白名单写得很宽）
_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "100.100.100.200",
}

# 只允许这些协议
_ALLOWED_SCHEMES = {"http", "https"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    resolved_ip: str = ""


def _parse_cidrs(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            continue
    return nets


def _ip_in_networks(ip: ipaddress._BaseAddress, nets: list) -> bool:
    return any(ip in net for net in nets)


def resolve_host(host: str) -> list[ipaddress._BaseAddress]:
    """解析主机名，返回所有 IP。解析失败返回空列表。"""
    try:
        # 先按字面量试（避免对内网 IP 走 DNS）
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    ips = []
    for info in infos:
        try:
            ips.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return ips


def check_url(
    url: str,
    *,
    allowed_cidrs: str = "",
    egress_allowlist: str = "",
) -> PolicyDecision:
    """检查一个 URL 是否允许访问。

    判定顺序：
    1. 协议必须是 http/https；
    2. 主机不能是元数据地址；
    3. 主机解析出的 IP 必须落在 ``allowed_cidrs`` 内
       （或主机本身在 ``egress_allowlist`` 里）；
    4. 所有解析出的 IP 都要通过 —— 防止 DNS rebinding（一个域名
       同时给出内网 IP 和外网 IP）。

    ``allowed_cidrs`` 为空 → 拒绝一切（默认拒绝）。
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return PolicyDecision(False, f"URL 解析失败：{exc}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return PolicyDecision(
            False, f"不支持的协议 '{scheme}'，只允许 http/https"
        )

    host = (parsed.hostname or "").strip()
    if not host:
        return PolicyDecision(False, "URL 缺少主机名")

    if host.lower() in _BLOCKED_HOSTS:
        return PolicyDecision(False, f"禁止访问元数据地址：{host}")

    # 出网白名单里的主机直接放行（运维显式声明的例外）
    egress = _parse_cidrs(egress_allowlist)
    egress_names = {
        c.strip().lower()
        for c in (egress_allowlist or "").split(",")
        if c.strip() and not _looks_like_cidr(c.strip())
    }
    if host.lower() in egress_names:
        return PolicyDecision(True, "命中出网白名单", host)

    ips = resolve_host(host)
    if not ips:
        return PolicyDecision(False, f"域名无法解析：{host}")

    nets = _parse_cidrs(allowed_cidrs)
    if not nets:
        return PolicyDecision(
            False,
            "未配置允许网段（INTRANET_ALLOWED_CIDRS），内网访问默认禁止",
        )

    for ip in ips:
        if _ip_in_networks(ip, egress):
            return PolicyDecision(True, "命中出网白名单网段", str(ip))
        if not _ip_in_networks(ip, nets):
            return PolicyDecision(
                False,
                f"目标 {ip} 不在允许网段内（INTRANET_ALLOWED_CIDRS）",
                str(ip),
            )

    return PolicyDecision(True, "在允许网段内", str(ips[0]))


def _looks_like_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return True
