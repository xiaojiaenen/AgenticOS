"""注册测试技能到数据库"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_session
from app.db.models import SkillModel
from sqlalchemy import select

ROOT_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "skills", "agenticos-test")
ROOT_DIR = os.path.abspath(ROOT_DIR)


def register():
    with create_db_session() as db:
        existing = db.scalar(select(SkillModel).where(SkillModel.slug == "agenticos-test"))
        if existing:
            print(f"技能已存在: id={existing.id}, name={existing.name}")
            return

        row = SkillModel(
            name="AgenticOS 系统测试助手",
            slug="agenticos-test",
            description="用于验证 AgenticOS 平台核心功能的综合性测试技能，涵盖对话理解、工具调用、Python脚本执行和参考资料查询",
            enabled=True,
            root_dir=ROOT_DIR,
            created_by=1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        print(f"技能已创建: id={row.id}, slug={row.slug}, root_dir={row.root_dir}")


if __name__ == "__main__":
    register()
