# utils/auth.py
import json
import os
from flask import request
import config

# 内存中缓存有效卡密
VALID_KEYS = set()

def load_keys():
    global VALID_KEYS
    # 如果文件不存在，清空集合
    if not os.path.exists(config.KEYS_FILE):
        VALID_KEYS.clear()
        return

    try:
        with open(config.KEYS_FILE, 'r', encoding='utf-8') as f:
            keys = json.load(f)
            # 【核心修复】不要使用 = 赋值，而是更新集合内容，保持内存地址不变
            VALID_KEYS.clear()
            VALID_KEYS.update(keys)
    except:
        VALID_KEYS.clear()

def save_keys():
    with open(config.KEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(VALID_KEYS), f)

# --- 新增：封装好的操作函数，供 routes.py 调用 ---

def get_all_keys():
    """获取所有 Key 列表"""
    if not VALID_KEYS:
        load_keys()
    return list(VALID_KEYS)

def add_key(key):
    """添加 Key"""
    if not VALID_KEYS:
        load_keys()
    VALID_KEYS.add(key)
    save_keys()

def remove_key(key):
    """删除 Key"""
    if not VALID_KEYS:
        load_keys()
    if key in VALID_KEYS:
        VALID_KEYS.remove(key)
        save_keys()

def is_valid_key(key):
    # 确保最新
    if not VALID_KEYS:
        load_keys()
    return key in VALID_KEYS

def check_auth():
    """Flask 路由中使用的鉴权辅助函数"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return False
    # 懒加载
    if not VALID_KEYS:
        load_keys()
    return user_id in VALID_KEYS

# 初始化加载
load_keys()