"""
Run once after the database is up and schema.sql has been applied:
    python seed.py

Creates: one hardcoded test user per persona + a superadmin, one KB folder per
persona, and an example tag taxonomy for the 'product' folder (matching the
example in the original requirements: Product Name, Product Version, Doctype, Geography).
"""

import uuid
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.models import Role, User, Folder, TagTaxonomy

PERSONAS = ["legal", "infosec", "infrastructure", "product", "business", "engineering"]

TEST_PASSWORDS = {
    "legal": "legal123", "infosec": "infosec123", "infrastructure": "infra123",
    "product": "product123", "business": "business123", "engineering": "engineering123",
    "admin": "admin123",
}


def run():
    db = SessionLocal()

    # Users (roles already seeded by schema.sql)
    for persona in PERSONAS:
        role = db.query(Role).filter(Role.name == persona).first()
        existing = db.query(User).filter(User.username == persona).first()
        if not existing:
            db.add(User(id=str(uuid.uuid4()), username=persona,
                        password_hash=hash_password(TEST_PASSWORDS[persona]), role_id=role.id))

    admin_role = db.query(Role).filter(Role.name == "superadmin").first()
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(id=str(uuid.uuid4()), username="admin",
                    password_hash=hash_password(TEST_PASSWORDS["admin"]), role_id=admin_role.id))
    db.commit()

    # Persona KB folders
    for persona in PERSONAS:
        role = db.query(Role).filter(Role.name == persona).first()
        existing = db.query(Folder).filter(Folder.name == persona, Folder.folder_type == "kb_persona").first()
        if not existing:
            db.add(Folder(id=str(uuid.uuid4()), name=persona, folder_type="kb_persona", owner_role_id=role.id))
    db.commit()

    # Example tag taxonomy for the 'product' folder, per the original spec's example
    product_folder = db.query(Folder).filter(Folder.name == "product", Folder.folder_type == "kb_persona").first()
    example_tags = [
        ("Doctype", None, True),
        ("Product Name", None, True),
        ("Product Version", None, True),
        ("Geography", ["All", "US", "EU", "APAC"], False),
    ]
    for tag_key, allowed_values, required in example_tags:
        exists = db.query(TagTaxonomy).filter(TagTaxonomy.folder_id == product_folder.id, TagTaxonomy.tag_key == tag_key).first()
        if not exists:
            db.add(TagTaxonomy(id=str(uuid.uuid4()), folder_id=product_folder.id, tag_key=tag_key,
                                allowed_values=allowed_values, required=required))
    db.commit()
    db.close()
    print("Seed complete. Test accounts (username/password):")
    for u, p in TEST_PASSWORDS.items():
        print(f"  {u} / {p}")


if __name__ == "__main__":
    run()
