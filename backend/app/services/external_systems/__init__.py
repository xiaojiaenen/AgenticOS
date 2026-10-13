"""外部系统集成包（自原 app/services/external_system_service.py 拆分）。

模块划分：
- context            当前用户/会话的 contextvars
- cache              外部系统配置的 Redis 缓存
- coordinators       UserInputBlocker / ApprovalBlocker 阻塞协调器
- serializers        ORM 序列化助手与轻量凭据对象
- auth_injector      AuthInjector：出站请求认证注入
- security_processor SecurityProcessor：签名/加解密
- tool_builder       一系统一工具的动态工具注册
- service            ExternalSystemService CRUD 门面
- presets            预设外部系统 seed

兼容入口：``app.services.external_system_service`` 继续 re-export 全部既有符号。
"""
