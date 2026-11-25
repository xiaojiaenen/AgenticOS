"""SOPS 加密配置加载层（docs/design/项目逐功能优化方案.md 3C.3 / 战线 D）。

[Mozilla SOPS](https://github.com/getsops/sops)（MPL-2.0，本地 CLI）用于
把密钥/凭据以**加密形态**提交与分发：``.env.sops``（加密的 dotenv）配合
age/KMS 解密。接入点在配置加载最前面 —— Settings 读 env 之前，把解密出的
键合并进 ``os.environ``。

用法：
    1. ``sops encrypt --age <recipient> --input-type dotenv backend/.env.secrets
       > backend/.env.sops``；
    2. 部署机放 age 私钥 / 配 KMS；
    3. 环境变量 ``SOPS_FILE=/path/to/.env.sops``（可选 ``SOPS_BINARY`` 覆盖
       sops 可执行文件路径）。

语义：
- **真实环境变量优先**：合并用 ``os.environ.setdefault``，宿主上已显式
  配置的键不会被密文覆盖；
- 未配置 ``SOPS_FILE`` → 完全 no-op（默认部署零影响）；
- sops 不可用 / 解密失败 → CRITICAL 告警（密钥缺失必须显眼），但不阻断
  启动 —— 无法假定哪些键对本次部署必需，由业务侧按缺键自行失败。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("agenticos.secrets")

_LOADED = False


def _parse_dotenv(text: str) -> dict[str, str]:
    """解析 dotenv 文本（KEY=VALUE，支持 export 前缀与引号，忽略注释）。"""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _decrypt_with_sops(sops_binary: str, path: Path) -> str:
    """调 sops CLI 解密；失败抛 subprocess.CalledProcessError。"""
    result = subprocess.run(
        [sops_binary, "-d", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout


def load_sops_secrets(force: bool = False) -> dict[str, str]:
    """把 ``SOPS_FILE`` 解密合并进 os.environ（幂等；返回合并的键值供测试）。

    真实环境变量优先（setdefault）。任何失败只告警不阻断 —— 但都是
    CRITICAL 级别，保证在告警管道里被看到。
    """
    global _LOADED
    if _LOADED and not force:
        return {}
    _LOADED = True

    file_path = os.environ.get("SOPS_FILE", "").strip()
    if not file_path:
        return {}

    path = Path(file_path)
    if not path.is_file():
        logger.critical("SOPS_FILE=%s 指向的加密配置不存在，密钥未加载", file_path)
        return {}

    sops_binary = os.environ.get("SOPS_BINARY") or shutil.which("sops")
    if not sops_binary:
        logger.critical(
            "SOPS_FILE 已配置但 sops 可执行文件不可用（装 sops 或用 SOPS_BINARY 指定路径），"
            "加密密钥未加载 —— 相关功能将以缺密钥状态启动"
        )
        return {}

    try:
        text = _decrypt_with_sops(sops_binary, path)
    except subprocess.CalledProcessError as exc:
        logger.critical(
            "sops 解密失败（exit=%s stderr=%s），密钥未加载 —— 检查 age 私钥/KMS 凭据",
            exc.returncode,
            (exc.stderr or "")[:200].replace("\n", " "),
        )
        return {}
    except Exception as exc:  # noqa: BLE001 —— 解密失败不能阻断启动
        logger.critical("sops 解密异常（%s），密钥未加载", exc)
        return {}

    merged: dict[str, str] = {}
    for key, value in _parse_dotenv(text).items():
        if key in os.environ:
            continue  # 真实环境变量优先
        os.environ[key] = value
        merged[key] = value
    logger.info("SOPS 加密配置已加载：%d 个密钥并入环境（键名不记日志）", len(merged))
    return merged
