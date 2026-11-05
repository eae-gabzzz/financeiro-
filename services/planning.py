"""Persistência de orçamentos e metas, sempre isolada pelo uid autenticado."""
from __future__ import annotations

import functools
import hashlib
import uuid

from google.api_core import exceptions as gexc
from google.cloud.firestore import SERVER_TIMESTAMP
from google.cloud.firestore_v1.base_query import FieldFilter

from database.firebase import FirebaseConfigError, resolve_db
from services.transactions import MAX_CENTS

COLLECTION = "financial_plans"


class PlanningError(Exception):
    """Erro base das funções de planejamento financeiro."""


class PlanningValidationError(PlanningError): ...
class PlanningNotFoundError(PlanningError): ...
class PlanningAuthorizationError(PlanningError): ...
class PlanningStorageError(PlanningError): ...


def _storage(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (gexc.GoogleAPICallError, gexc.RetryError) as exc:
            raise PlanningStorageError(
                "Não foi possível acessar os dados de planejamento. Verifique a conexão "
                "e as permissões do Firebase."
            ) from exc
    return wrapper


def _db(db=None):
    try:
        return resolve_db(db)
    except FirebaseConfigError as exc:
        raise PlanningStorageError(str(exc)) from exc


def _uid(uid) -> str:
    if not isinstance(uid, str) or not uid.strip():
        raise PlanningAuthorizationError("Autenticação necessária.")
    return uid


def _amount(value, *, allow_zero=False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > MAX_CENTS:
        raise PlanningValidationError("Informe um valor válido em centavos.")
    return value


def _owned_doc(uid: str, plan_id: str, db, *, kind: str | None = None):
    if not isinstance(plan_id, str) or not plan_id or "/" in plan_id:
        raise PlanningNotFoundError("Planejamento não encontrado.")
    ref = _db(db).collection(COLLECTION).document(plan_id)
    snap = ref.get()
    data = snap.to_dict() if snap.exists else None
    if not data or data.get("user_id") != uid or (kind and data.get("kind") != kind):
        raise PlanningNotFoundError("Planejamento não encontrado.")
    return ref, data


@_storage
def list_budgets(uid, *, db=None) -> list[dict]:
    uid = _uid(uid)
    docs = _db(db).collection(COLLECTION).where(filter=FieldFilter("user_id", "==", uid)).stream()
    return sorted(
        ({**snap.to_dict(), "id": snap.id} for snap in docs
         if (snap.to_dict() or {}).get("kind") == "budget"),
        key=lambda budget: budget["category"].casefold(),
    )


@_storage
def set_budget(uid, category, amount_cents, *, db=None) -> str:
    uid = _uid(uid)
    category = (category or "").strip()
    if not category or len(category) > 40:
        raise PlanningValidationError("Informe uma categoria válida.")
    amount_cents = _amount(amount_cents)
    plan_id = "budget-" + hashlib.sha256(f"{uid}\0{category.casefold()}".encode()).hexdigest()[:32]
    ref = _db(db).collection(COLLECTION).document(plan_id)
    snap = ref.get()
    existing = snap.to_dict() if snap.exists else None
    if existing and existing.get("user_id") != uid:
        raise PlanningAuthorizationError("Operação não permitida.")
    payload = {
        "kind": "budget",
        "user_id": uid,
        "category": category,
        "amount_cents": amount_cents,
        "updated_at": SERVER_TIMESTAMP,
    }
    if existing:
        ref.update(payload)
    else:
        ref.set({**payload, "created_at": SERVER_TIMESTAMP})
    return plan_id


@_storage
def delete_budget(uid, plan_id, *, db=None) -> None:
    uid = _uid(uid)
    ref, _ = _owned_doc(uid, plan_id, db, kind="budget")
    ref.delete()


@_storage
def add_savings_goal(uid, name, target_cents, *, db=None) -> str:
    uid = _uid(uid)
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise PlanningValidationError("Informe um nome de meta com até 80 caracteres.")
    target_cents = _amount(target_cents)
    plan_id = "goal-" + uuid.uuid4().hex
    _db(db).collection(COLLECTION).document(plan_id).create({
        "kind": "goal",
        "user_id": uid,
        "name": name,
        "target_cents": target_cents,
        "saved_cents": 0,
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    })
    return plan_id


@_storage
def list_savings_goals(uid, *, db=None) -> list[dict]:
    uid = _uid(uid)
    docs = _db(db).collection(COLLECTION).where(filter=FieldFilter("user_id", "==", uid)).stream()
    goals = ({**snap.to_dict(), "id": snap.id} for snap in docs
             if (snap.to_dict() or {}).get("kind") == "goal")
    return sorted(goals, key=lambda goal: goal["created_at"] if goal.get("created_at") else "", reverse=True)


@_storage
def update_savings_goal(uid, plan_id, saved_cents, *, db=None) -> None:
    uid = _uid(uid)
    saved_cents = _amount(saved_cents, allow_zero=True)
    ref, _ = _owned_doc(uid, plan_id, db, kind="goal")
    ref.update({"saved_cents": saved_cents, "updated_at": SERVER_TIMESTAMP})


@_storage
def delete_savings_goal(uid, plan_id, *, db=None) -> None:
    uid = _uid(uid)
    ref, _ = _owned_doc(uid, plan_id, db, kind="goal")
    ref.delete()
