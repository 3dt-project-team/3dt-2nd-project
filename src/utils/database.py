from sqlalchemy.orm import sessionmaker

# 같은 utils 폴더 안에 있는 vault 객체를 바로 가져옵니다.
from src.utils.vault_manager import vault


def get_db_session():
    """
    VaultManager의 get_pg_connection을 사용하여
    SQLAlchemy 엔진을 생성하고 세션을 반환합니다.
    """
    # 1. VaultManager에서 SQLAlchemy 엔진을 직접 가져옵니다.
    # 내부적으로 'pg-connection-string' 시크릿을 사용합니다.
    engine = vault.get_pg_connection(engine="sqlalchemy")

    # 2. 세션 생성기를 설정합니다.
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return SessionLocal()


# routes.py에서 'from src.utils.database import SessionLocal'로
# 불러올 수 있도록 변수를 설정합니다.
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=vault.get_pg_connection(engine="sqlalchemy")
)
