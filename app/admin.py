"""Small account administration screens with serialized access changes"""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .admin_forms import CreateAccountForm, EditAccountForm, ROLE_CHOICES, STATE_CHOICES
from .auth import roles_required
from .extensions import db
from .models import User

bp = Blueprint("admin", __name__, url_prefix="/admin")
ADMIN_LOCK_KEY = 87164021

@bp.before_request
def require_account_configuration():
    """Before each admin request, return 503 if the database or signing key is missing"""
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        abort(503)

def locked_accounts(target_id=None):
    """Lock and reload accounts before creating an account or changing access.

    The actor is the signed-in administrator; the optional target is the account
    being edited.A shared transaction lock makes admin changes run one at a time,
    preventing simultaneous changes from removing the last active administrator.
    Row locks protect these accounts from other updates until commit or rollback.

    Recheck the actor's role, active status, and session version after waiting,
    since another request may have revoked their access. Return (actor, target),
    with target=None for creation;reject revoked access with 403 or a missing
    target with 404. The caller must commit or roll back to release the locks
    """
    actor_id = current_user.id
    original_session_id = session.get("_user_id")
    db.session.execute(sa.select(sa.func.pg_advisory_xact_lock(ADMIN_LOCK_KEY)))
    identifiers = [actor_id] if target_id is None else [actor_id, target_id]
    rows = db.session.scalars(db.select(User).where(User.id.in_(identifiers)).order_by(User.id)
                              .with_for_update().execution_options(populate_existing=True)).all()
    accounts = {user.id: user for user in rows}
    actor = accounts.get(actor_id)
    if not actor or not actor.is_active or actor.role != "administrator" or actor.get_id() != original_session_id:
        db.session.rollback()
        abort(403)
    if target_id is not None and target_id not in accounts:
        db.session.rollback()
        abort(404)
    return actor, accounts.get(target_id)


def find_account(identifier):
    """Return an account by ID, or respond with 404 if the ID is invalid or absent"""
    if not 0 < identifier <= 2147483647:
        abort(404)
    user = db.session.get(User, identifier)
    if user is None:
        abort(404)
    return user


@bp.get("/accounts")
@roles_required("administrator")
def accounts():
    """GET /admin/accounts: show the administrator's filterable account list.

    Filter by role, active/inactive state, and name or email search text supplied
    in the URL query parameters. Invalid filters return 400; this endpoint only
    reads accounts and renders the list, without changing access
    """
    role = request.args.get("role", "")
    state = request.args.get("state", "")
    search = request.args.get("search", "").strip()
    if role not in ["", *dict(ROLE_CHOICES)] or state not in ["", *dict(STATE_CHOICES)] or len(search) > 100:
        abort(400)
    query = db.select(User).order_by(User.name, User.id)
    if role:
        query = query.where(User.role == role)
    if state:
        query = query.where(User.is_active.is_(state == "active"))
    if search:
        query = query.where(sa.or_(User.name.icontains(search, autoescape=True), User.email.icontains(search, autoescape=True)))
    return render_template("admin/accounts.html", accounts=db.session.scalars(query).all(),
                           role=role, state=state, search=search, roles=ROLE_CHOICES, states=STATE_CHOICES)


@bp.route("/accounts/new", methods=["GET", "POST"])
@roles_required("administrator")
def create():
    """GET shows the new-account form; POST creates a validated active account.

    Only administrators may choose the new account's role. Hash the password,
    recheck administrator access under locks, and save the account. Show form
    errors for invalid input or a duplicate email; redirect to the list on success
    """
    form = CreateAccountForm()
    if form.validate_on_submit():
        password_hash = generate_password_hash(form.password.data, method="scrypt")
        locked_accounts()
        db.session.add(User(name=form.name.data, email=form.email.data, password_hash=password_hash,
                            role=form.role.data, is_active=True))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.email.errors.append("An account with this email already exists.")
        else:
            flash("Account created.")
            return redirect(url_for("admin.accounts"))
    return render_template("admin/edit.html", form=form, title="Create account", account=None)


@bp.route("/accounts/<int:identifier>/edit", methods=["GET", "POST"])
@roles_required("administrator")
def edit(identifier):
    """GET shows an account's access settings; POST updates its role and status.
    Only administrators may make changes.Preserve the account and reservation
    history, and reject demoting or deactivating the last active administrator.
    A real access change increments the credential version to revoke sessions
    and reset links; changing your own access also signs you out immediately.
    Names, emails, and passwords are not editable through this endpoint
    """
    target = find_account(identifier)
    form = EditAccountForm()
    error = None
    if request.method == "GET":
        form.role.data = target.role
        form.state.data = "active" if target.is_active else "inactive"
    if form.validate_on_submit():
        actor, target = locked_accounts(identifier)
        active = form.state.data == "active"
        changed = target.role != form.role.data or target.is_active != active
        removes_admin = target.is_active and target.role == "administrator" and (not active or form.role.data != "administrator")
        admin_count = db.session.scalar(sa.select(sa.func.count()).select_from(User).where(User.is_active.is_(True), User.role == "administrator"))
        if removes_admin and admin_count <= 1:
            db.session.rollback()
            error = "At least one active administrator must remain. Create or activate another administrator first."
        else:
            if changed:
                target.role, target.is_active = form.role.data, active
                target.auth_version += 1
            self_changed = changed and target.id == actor.id
            db.session.commit()
            if self_changed:
                logout_user()
                session.clear()
                return redirect(url_for("auth.login"))
            flash("Account access updated." if changed else "Account access is unchanged.")
            return redirect(url_for("admin.accounts"))
    return render_template("admin/edit.html", form=form, title="Manage account access", account=target, error=error)
