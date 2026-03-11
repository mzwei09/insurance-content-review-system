"""pytest 配置"""
import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture(scope="session", autouse=True)
def use_test_database():
    """自动使用测试数据库，避免污染生产数据库"""
    # 创建临时测试数据库
    test_db_dir = Path("data/test")
    test_db_dir.mkdir(parents=True, exist_ok=True)
    test_db_path = test_db_dir / "test_users.db"
    
    # 设置环境变量，让测试使用测试数据库
    original_db = os.environ.get("DATABASE_URL")
    test_db_url = f"sqlite:///{test_db_path.absolute()}"
    os.environ["DATABASE_URL"] = test_db_url
    
    # 初始化测试数据库表结构
    from src.database import get_engine, init_db
    engine = get_engine(test_db_url)
    init_db(engine)
    
    yield
    
    # 测试结束后恢复原环境变量
    if original_db:
        os.environ["DATABASE_URL"] = original_db
    else:
        os.environ.pop("DATABASE_URL", None)
    
    # 清理测试数据库
    if test_db_path.exists():
        test_db_path.unlink()
    if test_db_dir.exists() and not list(test_db_dir.iterdir()):
        test_db_dir.rmdir()
