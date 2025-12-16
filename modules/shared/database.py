"""
Supabase database client
"""
from supabase import create_client, Client
from modules.shared.config import SUPABASE_URL, SUPABASE_KEY


def get_supabase_client() -> Client:
    """
    创建并返回 Supabase 客户端实例
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL 和 SUPABASE_KEY 必须在环境变量中设置")
    
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# 全局客户端实例（可选）
supabase: Client | None = None

try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = get_supabase_client()
except Exception as e:
    print(f"警告: 无法初始化 Supabase 客户端: {e}")

