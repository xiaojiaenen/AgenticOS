# tests 必须是包：否则 pytest 将 conftest.py 导入为顶层模块 "conftest"，
# 而 test_skills.py / test_agent_profiles.py 的 "from tests.conftest import ..."
# 会把它作为 "tests.conftest" 再执行一遍——顶层 shutil.rmtree 会把测试数据库
# 目录连同 test.db 一起删掉，导致后续所有用例报 "no such table"。
