"""Operational commands. Usage: python -m app.cli create-user --email you@example.com --role ADMIN

The password is read from the REI_PASSWORD env var or prompted (never passed as an argument,
so it does not land in shell history)."""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import User
from app.models.enums import UserRole


def create_user(email: str, role: UserRole) -> None:
    password = os.environ.get("REI_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 12:
        sys.exit("Password must have at least 12 characters.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"User {email} already exists.")
        db.add(User(email=email, password_hash=hash_password(password), role=role))
        db.commit()
    print(f"Created {role} user {email}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user")
    create.add_argument("--email", required=True)
    create.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.VIEWER)
    args = parser.parse_args()
    if args.command == "create-user":
        create_user(args.email.strip(), UserRole(args.role))


if __name__ == "__main__":
    main()
