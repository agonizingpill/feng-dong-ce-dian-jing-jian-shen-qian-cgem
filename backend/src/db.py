import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
url = os.environ['DATABASE_URL']
# MySQL 业务库使用 READ COMMITTED；SQLite 仅用于本地测试，不支持该隔离级别参数。
options = {'pool_pre_ping': True}
if not url.startswith('sqlite'):
    options['isolation_level'] = 'READ COMMITTED'
engine = create_engine(url, **options)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
def db_session():
    with Session() as s:
        yield s
