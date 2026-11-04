"""Regras de negócio e acesso ao Firestore para movimentações.

Toda função exige o `uid` JÁ VERIFICADO no servidor e checa a propriedade do documento,
pois o Admin SDK ignora as regras de segurança do Firestore.
"""
from __future__ import annotations

import functools
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from google.api_core import exceptions as gexc
from google.cloud.firestore import SERVER_TIMESTAMP
from google.cloud.firestore_v1.base_query import FieldFilter

from database.firebase import FirebaseConfigError, resolve_db

COLLECTION = "transactions"
INCOME, EXPENSE = "income", "expense"
TYPE_LABELS = {INCOME: "Receita", EXPENSE: "Despesa"}
CATEGORIES = {
    INCOME: ["Salário", "Freelance", "Investimentos", "Vendas", "Presentes", "Outros"],
    EXPENSE: ["Alimentação", "Moradia", "Transporte", "Saúde", "Educação", "Lazer",
              "Assinaturas", "Compras", "Contas", "Outros"],
}
MAX_CENTS = 10**13


class TransactionError(Exception):
    """Erro base (mensagem amigável)."""


class ValidationError(TransactionError): ...
class NotFoundError(TransactionError): ...
class AuthorizationError(TransactionError): ...
class StorageError(TransactionError): ...


@dataclass(frozen=True)
class Totals:
    income_cents: int
    expense_cents: int

    @property
    def balance_cents(self) -> int:
        return self.income_cents - self.expense_cents


def _storage(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (gexc.GoogleAPICallError, gexc.RetryError) as exc:
            raise StorageError(
                "Não foi possível acessar o banco de dados. Verifique a conexão e as "
                "permissões do Firebase."
            ) from exc
    return wrapper


def _db(db=None):
    try:
        return resolve_db(db)
    except FirebaseConfigError as exc:
        raise StorageError(str(exc)) from exc


def _require_uid(uid) -> str:
    if not isinstance(uid, str) or not uid.strip():
        raise AuthorizationError("Autenticação necessária.")
    return uid


def _iso(value) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValidationError("Data inválida.") from exc


def _clean(data: dict) -> dict:
    """Valida e normaliza os campos editáveis de uma movimentação."""
    tx_type = data.get("type")
    if tx_type not in (INCOME, EXPENSE):
        raise ValidationError("Tipo de movimentação inválido.")
    description = (data.get("description") or "").strip()
    if not description:
        raise ValidationError("Informe uma descrição.")
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValidationError("O valor deve ser maior que zero.")
    if amount > MAX_CENTS:
        raise ValidationError("Valor acima do limite permitido.")
    category = (data.get("category") or "").strip()
    if not category:
        raise ValidationError("Informe uma categoria.")
    return {
        "type": tx_type,
        "description": description[:120],
        "amount_cents": amount,
        "category": category[:40],
        "date": _iso(data.get("date")),
        "notes": (data.get("notes") or "").strip()[:500],
    }


def _tx_id(tx_id) -> str:
    if not isinstance(tx_id, str) or not tx_id or "/" in tx_id:
        raise NotFoundError("Movimentação não encontrada.")
    return tx_id


def _owned(uid: str, tx_id: str, db):
    ref = _db(db).collection(COLLECTION).document(_tx_id(tx_id))
    snap = ref.get()
    data = snap.to_dict() if snap.exists else None
    if not data or data.get("user_id") != uid:
        raise NotFoundError("Movimentação não encontrada.")  # não revela se existe
    return ref, data


# ---------- criação ----------
@_storage
def create_transaction(uid, data, *, tx_id=None, db=None) -> str:
    """Cria a movimentação. Com `tx_id` fixo a operação é idempotente (sem duplicatas)."""
    uid = _require_uid(uid)
    payload = _clean(data)
    tx_id = _tx_id(tx_id or uuid.uuid4().hex)
    ref = _db(db).collection(COLLECTION).document(tx_id)
    try:
        ref.create({**payload, "user_id": uid, "created_at": SERVER_TIMESTAMP})
    except gexc.AlreadyExists:
        if (ref.get().to_dict() or {}).get("user_id") != uid:
            raise AuthorizationError("Operação não permitida.") from None
    return tx_id


def create_income(uid, data, **kwargs) -> str:
    return create_transaction(uid, {**data, "type": INCOME}, **kwargs)


def create_expense(uid, data, **kwargs) -> str:
    return create_transaction(uid, {**data, "type": EXPENSE}, **kwargs)


# ---------- leitura ----------
def _row(snap) -> dict:
    row = snap.to_dict()
    row["id"] = snap.id
    return row


def _sort_key(tx):
    created = tx.get("created_at")
    return (tx.get("date", ""), created.timestamp() if hasattr(created, "timestamp") else 0.0)


def filter_transactions(items, *, tx_type=None, category=None, search=None,
                        date_from=None, date_to=None) -> list[dict]:
    """Filtro puro (não altera os totais globais)."""
    query = (search or "").strip().casefold()
    start = _iso(date_from) if date_from else None
    end = _iso(date_to) if date_to else None
    result = []
    for tx in items:
        if tx_type and tx["type"] != tx_type:
            continue
        if category and tx["category"] != category:
            continue
        if query and query not in tx["description"].casefold():
            continue
        if start and tx["date"] < start:
            continue
        if end and tx["date"] > end:
            continue
        result.append(tx)
    return result


@_storage
def list_transactions(uid, *, tx_type=None, category=None, search=None,
                      date_from=None, date_to=None, db=None) -> list[dict]:
    """Movimentações do usuário, da mais recente para a mais antiga."""
    uid = _require_uid(uid)
    snaps = _db(db).collection(COLLECTION).where(filter=FieldFilter("user_id", "==", uid)).stream()
    items = sorted((_row(s) for s in snaps), key=_sort_key, reverse=True)
    return filter_transactions(items, tx_type=tx_type, category=category, search=search,
                               date_from=date_from, date_to=date_to)


@_storage
def get_transaction(uid, tx_id, *, db=None) -> dict:
    uid = _require_uid(uid)
    ref, data = _owned(uid, tx_id, db)
    return {**data, "id": ref.id}


# ---------- alteração ----------
@_storage
def update_transaction(uid, tx_id, data, *, db=None) -> None:
    uid = _require_uid(uid)
    ref, _ = _owned(uid, tx_id, db)
    ref.update({**_clean(data), "updated_at": SERVER_TIMESTAMP})


@_storage
def delete_transaction(uid, tx_id, *, db=None) -> None:
    uid = _require_uid(uid)
    ref, _ = _owned(uid, tx_id, db)
    ref.delete()


# ---------- totais ----------
def summarize(items) -> Totals:
    income = sum(t["amount_cents"] for t in items if t["type"] == INCOME)
    expense = sum(t["amount_cents"] for t in items if t["type"] == EXPENSE)
    return Totals(income, expense)


def calculate_totals(uid, *, db=None) -> Totals:
    """Receita, despesas e saldo (property) do usuário, lidos do Firestore."""
    return summarize(list_transactions(uid, db=db))
