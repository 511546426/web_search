"""
可选：写入一些示例数据，方便首次打开页面就有内容。
在 backend 目录执行：python scripts/seed_demo.py
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.models import Anniversary, Memory, Note, Photo

def main():
    init_db()
    db = SessionLocal()
    try:
        if db.query(Anniversary).first():
            print("已有数据，跳过 seed。")
            return
        # 在一起的日子（示例：一年前）
        start = date.today() - timedelta(days=365)
        db.add(Anniversary(name="在一起的日子", date=start, repeat_yearly=True))
        db.add(Anniversary(name="第一次约会", date=start + timedelta(days=7), repeat_yearly=True))
        db.commit()
        db.add(Memory(
            title="第一次见面",
            content="那天阳光很好，你笑起来的样子我一直记得。",
            happened_at=datetime.utcnow() - timedelta(days=360),
            mood="心动",
        ))
        db.add(Memory(
            content="想和你一起看很多很多次日落。",
            happened_at=datetime.utcnow() - timedelta(days=30),
            mood="开心",
        ))
        db.add(Note(content="每天都要更爱你一点", is_public=True))
        db.add(Note(content="你是我的小幸运", is_public=True))
        db.commit()
        print("示例数据已写入，刷新页面即可看到。💕")
    finally:
        db.close()

if __name__ == "__main__":
    main()
