from app.db.database import Base, engine, SessionLocal
from app.db.models import UserModel, AccountModel

def test_database_schema_and_relations():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = UserModel(user_id="USR-DB-01", username="db_trader", email="db@pdeue.io")
        db.add(user)
        db.commit()

        acc1 = AccountModel(account_id="ACC-DB-01", user_id="USR-DB-01", account_name="Main Account", balance_cents=1000000)
        acc2 = AccountModel(account_id="ACC-DB-02", user_id="USR-DB-01", account_name="Risk Reserve", balance_cents=250000)
        db.add_all([acc1, acc2])
        db.commit()

        fetched_user = db.query(UserModel).filter(UserModel.user_id == "USR-DB-01").first()
        assert fetched_user is not None
        assert len(fetched_user.accounts) == 2
        assert fetched_user.accounts[0].balance_cents == 1000000
    finally:
        db.close()
