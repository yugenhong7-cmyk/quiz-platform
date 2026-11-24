"""pytest 全局夹具：强制使用独立测试数据库，绝不触碰正式库 quiz_platform.db。"""
import os
import sys

# 必须在 import app.* 之前设置，config 在导入时读取环境变量
_TEST_DB = os.path.join(os.path.dirname(__file__), "pytest_quiz.db")
os.environ["DATABASE_URL"] = "sqlite:///" + _TEST_DB.replace("\\", "/")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
