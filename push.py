"""
手機推播通知 (Web Push)。邏輯沿用 crypto-monitor 專案已經驗證過的 VAPID 模式:
金鑰第一次啟動時自動產生+存到磁碟, 之後都讀同一把, 不然每次重啟金鑰換掉的話使用者手機上
原本訂閱的推播會全部失效。跟crypto-monitor的差異只有訂閱清單改存SQLite(這裡本來就用SQLite),
不再另外存一份JSON。
"""
import base64
import json
import logging
import os

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush

import db

log = logging.getLogger("pet-care")

VAPID_KEY_FILE = os.environ.get("VAPID_KEY_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "vapid_private_key.pem"
)
VAPID_SUBJECT = "mailto:pet-care-owner@example.com"  # Web Push規範要求的聯絡資訊格式, 不會真的寄信
HTTP_TIMEOUT = 10

_vapid = None
_vapid_public_key_b64 = None


def init_vapid():
    global _vapid, _vapid_public_key_b64
    if _vapid is not None:
        return
    try:
        _vapid = Vapid02.from_file(VAPID_KEY_FILE)
        pub_bytes = _vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        _vapid_public_key_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
        log.info("VAPID金鑰已就緒, 推播通知功能可用")
    except Exception as e:
        log.warning(f"VAPID金鑰初始化失敗, 推播通知功能停用(不影響其他功能): {e}")


def get_public_key():
    init_vapid()
    return _vapid_public_key_b64


def add_subscription(sub):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (endpoint, keys_json) VALUES (?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET keys_json = excluded.keys_json",
            (sub["endpoint"], json.dumps(sub)),
        )


def remove_subscription(endpoint):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))


def _all_subscriptions():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT endpoint, keys_json FROM push_subscriptions").fetchall()
    return [json.loads(r["keys_json"]) for r in rows]


def send_notification(title, body, url="/"):
    """對所有已訂閱裝置發送一則推播。訂閱已失效(404/410)時順便清掉, 避免每次都浪費請求戳一個死掉的endpoint。"""
    init_vapid()
    if _vapid is None:
        return
    subs = _all_subscriptions()
    if not subs:
        return
    payload = json.dumps({"title": title, "body": body, "url": url})
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=_vapid,
                vapid_claims={"sub": VAPID_SUBJECT},
                timeout=HTTP_TIMEOUT,
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                remove_subscription(sub.get("endpoint"))
                log.info(f"推播失敗(status={status}), 已移除失效訂閱")
            else:
                log.warning(f"推播失敗(status={status}): {e}")
        except Exception as e:
            log.warning(f"推播發生未預期錯誤: {e}")
