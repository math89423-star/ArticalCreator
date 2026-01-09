# utils/auth.py
import json
import os
from flask import request
import config

# 内存中缓存有效卡密
VALID_KEYS = set()

def load_keys():
    global VALID_KEYS
    if not os.path.exists(config.KEYS_FILE):
        VALID_KEYS = set()
        return
    try:
        with open(config.KEYS_FILE, 'r', encoding='utf-8') as f:
            keys = json.load(f)
            VALID_KEYS = set(keys)
    except:
        VALID_KEYS = set()

def save_keys():
    with open(config.KEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(VALID_KEYS), f)

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