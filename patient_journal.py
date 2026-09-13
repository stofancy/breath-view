"""Private, device-scoped treatment change journal.

The journal is intentionally separate from the imported device snapshots and
from patient-contexts.json.  It contains only notes the patient chose to add
about treatment or life changes, and is written with the same private,
atomic-file convention as the existing context store.
"""

from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import secrets
import tempfile


KINDS = frozenset({'mask', 'clinician', 'comfort', 'lifestyle', 'illness', 'other'})
MAX_CHANGES = 2000
_DATE_RE = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')


def _home_path(home):
    return Path(home).expanduser().resolve()


def _store_path(home):
    return _home_path(home) / 'patient-changes.json'


def _serial(serial):
    if not isinstance(serial, str) or not serial:
        raise ValueError('设备序列号无效')
    return serial


def _change_id(value):
    if not isinstance(value, str) or not value:
        raise ValueError('治疗记录编号无效')
    return value


def _change_date(value):
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError('治疗记录日期格式无效')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('治疗记录日期无效') from exc
    if not 2000 <= parsed.year <= 2099:
        raise ValueError('治疗记录日期须在 2000 至 2099 年之间')
    return value


def _kind(value):
    if not isinstance(value, str) or value not in KINDS:
        raise ValueError('治疗记录类型无效')
    return value


def _note(value):
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError('治疗记录备注最多 1000 字')
    return value


def _now():
    return datetime.now().isoformat(timespec='seconds')


def _input(value, require_id=False):
    if not isinstance(value, dict):
        raise ValueError('治疗记录格式无效')
    identifier = value.get('id')
    if require_id or identifier is not None:
        identifier = _change_id(identifier)
    elif identifier is None:
        identifier = None
    return {
        'id': identifier,
        'date': _change_date(value.get('date')),
        'kind': _kind(value.get('kind')),
        'note': _note(value.get('note', '')),
    }


def _stored(value):
    """Validate a persisted entry without accepting partial records."""
    if not isinstance(value, dict):
        raise ValueError('治疗记录数据格式无效')
    identifier = _change_id(value.get('id'))
    created_at = value.get('created_at')
    updated_at = value.get('updated_at')
    if not isinstance(created_at, str) or not created_at:
        raise ValueError('治疗记录时间格式无效')
    if not isinstance(updated_at, str) or not updated_at:
        raise ValueError('治疗记录时间格式无效')
    result = _input(value, require_id=True)
    result.update(id=identifier, created_at=created_at, updated_at=updated_at)
    return result


def _read(home):
    path = _store_path(home)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('治疗记录文件无法读取') from exc
    if not isinstance(value, dict):
        raise ValueError('治疗记录文件格式无效')
    return value


def _entries(store, serial):
    values = store.get(serial, [])
    if not isinstance(values, list):
        raise ValueError('治疗记录文件格式无效')
    result = [_stored(item) for item in values]
    if len(result) > MAX_CHANGES:
        raise ValueError('治疗记录数量超过上限')
    if len({item['id'] for item in result}) != len(result):
        raise ValueError('治疗记录编号重复')
    return result


def _write(home, store):
    root = _home_path(home)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / 'patient-changes.json'
    fd, temporary = tempfile.mkstemp(prefix='.patient-changes-', dir=root)
    try:
        os.close(fd)
        temporary = Path(temporary)
        os.chmod(temporary, 0o600)
        temporary.write_text(json.dumps(store, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        os.replace(temporary, target)
    finally:
        temporary = Path(temporary)
        temporary.unlink(missing_ok=True)


def load_changes(home, serial):
    """Return only the current device's validated treatment changes."""
    serial = _serial(serial)
    return _entries(_read(home), serial)


def upsert_change(home, serial, value):
    """Create or update one change and return the stored entry."""
    serial = _serial(serial)
    supplied = _input(value)
    store = _read(home)
    entries = _entries(store, serial)
    identifier = supplied['id']
    now = _now()
    if identifier is None:
        if len(entries) >= MAX_CHANGES:
            raise ValueError('治疗记录数量已达到上限')
        identifier = secrets.token_hex(16)
        entry = {**supplied, 'id': identifier, 'created_at': now, 'updated_at': now}
        entries.append(entry)
    else:
        for index, existing in enumerate(entries):
            if existing['id'] == identifier:
                entry = {**supplied, 'id': identifier, 'created_at': existing['created_at'], 'updated_at': now}
                entries[index] = entry
                break
        else:
            raise ValueError('找不到治疗记录')
    store[serial] = entries
    _write(home, store)
    return dict(entry)


def delete_change(home, serial, identifier):
    """Delete one change from the current device and return its old entry."""
    serial = _serial(serial)
    identifier = _change_id(identifier)
    store = _read(home)
    entries = _entries(store, serial)
    for index, existing in enumerate(entries):
        if existing['id'] == identifier:
            removed = entries.pop(index)
            store[serial] = entries
            _write(home, store)
            return dict(removed)
    raise ValueError('找不到治疗记录')
