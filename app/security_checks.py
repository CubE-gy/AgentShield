from dataclasses import dataclass
import ipaddress
import re
import socket
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SecurityCheckResult:
    """单项安全检查的统一结果。"""

    decision: str
    risk_type: str | None
    risk_level: str
    reason_code: str | None


@dataclass(frozen=True)
class SecurityCheckInput:
    """所有安全检查共用的输入数据。"""

    prompt: str = ""
    tool_name: str | None = None
    target_url: str | None = None
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class PiiMaskingResult:
    """PII 脱敏后的文本与检测到的类型。"""

    masked_prompt: str
    detected_types: tuple[str, ...]


_INSTRUCTION_OVERRIDE_PATTERN = re.compile(
    r"(?:"
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+"
    r"(?:instructions|rules|prompts)"
    r"|"
    r"(?:忽略|无视|不要遵守|忘记).{0,20}"
    r"(?:之前|先前|上面|所有|原有).{0,20}"
    r"(?:指令|规则|要求|提示词)"
    r")",
    re.IGNORECASE,
)

_EDUCATIONAL_CONTEXT_PATTERN = re.compile(
    r"^\s*(?:请|帮我)?(?:解释|说明|讨论|分析|识别|检测|举例).{0,80}"
    r"(?:提示注入|prompt injection|攻击)[。！？?]?\s*$",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.+-])",
    re.IGNORECASE,
)

_CHINA_MOBILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:\+?86[-\s]?)?1[3-9]\d{9}(?![A-Za-z0-9_])"
)


def check_prompt_injection(
    check_input: SecurityCheckInput,
) -> SecurityCheckResult:
    """检查明显的“覆盖既有指令”型提示注入。"""

    if (
        _INSTRUCTION_OVERRIDE_PATTERN.search(check_input.prompt)
        and not _EDUCATIONAL_CONTEXT_PATTERN.search(check_input.prompt)
    ):
        return SecurityCheckResult(
            decision="block",
            risk_type="prompt_injection",
            risk_level="high",
            reason_code="PROMPT_INJECTION_DETECTED",
        )

    return SecurityCheckResult(
        decision="allow",
        risk_type=None,
        risk_level="low",
        reason_code=None,
    )


def check_tool_allowlist(
    check_input: SecurityCheckInput,
) -> SecurityCheckResult:
    """检查请求的工具是否由本机配置允许。"""

    if (
        check_input.tool_name is None
        or check_input.tool_name in check_input.allowed_tools
    ):
        return SecurityCheckResult(
            decision="allow",
            risk_type=None,
            risk_level="low",
            reason_code=None,
        )

    return SecurityCheckResult(
        decision="block",
        risk_type="tool",
        risk_level="high",
        reason_code="TOOL_NOT_ALLOWED",
    )


def check_url_ssrf(
    check_input: SecurityCheckInput,
) -> SecurityCheckResult:
    """阻止指向本机、内网和禁止协议的 URL。"""

    if check_input.target_url is None:
        return SecurityCheckResult(
            decision="allow",
            risk_type=None,
            risk_level="low",
            reason_code=None,
        )

    parsed_url = urlsplit(check_input.target_url)
    if parsed_url.scheme not in {"http", "https"}:
        return SecurityCheckResult(
            decision="block",
            risk_type="ssrf",
            risk_level="high",
            reason_code="URL_SCHEME_NOT_ALLOWED",
        )

    if parsed_url.hostname is None:
        return SecurityCheckResult(
            decision="block",
            risk_type="ssrf",
            risk_level="high",
            reason_code="URL_INVALID",
        )

    hostname = parsed_url.hostname.rstrip(".").lower()
    if (
        hostname in {"localhost", "metadata.google.internal"}
        or hostname.endswith(".local")
    ):
        return SecurityCheckResult(
            decision="block",
            risk_type="ssrf",
            risk_level="high",
            reason_code="SSRF_TARGET_BLOCKED",
        )

    target_ip = _parse_ip_address(hostname)
    if target_ip is not None:
        if _is_blocked_ip_address(target_ip):
            return SecurityCheckResult(
                decision="block",
                risk_type="ssrf",
                risk_level="high",
                reason_code="SSRF_TARGET_BLOCKED",
            )

        return SecurityCheckResult(
            decision="allow",
            risk_type=None,
            risk_level="low",
            reason_code=None,
        )

    try:
        resolved_addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return SecurityCheckResult(
            decision="block",
            risk_type="ssrf",
            risk_level="high",
            reason_code="URL_HOST_RESOLUTION_FAILED",
        )

    for resolved_address in resolved_addresses:
        resolved_ip = ipaddress.ip_address(resolved_address[4][0])
        if _is_blocked_ip_address(resolved_ip):
            return SecurityCheckResult(
                decision="block",
                risk_type="ssrf",
                risk_level="high",
                reason_code="SSRF_TARGET_BLOCKED",
            )

    return SecurityCheckResult(
        decision="allow",
        risk_type=None,
        risk_level="low",
        reason_code=None,
    )


def _parse_ip_address(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    try:
        if hostname.isdecimal():
            ip_as_integer = int(hostname, 10)
        elif hostname.lower().startswith("0x"):
            ip_as_integer = int(hostname, 16)
        else:
            return None
    except ValueError:
        return None

    if 0 <= ip_as_integer <= 2**32 - 1:
        return ipaddress.IPv4Address(ip_as_integer)

    return None


def _is_blocked_ip_address(
    target_ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return (
        target_ip.is_loopback
        or target_ip.is_private
        or target_ip.is_link_local
        or target_ip.is_multicast
        or target_ip.is_reserved
        or target_ip.is_unspecified
    )


def mask_pii(check_input: SecurityCheckInput) -> PiiMaskingResult:
    """脱敏明确格式的邮箱和中国大陆手机号。"""

    masked_prompt, email_count = _EMAIL_PATTERN.subn(
        "[MASKED_EMAIL]",
        check_input.prompt,
    )
    masked_prompt, phone_count = _CHINA_MOBILE_PATTERN.subn(
        "[MASKED_PHONE]",
        masked_prompt,
    )

    detected_types = []
    if email_count:
        detected_types.append("email")
    if phone_count:
        detected_types.append("phone")

    return PiiMaskingResult(
        masked_prompt=masked_prompt,
        detected_types=tuple(detected_types),
    )
