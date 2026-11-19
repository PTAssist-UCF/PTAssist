"""Make a user a therapist, found by the email they signed in with.

New users are patients, and the team promotes therapists with this script. The person
must sign in to the web app once first, so their user exists.

Run from backend/, with DATABASE_URL set to the database to change:

    python -m app.promote_therapist --email someone@example.com           # therapist
    python -m app.promote_therapist --email someone@example.com --demote  # patient

In Azure it runs as a manual Container Apps job (infra/README.md, Promote a therapist).
It prints the user's id, never their email: in Azure, its output goes to the logs.
"""

import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Plan, Role, TherapistPatient, User


class RoleChangeError(Exception):
    """The role can't be changed as asked. The message says why."""


def set_role(
    db: Session, email: str, role: Role, *, force: bool = False
) -> tuple[User, bool]:
    """Give the user with this email the role. Return them, and whether it changed.

    Someone who has links or plans in their current role is refused unless force is
    set: the links and plans stay, but they can't use them in the new role. A new
    therapist has only signed in once and has neither, so it is likely the wrong email.
    """
    user = _find_user(db, email)
    if user.role == role:
        return user, False
    if not force:
        links, plans = _links_and_plans(db, user)
        if links or plans:
            raise RoleChangeError(
                f"User {user.id} has {links} link(s) and {plans} plan(s) as a "
                f"{user.role}. As a {role} they could no longer use them. If this is "
                "the right person, run it again with --force."
            )
    user.role = role
    db.commit()
    return user, True


def _find_user(db: Session, email: str) -> User:
    # Ignores case and spaces around it: "Jane@Example.com " finds jane@example.com.
    users = db.scalars(
        select(User).where(func.lower(User.email) == func.lower(email.strip()))
    ).all()
    if not users:
        raise RoleChangeError(
            "No user has that email. The person must sign in to the web app once "
            "first, which creates their user."
        )
    if len(users) > 1:
        raise RoleChangeError(
            f"{len(users)} users have that email, so it is not clear which one to "
            "change."
        )
    return users[0]


def _links_and_plans(db: Session, user: User) -> tuple[int, int]:
    """Count the therapist-patient links and the plans the user is in, in their role."""
    if user.role == Role.PATIENT:
        in_link = TherapistPatient.patient_id == user.id
        in_plan = Plan.patient_id == user.id
    else:
        in_link = TherapistPatient.therapist_id == user.id
        in_plan = Plan.therapist_id == user.id
    links = db.scalar(select(func.count()).select_from(TherapistPatient).where(in_link))
    plans = db.scalar(select(func.count()).select_from(Plan).where(in_plan))
    return links, plans


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True, help="the email they signed in with")
    parser.add_argument(
        "--demote", action="store_true", help="make a therapist a patient again"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="change the role even if they have links or plans in their current role",
    )
    args = parser.parse_args()
    role = Role.PATIENT if args.demote else Role.THERAPIST
    with Session(engine) as db:
        try:
            user, changed = set_role(db, args.email, role, force=args.force)
        except RoleChangeError as exc:
            sys.exit(f"Role not changed: {exc}")
        if changed:
            print(
                f"User {user.id} is now a {role}. They see the {role} side of the web "
                "app after they reload it."
            )
        else:
            print(f"User {user.id} is already a {role}. Nothing changed.")


if __name__ == "__main__":
    main()
