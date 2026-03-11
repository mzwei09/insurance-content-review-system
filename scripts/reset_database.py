#!/usr/bin/env python3
"""重置用户数据库"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db

def main():
    db_path = Path("data/users.db")
    
    if db_path.exists():
        print(f"🗑️  删除旧数据库: {db_path}")
        db_path.unlink()
    
    print("🔧 初始化新数据库...")
    init_db()
    
    print("✅ 数据库已重置")
    print()
    print("下一步:")
    print("  1. 访问 http://localhost:8000")
    print("  2. 注册新账号")
    print("  3. 在个人中心配置你的百炼 API 密钥")

if __name__ == "__main__":
    main()
